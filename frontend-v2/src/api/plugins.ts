import { api, apiBlob } from '@/api/client'
import type {
  PluginContentImportResponse,
  PluginContentResponse,
  PluginInfo,
  PluginMarketplaceResponse,
  PluginMirror,
  PluginMirrorsResponse,
  PluginMirrorTestResponse,
  PluginToolInvokeResponse,
  PluginToolsResponse,
  WorldListResponse,
} from '@/api/types'

export type PluginTypeInfo = {
  id: string
  level: string
  filterable: boolean
  filter_order: number
}

const pluginPath = (pluginId: string, suffix = '') =>
  `/plugins/${encodeURIComponent(pluginId)}${suffix}`

export const pluginApi = {
  list: () => api<{ plugins: PluginInfo[] }>('/plugins'),
  listTypes: () => api<{ ok: boolean; types: PluginTypeInfo[] }>('/plugins/types'),
  tools: () => api<PluginToolsResponse>('/plugins/tools'),
  invokeTool: (pluginId: string, toolName: string, argumentsValue: Record<string, unknown>) =>
    api<PluginToolInvokeResponse>(
      `/plugins/tools/${encodeURIComponent(pluginId)}/${encodeURIComponent(toolName)}`,
      { method: 'POST', body: JSON.stringify({ arguments: argumentsValue, context: {} }) },
    ),
  marketplace: () => api<PluginMarketplaceResponse>('/plugins/marketplace'),
  mirrors: () => api<PluginMirrorsResponse>('/plugins/mirrors'),
  content: () => api<PluginContentResponse>('/plugins/content'),
  worlds: () => api<WorldListResponse>('/worlds'),
  docs: (pluginId: string) => api<{ ok: boolean; found?: boolean; name?: string; content?: string; error?: string }>(
    pluginPath(pluginId, '/docs'),
  ),
  importAllContent: (pluginId: string, targetWorldId: string) =>
    api<{ ok: boolean; imported_count?: number; error_count?: number; error?: string }>(
      '/plugins/content/import-all',
      { method: 'POST', body: JSON.stringify({ plugin_id: pluginId, target_world_id: targetWorldId }) },
    ),
  exportContent: (payload: {
    plugin_id: string
    name: string
    version: string
    description: string
    world_id?: string
    card_ids?: string[]
    rule_id?: string
    flat?: boolean
  }) => apiBlob('/plugins/export', { method: 'POST', body: JSON.stringify(payload) }),
  updateConfig: (pluginId: string, payload: Record<string, unknown>) =>
    api(pluginPath(pluginId, '/config'), { method: 'PUT', body: JSON.stringify(payload) }),
  restart: (pluginId: string) => api(pluginPath(pluginId, '/restart'), { method: 'POST' }),
  clearCardCache: (pluginId: string) =>
    api<{ deleted?: number; bytes_deleted?: number }>(pluginPath(pluginId, '/card-cache/clear'), { method: 'POST' }),
  setRunning: (pluginId: string, running: boolean) =>
    api(pluginPath(pluginId, running ? '/start' : '/stop'), { method: 'POST' }),
  install: (body: FormData) => api('/plugins/install', { method: 'POST', body }),
  rescan: () => api('/plugins/rescan', { method: 'POST' }),
  installMarketplace: (pluginId: string, overwrite: boolean) =>
    api('/plugins/marketplace/install', {
      method: 'POST',
      body: JSON.stringify({ plugin_id: pluginId, overwrite }),
    }),
  update: (pluginId: string) => api(pluginPath(pluginId, '/update'), { method: 'POST' }),
  uninstall: (pluginId: string, deleteData = false) =>
    api<{ ok: boolean; uninstalled?: boolean; lorebook_removed?: number; cards_removed?: number; worlds_removed?: number; worlds_kept?: string[] }>(
      pluginPath(pluginId), { method: 'DELETE', body: JSON.stringify({ delete_data: deleteData }) },
    ),
  addMirror: (mirror: PluginMirror) =>
    api('/plugins/mirrors', { method: 'POST', body: JSON.stringify(mirror) }),
  updateMirror: (mirrorId: string, patch: Partial<PluginMirror>) =>
    api(`/plugins/mirrors/${encodeURIComponent(mirrorId)}`, {
      method: 'PUT',
      body: JSON.stringify(patch),
    }),
  deleteMirror: (mirrorId: string) =>
    api(`/plugins/mirrors/${encodeURIComponent(mirrorId)}`, { method: 'DELETE' }),
  testMirror: (mirrorId = '') =>
    api<PluginMirrorTestResponse>('/plugins/mirrors/test', {
      method: 'POST',
      body: JSON.stringify({ mirror_id: mirrorId }),
    }),
  importContent: (kind: string, itemId: unknown, pluginId: string, targetWorldId: string) =>
    api<PluginContentImportResponse>('/plugins/content/import', {
      method: 'POST',
      body: JSON.stringify({
        kind,
        id: itemId,
        plugin_id: pluginId,
        target_world_id: targetWorldId,
      }),
    }),
}
