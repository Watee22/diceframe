import { computed, onMounted, onUnmounted, ref } from 'vue'
import { systemApi } from '@/api/system'
import { pluginApi } from '@/api/plugins'
import type { TunnelStatus } from '@/api/types'

// 模块级单例状态：设置卡是唯一消费方，多实例共享同一份隧道状态。
const status = ref<TunnelStatus | null>(null)
const starting = ref(false)
const error = ref('')
const linkUpdated = ref(false)
let pollTimer: number | null = null
let lastUrl = ''

async function refresh() {
  try {
    status.value = await systemApi.getTunnelStatus()
    const newUrl = status.value?.url || ''
    if (newUrl && lastUrl && newUrl !== lastUrl) {
      linkUpdated.value = true
    }
    lastUrl = newUrl
  } catch {
    // 静默：状态卡保留上次值
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(refresh, 5000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function enable(pluginId: string) {
  starting.value = true
  error.value = ''
  linkUpdated.value = false
  try {
    const resp = await pluginApi.invokeTool(pluginId, 'tunnel_start', {})
    if (!resp.ok) {
      error.value = resp.error || ''
    } else {
      const r = resp.result as Record<string, unknown> | undefined
      if (r && r.error) error.value = String(r.error)
    }
    await refresh()
    startPolling()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}

async function stop(pluginId: string) {
  starting.value = true
  error.value = ''
  try {
    const resp = await pluginApi.invokeTool(pluginId, 'tunnel_stop', {})
    if (!resp.ok) error.value = resp.error || ''
    await refresh()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}

function dismissLinkUpdated() {
  linkUpdated.value = false
}

export function useTunnel() {
  onMounted(() => {
    refresh()
    startPolling()
  })
  onUnmounted(stopPolling)
  return {
    status,
    starting,
    error,
    linkUpdated,
    active: computed(() => Boolean(status.value?.active)),
    providers: computed(() => status.value?.providers ?? []),
    refresh,
    enable,
    stop,
    dismissLinkUpdated,
  }
}
