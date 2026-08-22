import { describe, expect, it } from 'vitest'
import type { RendezvousRoomResponse } from '../src/api/types'
import {
  DEFAULT_STUN_URL,
  METERED_STUN_URL,
  NEXTCLOUD_STUN_URL,
  decodePeerInvite,
  encodePeerInvites,
  normalizeStunUrls,
  stunUrlsForPreset,
} from '../src/features/peer/inviteCode'

const room: RendezvousRoomResponse = {
  ok: true,
  protocol_version: 2,
  topology: 'host-star',
  room_code: 'H2345678',
  host_peer_id: 'h_abcdefghijk',
  host_token: 'host-token-that-must-never-enter-any-invite',
  invitations: [
    { peer_id: 'p_abcdefghijk', token: 'first-guest-token-with-at-least-thirty-two-characters' },
    { peer_id: 'p_lmnopqrst', token: 'second-guest-token-with-at-least-thirty-two-characters' },
  ],
  expires_at: '2026-08-20T12:05:00+00:00',
  websocket_url: 'wss://api.diceframe.com/v1/rendezvous/rooms/H2345678/ws',
}

function encodePayload(payload: Record<string, unknown>): string {
  const bytes = new TextEncoder().encode(JSON.stringify(payload))
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return `DFP2-${btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '')}`
}

describe('peer invite code', () => {
  it('provides documented presets, a multi-provider option, no STUN, and custom lists', () => {
    expect(stunUrlsForPreset('cloudflare')).toEqual([DEFAULT_STUN_URL])
    expect(stunUrlsForPreset('metered')).toEqual([METERED_STUN_URL])
    expect(stunUrlsForPreset('nextcloud')).toEqual([NEXTCLOUD_STUN_URL])
    expect(stunUrlsForPreset('multi')).toEqual([
      DEFAULT_STUN_URL,
      METERED_STUN_URL,
      NEXTCLOUD_STUN_URL,
    ])
    expect(stunUrlsForPreset('none')).toEqual([])
    expect(stunUrlsForPreset(
      'custom',
      ' stun:one.example.net:3478\nstun:two.example.net:3478 ',
    )).toEqual(['stun:one.example.net:3478', 'stun:two.example.net:3478'])
    expect(() => stunUrlsForPreset('custom', '')).toThrow('invalid_stun_url')
  })

  it('creates a separate invitation for every guest without exposing host credentials', () => {
    const invitations = encodePeerInvites(
      room,
      [DEFAULT_STUN_URL, METERED_STUN_URL],
      'web|game|host',
      [{ actorId: 'player_123', actorName: '夜莺' }, {}],
    )

    expect(invitations).toHaveLength(2)
    expect(invitations[0].inviteCode.startsWith('DFP2-')).toBe(true)
    expect(invitations[0].inviteCode).not.toContain(room.host_token)
    expect(decodePeerInvite(invitations[0].inviteCode)).toMatchObject({
      version: 2,
      roomCode: room.room_code,
      hostPeerId: room.host_peer_id,
      peerId: room.invitations[0].peer_id,
      guestToken: room.invitations[0].token,
      gameKey: 'web|game|host',
      stunUrls: [DEFAULT_STUN_URL, METERED_STUN_URL],
      actorId: 'player_123',
      actorName: '夜莺',
    })
    expect(invitations[0]).toMatchObject({ actorId: 'player_123', actorName: '夜莺' })
    expect(decodePeerInvite(invitations[1].inviteCode)).toMatchObject({
      peerId: room.invitations[1].peer_id,
      guestToken: room.invitations[1].token,
    })
    expect(decodePeerInvite(invitations[1].inviteCode).actorId).toBeUndefined()
  })

  it('rejects malformed, oversized, and tampered invitations', () => {
    expect(() => decodePeerInvite('DFP2-not-base64-json')).toThrow('invalid_invite')
    expect(() => decodePeerInvite(`DFP2-${'a'.repeat(4096)}`)).toThrow('invalid_invite')

    const invitation = encodePeerInvites(room, [], 'web|game|host')[0].inviteCode
    const encoded = invitation.slice(5)
    const normalized = encoded.replaceAll('-', '+').replaceAll('_', '/')
    const payload = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')))
    payload.peerId = payload.hostPeerId
    expect(() => decodePeerInvite(encodePayload(payload))).toThrow('invalid_invite')
  })

  it('normalizes at most four valid STUN URIs', () => {
    expect(normalizeStunUrls(
      'stun:one.example.net:3478, stun:two.example.net:3478;stun:one.example.net:3478',
    )).toEqual(['stun:one.example.net:3478', 'stun:two.example.net:3478'])
    expect(() => normalizeStunUrls([
      'stun:1.example.net:3478',
      'stun:2.example.net:3478',
      'stun:3.example.net:3478',
      'stun:4.example.net:3478',
      'stun:5.example.net:3478',
    ])).toThrow('too_many_stun_urls')
    expect(() => normalizeStunUrls(['stun:broken.example.net:0'])).toThrow('invalid_stun_url')
  })
})
