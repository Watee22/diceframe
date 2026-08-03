import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'
import type { PluginInfo } from '@/api/types'

type UninstallResult = {
  lorebook_removed?: number
  cards_removed?: number
  worlds_removed?: number
  worlds_kept?: string[]
}

type UninstallCleanupHandler = (plugin: PluginInfo, result: UninstallResult) => void

/**
 * 插件卸载后的前端残留清理。
 *
 * 各功能域把自己的清理 handler 注册进 handlers 数组；新增插件类型若在前端留下
 * 状态（如 localStorage、CSS 变量），在此追加一个 handler 即可，无需改
 * PluginSettings 的 onUninstalled 调用点。后端数据清理由 descriptor 的 cleanup
 * 域驱动（见 support.py）。
 */
export function usePluginUninstallCleanup() {
  const { t } = useLocale()
  const toast = useToast()
  const { pluginThemes, pluginThemeId, clearPluginTheme } = useTheme()

  const handlers: UninstallCleanupHandler[] = [
    // 主题：卸载的插件若正在用其主题，清除引用与已应用的 CSS 变量
    (plugin) => {
      const theme = pluginThemes.value.find(item => item.plugin_id === plugin.id)
      if (theme && pluginThemeId.value === theme.id) clearPluginTheme()
    },
  ]

  function onUninstalled(plugin: PluginInfo, result: UninstallResult) {
    for (const handler of handlers) handler(plugin, result)
    // 清理结果提示（数据计数 + 保留世界警告）
    if (result.lorebook_removed || result.cards_removed || result.worlds_removed) {
      toast.success(t('pluginUninstallCleaned', {
        entries: result.lorebook_removed || 0,
        cards: result.cards_removed || 0,
        worlds: result.worlds_removed || 0,
      }))
    }
    if (result.worlds_kept?.length) {
      toast.warning(t('pluginUninstallWorldsKept', { count: result.worlds_kept.length }))
    }
  }

  return { onUninstalled }
}
