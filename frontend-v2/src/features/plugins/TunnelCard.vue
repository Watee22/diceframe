<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NTag, NIcon } from 'naive-ui'
import { CopyOutline } from '@vicons/ionicons5'
import { useTunnel } from '@/composables/useTunnel'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useLocale } from '@/composables/useLocale'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'

const store = useSettingsStore()
const { t } = useLocale()
const toast = useToast()
const {
  status: tunnelStatus, starting: tunnelStarting, error: tunnelError,
  active: tunnelActive, providers: tunnelProviders, linkUpdated: tunnelLinkUpdated,
  enable: enableTunnel, stop: stopTunnel,
} = useTunnel()

const hasAccessPassword = computed(() => Boolean(store.config.access_password?.configured))

async function onTunnelEnable(pluginId: string) {
  if (!hasAccessPassword.value) { toast.error(t('tunnelNeedPassword')); return }
  await enableTunnel(pluginId)
  if (tunnelError.value) toast.error(tunnelError.value)
}
async function onTunnelStop(pluginId: string) {
  await stopTunnel(pluginId)
  if (tunnelError.value) toast.error(tunnelError.value)
}
async function onCopyTunnelLink() {
  const url = tunnelStatus.value?.url
  if (!url) return
  await copyToClipboard(url)
  toast.success(t('tunnelLinkCopied'))
}
</script>

<template>
  <section class="settings-group-card">
    <div v-if="!hasAccessPassword" class="form-row">
      <p class="form-hint">{{ t('tunnelNeedPassword') }}</p>
    </div>
    <div v-if="!tunnelProviders.length" class="form-row">
      <p class="form-hint">{{ t('tunnelNoProvider') }}</p>
    </div>
    <div v-for="p in tunnelProviders" :key="p.plugin_id" class="form-row">
      <label>{{ p.name }}</label>
      <div class="switch-inline">
        <NTag v-if="p.running" type="success" size="small">{{ t('tunnelActive') }}</NTag>
        <NTag v-else size="small">{{ t('tunnelIdle') }}</NTag>
        <NTag v-if="p.needs_core_update" type="warning" size="small">{{ t('pluginNeedsCoreUpdate', { version: p.min_app_version || '' }) }}</NTag>
        <NButton v-if="!tunnelActive" type="primary" size="small" :loading="tunnelStarting" :disabled="!hasAccessPassword" @click="onTunnelEnable(p.plugin_id)">{{ t('tunnelEnable') }}</NButton>
        <NButton v-else size="small" :loading="tunnelStarting" @click="onTunnelStop(p.plugin_id)">{{ t('tunnelStop') }}</NButton>
      </div>
    </div>
    <div v-if="tunnelStarting && !tunnelActive" class="form-row">
      <p class="muted">{{ t('tunnelStarting') }}</p>
    </div>
    <div v-if="tunnelActive && tunnelStatus?.url" class="form-row">
      <label>{{ t('tunnelActive') }}</label>
      <NInput :value="tunnelStatus.url" readonly />
      <div class="actions-row">
        <NButton @click="onCopyTunnelLink">
          <template #icon><NIcon :component="CopyOutline" /></template>
          {{ t('tunnelCopyLink') }}
        </NButton>
      </div>
      <p v-if="tunnelLinkUpdated" class="form-hint">{{ t('tunnelLinkUpdated') }}</p>
    </div>
    <div v-if="tunnelError" class="form-row">
      <p class="form-hint">{{ t('tunnelError') }}: {{ tunnelError }}</p>
    </div>
  </section>
</template>
