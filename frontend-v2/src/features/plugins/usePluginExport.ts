import { computed, ref, type Ref } from 'vue'
import { api, errorMessage } from '@/api/client'
import { pluginApi } from '@/api/plugins'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import type { CharacterCard, RuleSummary, WorldListResponse } from '@/api/types'

export function usePluginExport(busy: Ref<string>) {
  const toast = useToast()
  const { t } = useLocale()
  const worlds = ref<WorldListResponse['worlds']>([])
  const cards = ref<CharacterCard[]>([])
  const rules = ref<RuleSummary[]>([])
  const loading = ref(false)
  const packId = ref('')
  const packName = ref('')
  const packVersion = ref('0.1.0')
  const packDescription = ref('')
  const selectedWorldId = ref('')
  const selectedRuleId = ref('')
  const selectedCardIds = ref<string[]>([])

  const worldOptions = computed(() => (worlds.value || []).map(world => {
    const id = String(world?.id || world?.world_id || '')
    return { label: String(world?.name || world?.world_name || id), value: id }
  }).filter(item => item.value))
  const ruleOptions = computed(() => rules.value.map(rule => ({
    label: String(rule.rule_name || rule.rule_id),
    value: rule.rule_id,
  })))
  const cardOptions = computed(() => cards.value.map(card => ({
    label: String(card.character_name || card.id || t('unnamed')),
    value: String(card.id || ''),
  })).filter(item => item.value))

  async function loadAuthorData() {
    loading.value = true
    try {
      const [worldRes, cardRes, ruleRes] = await Promise.all([
        pluginApi.worlds(),
        api<{ cards: CharacterCard[] }>('/character-cards'),
        api<{ rules: RuleSummary[] }>('/rules'),
      ])
      worlds.value = worldRes.worlds || []
      cards.value = cardRes.cards || []
      rules.value = ruleRes.rules || []
    } catch (error: unknown) {
      toast.error(errorMessage(error))
    } finally {
      loading.value = false
    }
  }

  async function exportPack(flat = false) {
    if (!packId.value.trim() || !packName.value.trim()) {
      toast.error(t('exportPackNeedIdName'))
      return
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(packId.value.trim())) {
      toast.error(t('exportPackIdInvalid'))
      return
    }
    if (!selectedWorldId.value && !selectedRuleId.value && selectedCardIds.value.length === 0) {
      toast.error(t('exportPackNeedContent'))
      return
    }
    busy.value = 'export-pack'
    try {
      const response = await pluginApi.exportContent({
        plugin_id: packId.value.trim(),
        name: packName.value.trim(),
        version: packVersion.value.trim() || '0.1.0',
        description: packDescription.value.trim(),
        world_id: selectedWorldId.value,
        card_ids: selectedCardIds.value,
        rule_id: selectedRuleId.value,
        flat,
      })
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match?.[1] || `${packId.value}.dfplugin`
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success(t('exportPackDone', { filename }))
    } catch (error: unknown) {
      toast.error(errorMessage(error))
    } finally {
      busy.value = ''
    }
  }

  return {
    worlds, cards, rules, loading,
    packId, packName, packVersion, packDescription,
    selectedWorldId, selectedRuleId, selectedCardIds,
    worldOptions, ruleOptions, cardOptions,
    loadAuthorData, exportPack,
  }
}
