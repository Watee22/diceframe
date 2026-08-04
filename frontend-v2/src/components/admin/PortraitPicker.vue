<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CharacterPortrait } from '@/api/types'
import { uploadAvatar } from '@/api/avatars'
import { builtinPortraits, builtinRule, resolveBuiltinPortrait } from '@/utils/portraits'
import type { MessageKey } from '@/i18n'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import PortraitImage from '@/components/PortraitImage.vue'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps<{ modelValue?: CharacterPortrait; ruleId?: string; seed?: string; name?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: CharacterPortrait | undefined] }>()
const { t } = useLocale()
const toast = useToast()
const input = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const allOpen = ref(false)
const choices = computed(() => builtinPortraits(props.ruleId))
const resolvedId = computed(() => resolveBuiltinPortrait(props.modelValue, props.ruleId, props.seed || props.name).id)

const RULE_LABEL_KEYS: Record<string, MessageKey> = {
  dnd5e: 'ruleNameDnd5e',
  freeform_coc: 'ruleNameCoc',
  freeform_cyberpunk: 'ruleNameCyberpunk',
  freeform_fantasy: 'ruleNameFantasy',
  freeform_wuxia: 'ruleNameWuxia',
  tavern_free: 'ruleNameTavern',
}
const ALL_RULE_IDS = ['dnd5e', 'freeform_coc', 'freeform_cyberpunk', 'freeform_fantasy', 'freeform_wuxia', 'tavern_free']

function ruleLabel(ruleId: string): string {
  return t(RULE_LABEL_KEYS[ruleId] || 'ruleNameFantasy')
}

const allGroups = computed(() => {
  const current = builtinRule(props.ruleId)
  const groups = ALL_RULE_IDS.map(ruleId => ({
    ruleId,
    label: ruleLabel(ruleId),
    current: ruleId === current,
    portraits: builtinPortraits(ruleId),
  }))
  return [...groups].sort((a, b) => Number(b.current) - Number(a.current))
})

function choose(id: string) { emit('update:modelValue', { kind: 'builtin', id }) }

function chooseAll(ruleId: string, index: number) {
  emit('update:modelValue', { kind: 'builtin', id: `${ruleId}:${index}` })
  allOpen.value = false
}

async function onUpload(event: Event) {
  const element = event.target as HTMLInputElement
  const file = element.files?.[0]
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    toast.error(t('avatarFormatHint'))
    element.value = ''
    return
  }
  if (file.size > 3 * 1024 * 1024) {
    toast.error(t('avatarSizeHint'))
    element.value = ''
    return
  }
  uploading.value = true
  try {
    emit('update:modelValue', await uploadAvatar(file))
    toast.success(t('avatarUploaded'))
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : String(error))
  } finally {
    uploading.value = false
    element.value = ''
  }
}
</script>

<template>
  <section class="portrait-picker">
    <div class="portrait-picker-head">
      <div><strong>{{ t('characterAvatar') }}</strong><small>{{ t('avatarHelp') }}</small></div>
      <PortraitImage :portrait="modelValue" :rule-id="ruleId" :seed="seed" :name="name" :size="64" />
    </div>
    <div class="portrait-options">
      <button
        v-for="choice in choices"
        :key="choice.id"
        type="button"
        class="portrait-option"
        :class="{ selected: modelValue?.kind === 'builtin' ? modelValue.id === choice.id : resolvedId === choice.id }"
        :title="t('builtinAvatarOption', { index: choice.index + 1 })"
        @click="choose(choice.id)"
      >
        <PortraitImage :portrait="{ kind: 'builtin', id: choice.id }" :rule-id="ruleId" :name="name" :size="52" />
      </button>
      <button type="button" class="portrait-upload" :disabled="uploading" @click="input?.click()">
        {{ uploading ? t('uploading') : t('uploadCustomAvatar') }}
      </button>
      <button type="button" class="portrait-all" @click="allOpen = true">{{ t('allAvatars') }}</button>
      <button type="button" class="ghost portrait-auto" @click="emit('update:modelValue', undefined)">{{ t('useDefaultAvatar') }}</button>
    </div>
    <input ref="input" hidden type="file" accept="image/png,image/jpeg,image/webp" @change="onUpload">
    <small class="form-hint">{{ t('avatarUploadHint') }}</small>

    <Modal v-if="allOpen" :title="t('allAvatars')" @close="allOpen = false">
      <div v-for="group in allGroups" :key="group.ruleId" class="portrait-all-group" :class="{ current: group.current }">
        <div class="portrait-all-head">
          <strong>{{ group.label }}</strong>
          <small v-if="group.current" class="muted">{{ t('currentRule') }}</small>
        </div>
        <div class="portrait-options">
          <button
            v-for="p in group.portraits"
            :key="p.id"
            type="button"
            class="portrait-option"
            :class="{ selected: modelValue?.kind === 'builtin' ? modelValue.id === p.id : resolvedId === p.id }"
            :title="group.label + ' · ' + t('builtinAvatarOption', { index: p.index + 1 })"
            @click="chooseAll(group.ruleId, p.index)"
          >
            <PortraitImage :portrait="{ kind: 'builtin', id: p.id }" :rule-id="group.ruleId" :name="name" :size="52" />
          </button>
        </div>
      </div>
    </Modal>
  </section>
</template>