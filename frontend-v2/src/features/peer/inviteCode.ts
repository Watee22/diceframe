import type { RendezvousRoomResponse } from '@/api/types'

export const DEFAULT_STUN_URL = 'stun:stun.cloudflare.com:3478'
export const METERED_STUN_URL = 'stun:stun.relay.metered.ca:80'
export const NEXTCLOUD_STUN_URL = 'stun:stun.nextcloud.com:443'
export const MAX_STUN_URLS = 4
const MAX_INVITE_CODE_LENGTH = 4096

export type StunPresetId = 'cloudflare' | 'metered' | 'nextcloud' | 'multi' | 'none' | 'custom'

export interface StunPreset {
  id: StunPresetId
  urls: readonly string[]
  thirdParty: boolean
}

export const STUN_PRESETS: readonly StunPreset[] = [
  { id: 'cloudflare', urls: [DEFAULT_STUN_URL], thirdParty: true },
  { id: 'metered', urls: [METERED_STUN_URL], thirdParty: true },
  { id: 'nextcloud', urls: [NEXTCLOUD_STUN_URL], thirdParty: true },
  {
    id: 'multi',
    urls: [DEFAULT_STUN_URL, METERED_STUN_URL, NEXTCLOUD_STUN_URL],
    thirdParty: true,
  },
  { id: 'none', urls: [], thirdParty: false },
  { id: 'custom', urls: [], thirdParty: true },
]

export function stunUrlsForPreset(preset: StunPresetId, customUrls = ''): string[] {
  if (preset === 'custom') {
    const normalized = normalizeStunUrls(customUrls)
    if (!normalized.length) throw new Error('invalid_stun_url')
    return normalized
  }
  const urls = STUN_PRESETS.find(item => item.id === preset)?.urls
  return [...(urls ?? [DEFAULT_STUN_URL])]
}

export interface PeerInvite {
  version: 2
  roomCode: string
  peerId: string
  hostPeerId: string
  guestToken: string
  gameKey: string
  websocketUrl: string
  stunUrl: string
  stunUrls: string[]
  expiresAt: string
  /** 房主为这枚一次性邀请指定的已有玩家身份；留空表示创建新玩家。 */
  actorId?: string
  actorName?: string
}

export interface EncodedPeerInvite {
  peerId: string
  inviteCode: string
  actorId?: string
  actorName?: string
}

export interface PeerInviteTarget {
  actorId?: string
  actorName?: string
}

function encodeBase64Url(value: string): string {
  const bytes = new TextEncoder().encode(value)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/u, '')
}

function decodeBase64Url(value: string): string {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/')
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
  const binary = atob(padded)
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

function validWebSocketUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (url.protocol === 'wss:' || url.protocol === 'ws:')
      && !url.username && !url.password && !url.search && !url.hash
  } catch {
    return false
  }
}

function validStunUrl(value: string): boolean {
  if (value === '') return true
  if (value.length > 300) return false
  const match = /^stuns?:(?:\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::(\d{1,5}))?$/iu.exec(value)
  if (!match) return false
  if (match[1] === undefined) return true
  const port = Number(match[1])
  return port >= 1 && port <= 65535
}

export function normalizeStunUrl(value: string): string {
  const normalized = value.trim()
  if (!validStunUrl(normalized)) throw new Error('invalid_stun_url')
  return normalized
}

export function normalizeStunUrls(value: string | readonly string[]): string[] {
  const candidates = (typeof value === 'string' ? [value] : value)
    .flatMap(item => item.split(/[\s,;]+/u))
    .filter(Boolean)
  if (candidates.length > MAX_STUN_URLS) throw new Error('too_many_stun_urls')

  const normalized: string[] = []
  for (const candidate of candidates) {
    const url = normalizeStunUrl(candidate)
    if (url && !normalized.includes(url)) normalized.push(url)
  }
  return normalized
}

export function encodePeerInvites(
  room: RendezvousRoomResponse,
  stunUrls: string | readonly string[],
  gameKey: string,
  targets: readonly PeerInviteTarget[] = [],
): EncodedPeerInvite[] {
  const normalizedGameKey = gameKey.trim()
  if (!normalizedGameKey || normalizedGameKey.length > 512) throw new Error('invalid_game_key')
  const normalizedStunUrls = normalizeStunUrls(stunUrls)
  return room.invitations.map((invitation, index) => {
    const target = targets[index] || {}
    const actorId = String(target.actorId || '').trim()
    const actorName = String(target.actorName || '').trim()
    if (actorId.length > 128 || actorName.length > 200) throw new Error('invalid_invite_target')
    return {
      peerId: invitation.peer_id,
      actorId: actorId || undefined,
      actorName: actorName || undefined,
      inviteCode: `DFP2-${encodeBase64Url(JSON.stringify({
      version: 2,
      roomCode: room.room_code,
      peerId: invitation.peer_id,
      hostPeerId: room.host_peer_id,
      guestToken: invitation.token,
      gameKey: normalizedGameKey,
      websocketUrl: room.websocket_url,
      stunUrl: normalizedStunUrls[0] ?? '',
      stunUrls: normalizedStunUrls,
      expiresAt: room.expires_at,
      actorId: actorId || undefined,
      actorName: actorName || undefined,
    } satisfies PeerInvite))}`,
    }
  })
}

export function decodePeerInvite(value: string): PeerInvite {
  const compact = value.trim()
  if (!compact.startsWith('DFP2-') || compact.length > MAX_INVITE_CODE_LENGTH) {
    throw new Error('invalid_invite')
  }
  let candidate: unknown
  try {
    candidate = JSON.parse(decodeBase64Url(compact.slice(5)))
  } catch {
    throw new Error('invalid_invite')
  }
  if (!candidate || typeof candidate !== 'object') throw new Error('invalid_invite')
  const invite = candidate as Partial<PeerInvite>
  const validPeerId = (peerId: unknown, prefix: 'h' | 'p') => (
    typeof peerId === 'string'
    && new RegExp(`^${prefix}_[A-Za-z0-9_-]{8,64}$`, 'u').test(peerId)
  )
  if (
    invite.version !== 2
    || typeof invite.roomCode !== 'string'
    || !/^[A-Z0-9]{8}$/u.test(invite.roomCode)
    || !validPeerId(invite.peerId, 'p')
    || !validPeerId(invite.hostPeerId, 'h')
    || typeof invite.guestToken !== 'string'
    || invite.guestToken.length < 32
    || invite.guestToken.length > 256
    || typeof invite.gameKey !== 'string'
    || !invite.gameKey.trim()
    || invite.gameKey.length > 512
    || typeof invite.websocketUrl !== 'string'
    || invite.websocketUrl.length > 2048
    || !validWebSocketUrl(invite.websocketUrl)
    || typeof invite.stunUrl !== 'string'
    || !validStunUrl(invite.stunUrl)
    || !Array.isArray(invite.stunUrls)
    || invite.stunUrls.some(url => typeof url !== 'string')
    || typeof invite.expiresAt !== 'string'
    || invite.expiresAt.length > 64
    || !Number.isFinite(Date.parse(invite.expiresAt))
    || (invite.actorId !== undefined && (
      typeof invite.actorId !== 'string'
      || !invite.actorId.trim()
      || invite.actorId.length > 128
    ))
    || (invite.actorName !== undefined && (
      typeof invite.actorName !== 'string'
      || !invite.actorName.trim()
      || invite.actorName.length > 200
    ))
  ) {
    throw new Error('invalid_invite')
  }
  let stunUrls: string[]
  try {
    stunUrls = normalizeStunUrls(invite.stunUrls as string[])
    if (
      stunUrls.length !== invite.stunUrls.length
      || (stunUrls[0] ?? '') !== invite.stunUrl
    ) {
      throw new Error('invalid_stun_urls')
    }
  } catch {
    throw new Error('invalid_invite')
  }
  return { ...(invite as PeerInvite), stunUrls }
}
