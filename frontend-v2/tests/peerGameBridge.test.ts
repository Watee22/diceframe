import { describe, expect, it, vi } from 'vitest'
import {
  PeerHostGameBridge,
  PeerRemoteGameClient,
  type PeerLocalApiExecutor,
} from '@/peer/game/bridge'
import type { MultiPeerConnectionSession } from '@/peer/session/MultiPeerConnectionSession'

describe('peer host game bridge', () => {
  it('maps allowlisted operations to a delegated player identity', async () => {
    const calls: Array<{ path: string; init?: RequestInit }> = []
    const executor: PeerLocalApiExecutor = async (path, init) => {
      calls.push({ path, init })
      if (path === '/games/web%7Cgame%7Chost') {
        return {
          game_key: 'web|game|host',
          player_access_open: true,
          player_count: 1,
          max_players: 6,
        }
      }
      if (path === '/games/web%7Cgame%7Chost/players') {
        return { ok: true, user_id: 'player_123' }
      }
      return { ok: true }
    }
    const changed = vi.fn()
    const bridge = new PeerHostGameBridge('web|game|host', executor, changed)

    await bridge.handle('p_abcdefghijk', 'player.create', {
      character_name: '调查员',
      user_id: 'attempted-impersonation',
      path: '/api/config',
    })
    await bridge.handle('p_abcdefghijk', 'action.submit', { text: '调查房间' })

    const createBody = JSON.parse(String(calls[1].init?.body))
    expect(createBody.user_id).toBeUndefined()
    expect(createBody.join_as_new).toBe(true)
    expect(createBody.path).toBeUndefined()
    expect(createBody.character_name).toBe('调查员')
    expect(calls[3].path).toBe(
      '/games/web%7Cgame%7Chost/action?user=player_123&share=1&delegate=1',
    )
    const actionBody = JSON.parse(String(calls[3].init?.body))
    expect(actionBody).toEqual({ text: '调查房间' })
    expect(changed).toHaveBeenCalledTimes(2)
  })

  it('strips non-whitelisted fields from peer payloads', async () => {
    const calls: Array<{ path: string; init?: RequestInit }> = []
    const executor: PeerLocalApiExecutor = async (path, init) => {
      calls.push({ path, init })
      if (path === '/games/web%7Cgame%7Chost') {
        return { game_key: 'web|game|host', player_access_open: true }
      }
      if (path === '/games/web%7Cgame%7Chost/players') {
        return { ok: true, user_id: 'player_123' }
      }
      return { ok: true }
    }
    const bridge = new PeerHostGameBridge('web|game|host', executor, () => undefined)

    await bridge.handle('p_abcdefghijk', 'player.create', {
      character_name: '调查员',
      user_id: 'attempted-impersonation',
      path: '/api/config',
      role: 'gm',
    })
    const createBody = JSON.parse(String(calls[1].init?.body))
    expect(createBody).toEqual({
      character_name: '调查员',
      join_as_new: true,
    })

    await bridge.handle('p_abcdefghijk', 'luck.resolve', {
      check_id: 'check-1',
      spend: true,
      user_id: 'someone-else',
    })
    expect(calls[3].path).toBe(
      '/games/web%7Cgame%7Chost/checks/check-1/luck?user=player_123&share=1&delegate=1',
    )
    const luckBody = JSON.parse(String(calls[3].init?.body))
    expect(luckBody).toEqual({ spend: true })
  })

  it('stops all player operations when the local game owner closes access', async () => {
    const executor: PeerLocalApiExecutor = async () => ({
      game_key: 'web|game|host',
      player_access_open: false,
    })
    const bridge = new PeerHostGameBridge('web|game|host', executor, () => undefined)

    await expect(bridge.handle('p_abcdefghijk', 'game.detail', {}))
      .rejects.toThrow('player_access_closed')
  })
})

describe('peer remote game client', () => {
  it('translates only known game routes into semantic operations', async () => {
    const requestGame = vi.fn(async (_peerId, operation, payload) => {
      if (operation === 'player.create') return { ok: true, user_id: 'player_456' }
      return { ok: true, operation, payload }
    })
    const session = { requestGame } as unknown as MultiPeerConnectionSession
    const client = new PeerRemoteGameClient(
      session,
      'h_abcdefghijk',
      'web|game|host',
    )

    const result = await client.tryApi<{ user_id: string }>(
      '/games/web%7Cgame%7Chost/players',
      { method: 'POST', body: JSON.stringify({ character_name: '调查员' }) },
    )

    expect(result.value?.user_id).toBe('player_456')
    expect(client.userId).toBe('player_456')
    expect(requestGame).toHaveBeenCalledWith(
      'h_abcdefghijk',
      'player.create',
      { character_name: '调查员' },
    )
    await expect(client.tryApi('/games/web%7Cgame%7Chost/export'))
      .rejects.toThrow('peer_game_operation_not_supported')
    expect(client.handlesGamePath('/games/web%7Cgame%7Chost/scene-image')).toBe(true)
    expect(client.handlesGamePath('/games/another-game/scene-image')).toBe(false)
    expect((await client.tryApi('/config')).handled).toBe(false)
  })

  it('rebinds a returning guest to its previous actor instead of creating a new character', async () => {
    localStorage.setItem('diceframe_peer_actor_web|game|host', 'player_789')
    try {
      const requestGame = vi.fn(async (_peerId, operation) => {
        if (operation === 'player.rebind') return { ok: true, user_id: 'player_789', rebound: true }
        throw new Error('unexpected_operation')
      })
      const session = { requestGame } as unknown as MultiPeerConnectionSession
      const client = new PeerRemoteGameClient(session, 'h_abcdefghijk', 'web|game|host')

      // 构造函数从 localStorage 恢复身份
      expect(client.userId).toBe('player_789')

      const ok = await client.rebindIdentity()
      expect(ok).toBe(true)
      expect(requestGame).toHaveBeenCalledWith(
        'h_abcdefghijk',
        'player.rebind',
        { user_id: 'player_789' },
      )
    } finally {
      localStorage.removeItem('diceframe_peer_actor_web|game|host')
    }
  })

  it('prefers the actor assigned by the invite over an unrelated local cache', async () => {
    localStorage.setItem('diceframe_peer_actor_web|game|host', 'player_old')
    try {
      const requestGame = vi.fn(async () => ({
        ok: true,
        user_id: 'player_assigned',
        rebound: true,
      }))
      const session = { requestGame } as unknown as MultiPeerConnectionSession
      const client = new PeerRemoteGameClient(
        session,
        'h_abcdefghijk',
        'web|game|host',
        'player_assigned',
      )

      expect(client.userId).toBe('player_assigned')
      await expect(client.rebindIdentity()).resolves.toBe(true)
      expect(requestGame).toHaveBeenCalledWith(
        'h_abcdefghijk',
        'player.rebind',
        { user_id: 'player_assigned' },
      )
    } finally {
      localStorage.removeItem('diceframe_peer_actor_web|game|host')
    }
  })

  it('reports rebind failure without throwing when the identity is gone', async () => {
    localStorage.setItem('diceframe_peer_actor_web|game|host', 'player_dead')
    try {
      const requestGame = vi.fn(async () => {
        throw new Error('player_identity_unknown')
      })
      const session = { requestGame } as unknown as MultiPeerConnectionSession
      const client = new PeerRemoteGameClient(session, 'h_abcdefghijk', 'web|game|host')

      await expect(client.rebindIdentity()).resolves.toBe(false)
    } finally {
      localStorage.removeItem('diceframe_peer_actor_web|game|host')
    }
  })
})

describe('peer host bridge player.rebind', () => {
  it('restores the identity map after a guest refresh and rejects unknown actors', async () => {
    const players = [{ user_id: 'player_789', character_name: '调查员' }]
    const executor: PeerLocalApiExecutor = async (path) => {
      if (path.startsWith('/games/web%7Cgame%7Chost')) {
        return {
          game_key: 'web|game|host',
          player_access_open: true,
          players,
        }
      }
      return { ok: true }
    }
    const bridge = new PeerHostGameBridge(
      'web|game|host',
      executor,
      () => undefined,
      { p_abcdefghijk: 'player_789' },
    )

    // 邀请未指定的身份：拒绝，不能拿普通邀请码枚举并冒充角色。
    await expect(bridge.handle('p_abcdefghijk', 'player.rebind', { user_id: 'player_ghost' }))
      .rejects.toThrow('player_identity_not_assigned')

    // 已知身份：恢复映射，后续操作直接以该身份执行
    const result = await bridge.handle('p_abcdefghijk', 'player.rebind', { user_id: 'player_789' })
    expect(result).toMatchObject({ ok: true, user_id: 'player_789', rebound: true })

    await bridge.handle('p_abcdefghijk', 'game.player_context', {})
    const context = await bridge.handle('p_abcdefghijk', 'game.player_context', {})
    expect(context.user_id).toBe('player_789')
  })

  it('refuses to rebind an actor already claimed by a different peer', async () => {
    const players = [{ user_id: 'player_789', character_name: '调查员' }]
    const executor: PeerLocalApiExecutor = async () => ({
      game_key: 'web|game|host',
      player_access_open: true,
      players,
    })
    const bridge = new PeerHostGameBridge(
      'web|game|host',
      executor,
      () => undefined,
      {
        p_abcdefghijk: 'player_789',
        p_cdefghijklm: 'player_789',
      },
    )

    await bridge.handle('p_abcdefghijk', 'player.rebind', { user_id: 'player_789' })
    await expect(bridge.handle('p_cdefghijklm', 'player.rebind', { user_id: 'player_789' }))
      .rejects.toThrow('player_identity_taken')

    // 同一 peer 重复 rebind 幂等
    const again = await bridge.handle('p_abcdefghijk', 'player.rebind', { user_id: 'player_789' })
    expect(again.rebound).toBe(true)
  })

  it('does not let an unassigned new-player invite claim an occupied character', async () => {
    const executor: PeerLocalApiExecutor = async () => ({
      game_key: 'web|game|host',
      player_access_open: true,
      players: [{ user_id: 'player_789', character_name: '调查员' }],
    })
    const bridge = new PeerHostGameBridge('web|game|host', executor, () => undefined)

    await expect(bridge.handle('p_abcdefghijk', 'player.rebind', { user_id: 'player_789' }))
      .rejects.toThrow('player_identity_not_assigned')
  })
})
