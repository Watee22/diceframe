import { ref } from 'vue'

// 浏览器本地语音朗读封装。零后端、零依赖，用 window.speechSynthesis。
// 不支持时所有方法静默降级，调用方无需感知。

export interface SpeakOptions {
  lang?: string
  rate?: number
  pitch?: number
  onEnd?: () => void
}

const RATE_STORAGE_KEY = 'trpg_tts_rate'
export const DEFAULT_TTS_RATE = 1.0

// 读取语速偏好（0.5–5.0），localStorage 存字符串。
export function ttsRate(): number {
  try {
    const raw = Number(localStorage.getItem(RATE_STORAGE_KEY))
    if (Number.isFinite(raw) && raw >= 0.5 && raw <= 5) return raw
  } catch { /* localStorage 不可用时用默认 */ }
  return DEFAULT_TTS_RATE
}

export function setTtsRate(rate: number): void {
  const clamped = Math.min(5, Math.max(0.5, Number(rate) || DEFAULT_TTS_RATE))
  try { localStorage.setItem(RATE_STORAGE_KEY, String(clamped)) } catch { /* 忽略 */ }
}

let voices: SpeechSynthesisVoice[] = []

function loadVoices(): void {
  if (!('speechSynthesis' in window)) return
  voices = window.speechSynthesis.getVoices()
}

if (typeof window !== 'undefined') {
  loadVoices()
  // Chrome 在语音列表异步加载时会先返回空数组，监听事件补一次。
  if ('speechSynthesis' in window) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      voices = window.speechSynthesis.getVoices()
    })
  }
}

export function ttsSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function pickVoice(lang: string): SpeechSynthesisVoice | null {
  const normalized = lang.toLowerCase()
  const preferred = voices.find(voice => voice.lang.toLowerCase().replace('_', '-').startsWith(normalized))
  if (preferred) return preferred
  return null
}

// 当前正在朗读的内容标识，用于单声道（播新的停旧的）。
export const speakingKey = ref<string>('')

// 剥离 HTML 标签并解码实体，得到纯文本供朗读。GM 叙事段落由
// renderer 高亮关键词时包了 <span class="...">，朗读前必须还原。
export function stripHtml(text: string): string {
  const raw = String(text || '')
  if (!raw.includes('<') && !raw.includes('&')) return raw
  return raw
    .replace(/<[^>]+>/g, '')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .trim()
}

export function ttsSpeak(text: string, key: string, options: SpeakOptions = {}): void {
  if (!ttsSupported() || !text.trim()) return
  const synth = window.speechSynthesis
  synth.cancel()
  speakingKey.value = key
  const utterance = new SpeechSynthesisUtterance(stripHtml(text))
  const voice = pickVoice(options.lang || 'zh-CN')
  if (voice) utterance.voice = voice
  utterance.lang = voice?.lang || options.lang || 'zh-CN'
  utterance.rate = options.rate ?? ttsRate()
  utterance.pitch = options.pitch ?? 1
  utterance.onend = () => {
    if (speakingKey.value === key) speakingKey.value = ''
    options.onEnd?.()
  }
  utterance.onerror = () => {
    if (speakingKey.value === key) speakingKey.value = ''
    options.onEnd?.()
  }
  synth.speak(utterance)
}

export function ttsStop(): void {
  if (!ttsSupported()) return
  window.speechSynthesis.cancel()
  speakingKey.value = ''
}

export function ttsToggle(text: string, key: string, options: SpeakOptions = {}): void {
  if (speakingKey.value === key) {
    ttsStop()
  } else {
    ttsSpeak(text, key, options)
  }
}
