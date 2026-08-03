import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  clearPluginTheme: vi.fn(),
  toastSuccess: vi.fn(),
  toastWarning: vi.fn(),
  t: vi.fn((key: string) => key),
  pluginThemes: { value: [] as Array<{ plugin_id: string; id: string }> },
  pluginThemeId: { value: '' },
}))

vi.mock('../src/composables/useTheme', () => ({
  useTheme: () => ({
    pluginThemes: mocks.pluginThemes,
    pluginThemeId: mocks.pluginThemeId,
    clearPluginTheme: mocks.clearPluginTheme,
  }),
}))
vi.mock('../src/composables/useToast', () => ({
  useToast: () => ({ success: mocks.toastSuccess, warning: mocks.toastWarning }),
}))
vi.mock('../src/composables/useLocale', () => ({
  useLocale: () => ({ t: mocks.t }),
}))

import { usePluginUninstallCleanup } from '../src/features/plugins/usePluginUninstallCleanup'

describe('usePluginUninstallCleanup', () => {
  beforeEach(() => {
    mocks.clearPluginTheme.mockReset()
    mocks.toastSuccess.mockReset()
    mocks.toastWarning.mockReset()
    mocks.t.mockImplementation((key: string) => key)
    mocks.pluginThemes.value = [{ plugin_id: 'pack-a', id: 'theme-a' }]
    mocks.pluginThemeId.value = 'theme-a'
  })

  it('clears the active theme when its plugin is uninstalled', () => {
    const { onUninstalled } = usePluginUninstallCleanup()
    onUninstalled({ id: 'pack-a' } as never, {})
    expect(mocks.clearPluginTheme).toHaveBeenCalled()
  })

  it('does not clear theme when a different plugin is uninstalled', () => {
    mocks.pluginThemeId.value = 'theme-other'
    const { onUninstalled } = usePluginUninstallCleanup()
    onUninstalled({ id: 'pack-a' } as never, {})
    expect(mocks.clearPluginTheme).not.toHaveBeenCalled()
  })

  it('toasts cleanup counts and worlds_kept warnings', () => {
    const { onUninstalled } = usePluginUninstallCleanup()
    onUninstalled({ id: 'pack-a' } as never, {
      lorebook_removed: 3, cards_removed: 1, worlds_removed: 2, worlds_kept: ['w1'],
    })
    expect(mocks.toastSuccess).toHaveBeenCalled()
    expect(mocks.toastWarning).toHaveBeenCalled()
  })

  it('does not toast when nothing was cleaned', () => {
    const { onUninstalled } = usePluginUninstallCleanup()
    onUninstalled({ id: 'pack-a' } as never, {})
    expect(mocks.toastSuccess).not.toHaveBeenCalled()
    expect(mocks.toastWarning).not.toHaveBeenCalled()
  })
})
