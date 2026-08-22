import { computed, markRaw, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  PeerHostGameBridge,
  PeerRemoteGameClient,
  setActivePeerGameClient,
  type PeerLocalApiExecutor,
} from '@/peer/game/bridge'
import type { PeerConnectionState } from '@/peer/protocol/signaling'
import { MultiPeerConnectionSession } from '@/peer/session/MultiPeerConnectionSession'

interface MultiStartOptions {
  isHost: boolean
  localPeerId: string
  token: string
  hostPeerId: string
  guestPeerIds: readonly string[]
  roomCode: string
  websocketUrl: string
  stunUrls: readonly string[]
  gameKey: string
  localApi?: PeerLocalApiExecutor
  /** host: 每个 guest peer 被明确分配的已有角色。 */
  guestActorIds?: Record<string, string>
  /** host: 会话期间已经完成的 peer -> 角色绑定，用于刷新恢复。 */
  boundActorIds?: Record<string, string>
  /** guest: 这枚邀请码指定的已有角色。 */
  assignedActorId?: string
}

/** localStorage 里可恢复的会话参数（刷新后自动重连用）。 */
interface PersistedPeerSession {
  isHost: boolean
  localPeerId: string
  token: string
  hostPeerId: string
  guestPeerIds: string[]
  roomCode: string
  websocketUrl: string
  stunUrls: string[]
  gameKey: string
  guestActorIds?: Record<string, string>
  boundActorIds?: Record<string, string>
  assignedActorId?: string
  savedAt: number
}

const PERSIST_KEY = 'diceframe_peer_session'
/** 4 小时后邀请码必然过期，不再尝试恢复。 */
const PERSIST_TTL_MS = 4 * 60 * 60 * 1000

function readPersisted(): PersistedPeerSession | null {
  try {
    const raw = localStorage.getItem(PERSIST_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as PersistedPeerSession
    if (!value || typeof value !== 'object' || !value.gameKey || !value.localPeerId) return null
    if (!Array.isArray(value.guestPeerIds) || !value.guestPeerIds.length) return null
    if (Date.now() - Number(value.savedAt || 0) > PERSIST_TTL_MS) return null
    return value
  } catch {
    return null
  }
}

function writePersisted(options: MultiStartOptions): void {
  const value: PersistedPeerSession = {
    isHost: options.isHost,
    localPeerId: options.localPeerId,
    token: options.token,
    hostPeerId: options.hostPeerId,
    guestPeerIds: [...options.guestPeerIds],
    roomCode: options.roomCode,
    websocketUrl: options.websocketUrl,
    stunUrls: [...options.stunUrls],
    gameKey: options.gameKey,
    guestActorIds: { ...(options.guestActorIds || {}) },
    boundActorIds: { ...(options.boundActorIds || {}) },
    assignedActorId: options.assignedActorId || '',
    savedAt: Date.now(),
  }
  try {
    localStorage.setItem(PERSIST_KEY, JSON.stringify(value))
  } catch {
    // 存储不可用：跳过持久化，仅本次会话可玩。
  }
}

function clearPersisted(): void {
  try {
    localStorage.removeItem(PERSIST_KEY)
  } catch {
    // 忽略
  }
}

export const usePeerSessionStore = defineStore('peer-session', () => {
  const state = ref<PeerConnectionState>('idle')
  const stateDetail = ref('')
  const roomCode = ref('')
  const peerStates = ref<Record<string, PeerConnectionState>>({})
  const gameKey = ref('')
  const isHost = ref(false)
  const actorId = ref('')
  let session: MultiPeerConnectionSession | null = null
  let remoteGameClient: PeerRemoteGameClient | null = null

  const connected = computed(() => state.value === 'connected')

  function updateState(next: PeerConnectionState, detail = ''): void {
    state.value = next
    stateDetail.value = detail
  }

  function stop(): void {
    setActivePeerGameClient(null)
    remoteGameClient = null
    session?.close()
    session = null
    if (state.value !== 'idle') updateState('closed')
    peerStates.value = {}
    gameKey.value = ''
    isHost.value = false
    actorId.value = ''
  }

  function reset(): void {
    stop()
    clearPersisted()
    state.value = 'idle'
    stateDetail.value = ''
    roomCode.value = ''
  }

  function startMulti(options: MultiStartOptions, localApi?: PeerLocalApiExecutor): void {
    stop()
    const executor = localApi ?? options.localApi
    const persistedOptions: MultiStartOptions = {
      ...options,
      guestActorIds: { ...(options.guestActorIds || {}) },
      boundActorIds: { ...(options.boundActorIds || {}) },
    }
    roomCode.value = options.roomCode
    gameKey.value = options.gameKey
    isHost.value = options.isHost
    peerStates.value = Object.fromEntries(
      (options.isHost ? options.guestPeerIds : [options.hostPeerId])
        .map(peerId => [peerId, 'waiting' as PeerConnectionState]),
    )
    const hostBridge = options.isHost
      ? new PeerHostGameBridge(
          options.gameKey,
          requiredLocalApi(executor),
          () => {
            session?.notifyGameChanged()
          },
          persistedOptions.guestActorIds,
          persistedOptions.boundActorIds,
          (peerId, nextActorId) => {
            persistedOptions.boundActorIds = {
              ...(persistedOptions.boundActorIds || {}),
              [peerId]: nextActorId,
            }
            writePersisted(persistedOptions)
          },
        )
      : null
    const next = new MultiPeerConnectionSession({
      ...options,
      onState: updateState,
      onPeerState(peerId, peerState) {
        peerStates.value = { ...peerStates.value, [peerId]: peerState }
      },
      onGameRequest: hostBridge
        ? (peerId, operation, payload) => hostBridge.handle(peerId, operation, payload)
        : undefined,
      onGameEvent() {
        remoteGameClient?.notifyStateChanged()
      },
    })
    session = markRaw(next)
    if (!options.isHost) {
      remoteGameClient = markRaw(new PeerRemoteGameClient(
        next,
        options.hostPeerId,
        options.gameKey,
        options.assignedActorId,
      ))
      actorId.value = remoteGameClient.userId
      setActivePeerGameClient(remoteGameClient)
    }
    writePersisted(persistedOptions)
    next.connect()
  }

  /** 刷新后恢复：读 localStorage 里的会话参数重建连接（guest 需先重绑身份）。 */
  function restore(localApi: PeerLocalApiExecutor): boolean {
    const saved = readPersisted()
    if (!saved || session) return false
    startMulti({
      isHost: saved.isHost,
      localPeerId: saved.localPeerId,
      token: saved.token,
      hostPeerId: saved.hostPeerId,
      guestPeerIds: saved.guestPeerIds,
      roomCode: saved.roomCode,
      websocketUrl: saved.websocketUrl,
      stunUrls: saved.stunUrls,
      gameKey: saved.gameKey,
      guestActorIds: saved.guestActorIds,
      boundActorIds: saved.boundActorIds,
      assignedActorId: saved.assignedActorId,
      localApi,
    }, localApi)
    return true
  }

  /** guest 重连后向 host 恢复原角色身份。 */
  async function rebindIdentity(): Promise<boolean> {
    if (!remoteGameClient) return false
    const rebound = await remoteGameClient.rebindIdentity()
    actorId.value = rebound ? remoteGameClient.userId : ''
    return rebound
  }

  function hasPersistedSession(): boolean {
    return readPersisted() !== null
  }

  return {
    state,
    stateDetail,
    roomCode,
    peerStates,
    gameKey,
    isHost,
    actorId,
    connected,
    updateState,
    startMulti,
    stop,
    reset,
    restore,
    rebindIdentity,
    hasPersistedSession,
  }
})

function requiredLocalApi(value: PeerLocalApiExecutor | undefined): PeerLocalApiExecutor {
  if (!value) throw new Error('host_game_api_required')
  return value
}
