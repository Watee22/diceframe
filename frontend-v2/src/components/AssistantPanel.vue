<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NButton, NIcon, NInput } from 'naive-ui'
import {
  CloseOutline, DocumentTextOutline, RefreshOutline, SendOutline,
  SparklesOutline, StopCircleOutline, TrashOutline,
} from '@vicons/ionicons5'
import { useLocale } from '@/composables/useLocale'
import { useAssistant } from '@/composables/useAssistant'
import { renderSafeMarkdown } from '@/utils/markdown'

const emit = defineEmits<{ close: [] }>()
const { t, locale } = useLocale()
const { messages, streaming, send, stop, retryLast, clear } = useAssistant()
const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const quickQuestions = () => [
  t('assistantQuickLogs'),
  t('assistantQuickApi'),
  t('assistantQuickPlugin'),
  t('assistantQuickPlayers'),
  t('assistantQuickTunnel'),
]

function scrollToBottom() {
  void nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

watch(messages, scrollToBottom, { deep: true })

function renderMd(text: string): string {
  return renderSafeMarkdown(text)
}

async function onSubmit() {
  const value = draft.value.trim()
  if (!value || streaming.value) return
  draft.value = ''
  await send(value, locale.value)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void onSubmit()
  }
}

function ask(question: string) {
  if (streaming.value) return
  draft.value = question
  void onSubmit()
}
</script>

<template>
  <section class="assistant-panel" aria-labelledby="assistant-panel-title">
    <header class="assistant-panel-head">
      <span class="assistant-brand" aria-hidden="true"><NIcon :component="SparklesOutline" size="21" /></span>
      <div class="assistant-head-copy">
        <strong id="assistant-panel-title">{{ t('assistantTitle') }}</strong>
        <span>{{ t('assistantSubtitle') }}</span>
      </div>
      <NButton size="small" quaternary circle :title="t('assistantClear')" :disabled="!messages.length" @click="clear">
        <template #icon><NIcon :component="TrashOutline" /></template>
      </NButton>
      <NButton size="small" quaternary circle :title="t('close')" @click="emit('close')">
        <template #icon><NIcon :component="CloseOutline" /></template>
      </NButton>
    </header>

    <div ref="listEl" class="assistant-messages" aria-live="polite">
      <div v-if="!messages.length" class="assistant-empty">
        <span class="assistant-empty-icon"><NIcon :component="SparklesOutline" size="28" /></span>
        <strong>{{ t('assistantEmpty') }}</strong>
        <p>{{ t('assistantEmptyHint') }}</p>
        <div class="assistant-quick-grid">
          <button v-for="question in quickQuestions()" :key="question" type="button" @click="ask(question)">
            {{ question }}
          </button>
        </div>
        <small>{{ t('assistantVersionHint') }}</small>
        <small>{{ t('assistantLogPrivacyHint') }}</small>
      </div>

      <article
        v-for="(message, index) in messages"
        :key="index"
        class="assistant-message"
        :class="`assistant-message-${message.role}`"
      >
        <span v-if="message.role === 'assistant'" class="assistant-avatar" aria-hidden="true">
          <NIcon :component="SparklesOutline" />
        </span>
        <div class="assistant-message-stack">
          <div
            v-if="message.content || (streaming && index === messages.length - 1)"
            class="assistant-bubble"
            :class="message.role"
          >
            <span
              v-if="streaming && index === messages.length - 1 && !message.content"
              class="assistant-thinking"
            >
              <i /><i /><i /><span class="sr-only">{{ t('assistantThinking') }}</span>
            </span>
            <div v-else-if="message.role === 'assistant'" class="safe-markdown" v-html="renderMd(message.content)" />
            <span v-else>{{ message.content }}</span>
          </div>

          <details v-if="message.sources?.length" class="assistant-sources">
            <summary><NIcon :component="DocumentTextOutline" />{{ t('assistantSources') }}</summary>
            <ul>
              <li v-for="source in message.sources" :key="`${source.source}:${source.heading}`">
                <span>{{ source.heading }}</span>
              </li>
            </ul>
          </details>

          <div v-if="message.error || message.stopped" class="assistant-inline-state">
            <span>{{ message.error || t('assistantStopped') }}</span>
            <NButton
              v-if="index === messages.length - 1"
              size="tiny"
              quaternary
              @click="retryLast(locale)"
            >
              <template #icon><NIcon :component="RefreshOutline" /></template>
              {{ t('assistantRetry') }}
            </NButton>
          </div>
        </div>
      </article>
    </div>

    <footer class="assistant-composer">
      <NInput
        v-model:value="draft"
        type="textarea"
        :placeholder="t('assistantPlaceholder')"
        :autosize="{ minRows: 1, maxRows: 5 }"
        @keydown="onKeydown"
      />
      <NButton v-if="streaming" type="warning" class="assistant-send" @click="stop">
        <template #icon><NIcon :component="StopCircleOutline" /></template>
        {{ t('assistantStop') }}
      </NButton>
      <NButton v-else type="primary" class="assistant-send" :disabled="!draft.trim()" @click="onSubmit">
        <template #icon><NIcon :component="SendOutline" /></template>
        {{ t('assistantSend') }}
      </NButton>
      <span class="assistant-composer-hint">{{ t('assistantInputHint') }}</span>
    </footer>
  </section>
</template>

<style scoped>
.assistant-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  color: var(--df-text);
  background:
    radial-gradient(circle at 100% 0, color-mix(in srgb, var(--df-interactive) 12%, transparent), transparent 26%),
    var(--df-surface-1);
}

.assistant-panel-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 9px;
  padding: 14px 15px;
  border-bottom: 1px solid var(--df-border-soft);
  background: color-mix(in srgb, var(--df-surface-raised) 88%, transparent);
  backdrop-filter: blur(16px);
}

.assistant-brand,
.assistant-empty-icon,
.assistant-avatar {
  display: grid;
  place-items: center;
  color: var(--df-interactive-strong);
  border: 1px solid color-mix(in srgb, var(--df-interactive) 38%, var(--df-border-soft));
  background: color-mix(in srgb, var(--df-interactive) 10%, var(--df-control-bg));
}

.assistant-brand {
  width: 38px;
  height: 38px;
  border-radius: 12px;
}

.assistant-head-copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.assistant-head-copy strong {
  color: var(--df-accent-strong);
  font-size: 15px;
}

.assistant-head-copy span {
  overflow: hidden;
  color: var(--df-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-messages {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow-y: auto;
  flex-direction: column;
  gap: 14px;
  padding: 18px 15px;
  scroll-behavior: smooth;
}

.assistant-empty {
  display: grid;
  width: min(100%, 360px);
  margin: auto;
  justify-items: center;
  gap: 9px;
  padding: 24px 6px;
  text-align: center;
}

.assistant-empty-icon {
  width: 56px;
  height: 56px;
  margin-bottom: 4px;
  border-radius: 18px;
  box-shadow: var(--df-shadow);
}

.assistant-empty strong {
  color: var(--df-accent-strong);
  font-size: 17px;
}

.assistant-empty p,
.assistant-empty small {
  margin: 0;
  color: var(--df-text-muted);
  line-height: 1.6;
}

.assistant-quick-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 2px;
}

.assistant-quick-grid button {
  min-height: 54px;
  padding: 9px 10px;
  border: 1px solid var(--df-border-soft);
  border-radius: var(--df-radius-md);
  color: var(--df-text-secondary);
  background: color-mix(in srgb, var(--df-control-bg) 82%, transparent);
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
}

.assistant-quick-grid button:first-child {
  grid-column: 1 / -1;
  border-color: color-mix(in srgb, var(--df-accent) 46%, var(--df-border-soft));
  background: color-mix(in srgb, var(--df-accent) 10%, var(--df-control-bg));
}

.assistant-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.assistant-message-user {
  justify-content: flex-end;
}

.assistant-avatar {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  margin-top: 2px;
  border-radius: 9px;
}

.assistant-message-stack {
  display: grid;
  max-width: 88%;
  min-width: 0;
  gap: 6px;
}

.assistant-bubble {
  padding: 10px 12px;
  border: 1px solid var(--df-border-soft);
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.assistant-bubble.user {
  border-bottom-right-radius: 5px;
  border-color: color-mix(in srgb, var(--df-interactive) 50%, var(--df-border-soft));
  background: color-mix(in srgb, var(--df-interactive) 15%, var(--df-surface-raised));
  white-space: pre-wrap;
}

.assistant-bubble.assistant {
  border-top-left-radius: 5px;
  background: linear-gradient(155deg, var(--df-surface-raised), var(--df-surface-2));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04);
}

.assistant-thinking {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 20px;
}

.assistant-thinking i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--df-interactive-strong);
  animation: assistant-pulse 1s ease-in-out infinite;
}

.assistant-thinking i:nth-child(2) { animation-delay: .14s; }
.assistant-thinking i:nth-child(3) { animation-delay: .28s; }

@keyframes assistant-pulse {
  0%, 70%, 100% { opacity: .25; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-3px); }
}

.assistant-sources {
  color: var(--df-text-muted);
  font-size: 11px;
}

.assistant-sources summary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.assistant-sources ul {
  display: grid;
  gap: 5px;
  margin: 7px 0 0;
  padding: 8px 10px 8px 24px;
  border-left: 1px solid var(--df-border-soft);
}

.assistant-sources li span {
  display: block;
}

.assistant-inline-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid color-mix(in srgb, var(--df-danger) 38%, var(--df-border-soft));
  border-radius: var(--df-radius-sm);
  color: var(--df-danger-strong);
  background: color-mix(in srgb, var(--df-danger) 8%, transparent);
  font-size: 11px;
}

.assistant-composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
  padding: 12px 14px calc(10px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--df-border-soft);
  background: color-mix(in srgb, var(--df-surface-raised) 94%, transparent);
  box-shadow: 0 -12px 28px color-mix(in srgb, #000 10%, transparent);
}

.assistant-send {
  min-height: 36px;
}

.assistant-composer-hint {
  grid-column: 1 / -1;
  color: var(--df-text-muted);
  font-size: 10px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

@media (max-width: 420px) {
  .assistant-quick-grid { grid-template-columns: 1fr; }
  .assistant-message-stack { max-width: 92%; }
}
</style>
