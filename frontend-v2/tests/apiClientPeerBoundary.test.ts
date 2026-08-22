import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiBlob } from '@/api/client'
import {
  setActivePeerGameClient,
  type PeerRemoteGameClient,
} from '@/peer/game/bridge'

describe('API client peer boundary', () => {
  afterEach(() => {
    setActivePeerGameClient(null)
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('uses the ordinary HTTP path when no peer game is active', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true, transport: 'http' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api<{ transport: string }>('/games/local-game')).resolves.toEqual({
      ok: true,
      transport: 'http',
    })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/games/local-game')
  })

  it('leaves unrelated requests on HTTP even while a peer game is active', async () => {
    const tryApi = vi.fn().mockResolvedValue({ handled: false })
    setActivePeerGameClient({ tryApi } as unknown as PeerRemoteGameClient)
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api('/config')).resolves.toEqual({ ok: true })
    expect(tryApi).toHaveBeenCalledWith('/config', {})
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('keeps binary HTTP requests available outside peer games', async () => {
    // jsdom's Blob is not the same implementation used by Node's Response in CI.
    const response = new Response('image', {
      status: 200,
      headers: { 'Content-Type': 'image/png' },
    })
    const fetchMock = vi.fn().mockResolvedValue(response)
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiBlob('/assets/scene')).resolves.toBe(response)
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
