import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf-8')
}

const assistantPanelSource = source('../src/components/AssistantPanel.vue')

describe('DF Assistant runtime log entry', () => {
  it('offers an explicit log check and explains external-model processing', () => {
    expect(assistantPanelSource).toContain("t('assistantQuickLogs')")
    expect(assistantPanelSource).toContain("t('assistantLogPrivacyHint')")
  })
})
