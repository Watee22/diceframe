import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { isSettingsSectionAvailable, normalizeSettingsSection } from '../src/utils/settingsSections'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf-8')
}

const settingsSource = source('../src/features/admin/SettingsView.vue')
const settingsCss = source('../src/styles/v2/settings-ai-management.css')

describe('settings section links', () => {
  it('keeps old vector-memory links working after merging the page', () => {
    expect(normalizeSettingsSection('memory')).toBe('models')
  })

  it('accepts current sections and ignores unknown targets', () => {
    expect(normalizeSettingsSection('api')).toBe('api')
    expect(normalizeSettingsSection('connection')).toBe('connection')
    expect(normalizeSettingsSection('models')).toBe('models')
    expect(normalizeSettingsSection('missing')).toBeNull()
  })

  it('only exposes backend connections in standalone frontends', () => {
    expect(isSettingsSectionAvailable('connection', true)).toBe(true)
    expect(isSettingsSectionAvailable('connection', false)).toBe(false)
    expect(isSettingsSectionAvailable('api', false)).toBe(true)
    expect(settingsSource).toContain('v-if="standaloneFrontend" v-show="section === \'connection\'"')
  })

  it('auto-saves model feature switches through the shared model routing save path', () => {
    expect(settingsSource).toContain('async function setModelRoutingBool')
    expect(settingsSource.match(/@update:value="setModelRoutingBool\('/g)).toHaveLength(5)
    expect(settingsSource).toContain('class="model-routing-save" type="success"')
  })

  it('draws one focus ring around provider and model catalog searches', () => {
    expect(settingsCss).toContain('.provider-search-box input:focus-visible')
    expect(settingsCss).toContain('.provider-catalog-search input:focus-visible')
    expect(settingsCss).toMatch(/\.provider-catalog-search input:focus-visible\s*\{[\s\S]*?box-shadow: none;/)
  })

  it('treats browser and Edge TTS as built-in speech engines', () => {
    expect(settingsSource).toContain("const ttsBuiltIn = ttsMode === 'browser' || ttsMode === 'edge-tts'")
    expect(settingsSource).toContain("value: speechReady ? t('statusComplete') : speechPartial ? t('statusPartial') : t('statusNeedsSetup')")
  })

  it('places contribution links in the About settings page', () => {
    expect(settingsSource).toContain('https://github.com/diceframe/diceframe/blob/main/CONTRIBUTING.md')
    expect(settingsSource).toContain('https://github.com/diceframe/diceframe/graphs/contributors')
    expect(settingsSource).toContain("t('contributingGuide')")
    expect(settingsSource).toContain("t('contributors')")
  })

  it('manages retained runtime logs without conflating them with game history', () => {
    expect(settingsSource).toContain("api<RuntimeLogStatus>('/system/runtime-logs')")
    expect(settingsSource).toContain("api<RuntimeLogStatus>('/system/runtime-logs/clear', { method: 'POST' })")
    expect(settingsSource).toContain("t('runtimeLogsRetention'")
    expect(settingsSource).toContain('class="advanced-section runtime-logs-section"')
    expect(settingsSource).toContain('class="advanced-section test-timeout-section"')
  })

  it('lays out About links four per row on desktop', () => {
    const polishCss = source('../src/styles/v2/settings-polish.css')
    const responsiveCss = source('../src/styles/v2/play-panels.css')
    expect(polishCss).toMatch(/\.about-links\s*\{[\s\S]*?grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/)
    expect(responsiveCss).toMatch(/\.about-detail-grid,\s+\.about-links\s*\{[\s\S]*?grid-template-columns: minmax\(0, 1fr\);/)
  })
})
