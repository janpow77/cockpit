<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, ChevronDown, Copy, RotateCcw, Send, Square } from 'lucide-vue-next'
import { listChatModels, streamChat } from '../api/chat'
import { extractError } from '../api/client'
import type { ChatModel, ChatStreamChunk } from '../api/types'
import { useToastStore } from '../stores/toast'

const STORAGE_KEY = 'cockpit.chat.v1'

interface ChatStats {
  evalCount: number | null
  evalDurationMs: number | null
  promptEvalCount: number | null
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string
  model?: string
  stats?: ChatStats
  status?: 'streaming' | 'done' | 'aborted' | 'error'
  error?: string
}

interface PersistedChat {
  messages: ChatMessage[]
  model: string
  temperature: number
  systemPrompt: string
}

const examples = [
  'Fasse die 12-Uhr-Regel des KPAnG in drei Sätzen zusammen',
  'Erkläre den Unterschied zwischen TER und RER',
  'Schreibe einen kurzen Vermerk-Absatz zur Stichprobenauswahl',
  'Welche BSI-Maßnahmen gelten für ein Behördenportal?',
]

const toast = useToastStore()
const messages = ref<ChatMessage[]>([])
const models = ref<ChatModel[]>([])
const selectedModel = ref('')
const temperature = ref(0.7)
const systemPrompt = ref('')
const routerAddress = ref('–')
const routerOk = ref(false)
const modelsLoading = ref(true)
const modelsError = ref<string | null>(null)
const systemOpen = ref(false)
const input = ref('')
const streaming = ref(false)
const inputElement = ref<HTMLTextAreaElement | null>(null)
const historyElement = ref<HTMLElement | null>(null)
const autoScroll = ref(true)
let abortController: AbortController | null = null
let hasStoredSystem = false
let hasStoredModel = false

const canSend = computed(() => input.value.trim().length > 0 && selectedModel.value.length > 0)

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!isRecord(value)) return false
  return typeof value.id === 'string'
    && (value.role === 'user' || value.role === 'assistant')
    && typeof value.content === 'string'
    && typeof value.createdAt === 'string'
}

function restoreChat(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const stored: unknown = JSON.parse(raw)
    if (!isRecord(stored)) return
    if (Array.isArray(stored.messages)) {
      messages.value = stored.messages.filter(isChatMessage).map((message) => (
        message.status === 'streaming' ? { ...message, status: 'aborted' } : message
      ))
    }
    if (typeof stored.model === 'string') {
      selectedModel.value = stored.model
      hasStoredModel = stored.model.length > 0
    }
    if (typeof stored.temperature === 'number' && stored.temperature >= 0 && stored.temperature <= 1.5) {
      temperature.value = stored.temperature
    }
    if (typeof stored.systemPrompt === 'string') {
      systemPrompt.value = stored.systemPrompt
      hasStoredSystem = true
    }
  } catch {
    // Beschädigte lokale Daten verhindern den Start nicht.
  }
}

function persistChat(): void {
  try {
    const payload: PersistedChat = {
      messages: messages.value,
      model: selectedModel.value,
      temperature: temperature.value,
      systemPrompt: systemPrompt.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Inkognito- und Speicherfehler bleiben ohne Einfluss auf den Chat.
  }
}

async function loadModels(): Promise<void> {
  modelsLoading.value = true
  try {
    const response = await listChatModels()
    models.value = response.models
    routerAddress.value = response.router
    routerOk.value = response.router_ok
    if (!hasStoredSystem) systemPrompt.value = response.system

    const storedExists = response.models.some((model) => model.tag === selectedModel.value)
    if (!hasStoredModel || !storedExists) {
      selectedModel.value = response.models.find((model) => model.tag.startsWith('qwen3.8'))?.tag
        ?? response.models[0]?.tag
        ?? ''
    }
    modelsError.value = response.models.length ? null : 'Keine Modelle verfügbar.'
  } catch (error) {
    modelsError.value = extractError(error)
    routerOk.value = false
    toast.error(`Modelle konnten nicht geladen werden: ${modelsError.value}`)
  } finally {
    modelsLoading.value = false
  }
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' }).format(date)
}

function formatTemperature(value: number): string {
  return value.toFixed(1).replace('.', ',')
}

function formatDuration(ms: number | null | undefined): string {
  return ms == null ? '–' : `${(ms / 1000).toFixed(1).replace('.', ',')} s`
}

function tokensPerSecond(stats: ChatStats | undefined): string {
  if (!stats?.evalCount || !stats.evalDurationMs) return '–'
  return (stats.evalCount / (stats.evalDurationMs / 1000)).toFixed(1).replace('.', ',')
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function renderInline(value: string): string {
  const codeParts: string[] = []
  let html = escapeHtml(value).replace(/`([^`\n]+)`/g, (_match, code: string) => {
    const index = codeParts.push(`<code>${code}</code>`) - 1
    return `\u0000INLINE${index}\u0000`
  })
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  return html.replace(/\u0000INLINE(\d+)\u0000/g, (_match, index: string) => codeParts[Number(index)] ?? '')
}

function renderTextBlock(value: string): string {
  const lines = value.split('\n')
  const output: string[] = []
  let listType: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (listType) output.push(`</${listType}>`)
    listType = null
  }

  for (const line of lines) {
    const unordered = line.match(/^\s*-\s+(.+)$/)
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    const nextType = unordered ? 'ul' : ordered ? 'ol' : null
    if (nextType) {
      if (listType !== nextType) {
        closeList()
        output.push(`<${nextType}>`)
        listType = nextType
      }
      output.push(`<li>${renderInline((unordered?.[1] ?? ordered?.[1]) ?? '')}</li>`)
    } else {
      closeList()
      output.push(line ? `${renderInline(line)}<br>` : '<br>')
    }
  }
  closeList()
  return output.join('\n')
}

function markdownLight(value: string): string {
  const parts = value.split(/```/)
  return parts.map((part, index) => {
    if (index % 2 === 0) return renderTextBlock(part)
    const firstBreak = part.indexOf('\n')
    const possibleLanguage = firstBreak >= 0 ? part.slice(0, firstBreak).trim() : ''
    const hasLanguage = /^[a-zA-Z0-9_+#.-]{1,24}$/.test(possibleLanguage)
    const code = hasLanguage ? part.slice(firstBreak + 1) : part
    const blockIndex = Math.floor(index / 2)
    const language = hasLanguage ? `<span class="code-language">${escapeHtml(possibleLanguage)}</span>` : ''
    return `<div class="code-block"><div class="code-head">${language}<button type="button" class="code-copy" data-code-index="${blockIndex}">Kopieren</button></div><pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre></div>`
  }).join('')
}

function codeBlocks(value: string): string[] {
  const parts = value.split(/```/)
  return parts.filter((_part, index) => index % 2 === 1).map((part) => {
    const firstBreak = part.indexOf('\n')
    const possibleLanguage = firstBreak >= 0 ? part.slice(0, firstBreak).trim() : ''
    return /^[a-zA-Z0-9_+#.-]{1,24}$/.test(possibleLanguage) ? part.slice(firstBreak + 1).replace(/\n$/, '') : part.replace(/\n$/, '')
  })
}

async function copyText(text: string, successMessage: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(successMessage)
  } catch (error) {
    toast.error(`Kopieren fehlgeschlagen: ${extractError(error)}`)
  }
}

function handleMarkdownClick(event: MouseEvent, message: ChatMessage): void {
  const target = event.target
  if (!(target instanceof Element)) return
  const button = target.closest<HTMLButtonElement>('.code-copy')
  if (!button) return
  const index = Number(button.dataset.codeIndex)
  const code = codeBlocks(message.content)[index]
  if (code !== undefined) void copyText(code, 'Codeblock kopiert.')
}

function resizeInput(): void {
  const element = inputElement.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 192)}px`
}

function useExample(example: string): void {
  input.value = example
  nextTick(() => {
    resizeInput()
    inputElement.value?.focus()
  })
}

function onHistoryScroll(): void {
  const element = historyElement.value
  if (!element) return
  autoScroll.value = element.scrollHeight - element.scrollTop - element.clientHeight < 80
}

async function scrollToEnd(force = false): Promise<void> {
  if (!force && !autoScroll.value) return
  await nextTick()
  const element = historyElement.value
  if (element) element.scrollTop = element.scrollHeight
}

function handleChunk(chunk: ChatStreamChunk, assistant: ChatMessage): void {
  if (chunk.delta) assistant.content += chunk.delta
  if (chunk.eval_count !== undefined || chunk.eval_duration_ms !== undefined || chunk.prompt_eval_count !== undefined) {
    assistant.stats = {
      evalCount: chunk.eval_count ?? assistant.stats?.evalCount ?? null,
      evalDurationMs: chunk.eval_duration_ms ?? assistant.stats?.evalDurationMs ?? null,
      promptEvalCount: chunk.prompt_eval_count ?? assistant.stats?.promptEvalCount ?? null,
    }
  }
  if (chunk.done) assistant.status = 'done'
  if (chunk.error) {
    assistant.status = 'error'
    assistant.error = chunk.error
    toast.error(chunk.error)
  }
}

async function sendMessage(): Promise<void> {
  const content = input.value.trim()
  if (!content || streaming.value || !selectedModel.value) return

  const model = selectedModel.value
  const requestMessages = messages.value
    .filter((message) => message.content && message.status !== 'error')
    .map((message) => ({ role: message.role, content: message.content }))
  const user: ChatMessage = { id: makeId(), role: 'user', content, createdAt: new Date().toISOString() }
  const assistant: ChatMessage = {
    id: makeId(), role: 'assistant', content: '', createdAt: new Date().toISOString(), model, status: 'streaming',
  }
  messages.value.push(user, assistant)
  input.value = ''
  streaming.value = true
  autoScroll.value = true
  abortController = new AbortController()
  await nextTick()
  resizeInput()
  await scrollToEnd(true)

  const controller = abortController
  try {
    await streamChat({
      model,
      messages: [...requestMessages, { role: 'user', content }],
      system: systemPrompt.value || undefined,
      temperature: temperature.value,
      signal: controller.signal,
      onChunk: (chunk) => {
        if (!controller.signal.aborted) handleChunk(chunk, assistant)
      },
    })
    if (controller.signal.aborted) assistant.status = 'aborted'
    else if (assistant.status === 'streaming') assistant.status = 'done'
  } catch (error) {
    if ((error instanceof Error && error.name === 'AbortError') || controller.signal.aborted) {
      assistant.status = 'aborted'
    } else {
      const message = extractError(error)
      assistant.status = 'error'
      assistant.error = message
      toast.error(message)
    }
  } finally {
    streaming.value = false
    abortController = null
    await scrollToEnd()
  }
}

function stopStreaming(): void {
  abortController?.abort()
}

function newConversation(): void {
  abortController?.abort()
  messages.value = []
  autoScroll.value = true
  toast.info('Neues Gespräch begonnen.')
  nextTick(() => inputElement.value?.focus())
}

function onInputKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  if (!streaming.value) void sendMessage()
}

watch([messages, selectedModel, temperature, systemPrompt], persistChat, { deep: true })
watch(messages, () => { void scrollToEnd() }, { deep: true })
watch(input, () => { void nextTick(resizeInput) })

onMounted(() => {
  if (!document.getElementById('wall-fonts')) {
    const link = document.createElement('link')
    link.id = 'wall-fonts'
    link.rel = 'stylesheet'
    link.href = 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap'
    document.head.appendChild(link)
  }
  restoreChat()
  void loadModels()
  void scrollToEnd(true)
  resizeInput()
})

onBeforeUnmount(() => abortController?.abort())
</script>

<template>
  <main class="chat-console">
    <header class="console-header">
      <div class="title-block">
        <h1>KI-Konsole</h1>
        <div class="router-state mono">
          <span class="status-dot" :class="routerOk ? 'ok' : 'error'" aria-hidden="true"></span>
          <span>{{ routerAddress }}</span>
          <span class="state-text">{{ routerOk ? 'Router bereit' : 'Router nicht erreichbar' }}</span>
        </div>
      </div>

      <div class="controls">
        <label class="field model-field">
          <span>Modell</span>
          <select v-model="selectedModel" :disabled="modelsLoading || streaming || !models.length">
            <option v-if="!models.length" value="">{{ modelsLoading ? 'Modelle werden geladen …' : 'Kein Modell verfügbar' }}</option>
            <option v-for="model in models" :key="model.tag" :value="model.tag">
              {{ model.label }} · {{ model.parameter_size }}
            </option>
          </select>
        </label>

        <label class="field temperature-field">
          <span>Temperatur <b class="mono">{{ formatTemperature(temperature) }}</b></span>
          <input v-model.number="temperature" type="range" min="0" max="1.5" step="0.1" :disabled="streaming">
        </label>

        <button class="button ghost" type="button" :aria-expanded="systemOpen" @click="systemOpen = !systemOpen">
          Systemprompt
          <ChevronDown :size="15" :class="{ rotated: systemOpen }" aria-hidden="true" />
        </button>
        <button class="button ghost" type="button" @click="newConversation">
          <RotateCcw :size="15" aria-hidden="true" />
          Neues Gespräch
        </button>
        <RouterLink class="button ghost" to="/wall">
          <ArrowLeft :size="15" aria-hidden="true" />
          Zur Wand
        </RouterLink>
      </div>

      <Transition name="reveal">
        <div v-if="systemOpen" class="system-panel">
          <label for="system-prompt">Systemprompt</label>
          <textarea id="system-prompt" v-model="systemPrompt" rows="4" :disabled="streaming" spellcheck="true"></textarea>
        </div>
      </Transition>
    </header>

    <section ref="historyElement" class="history" aria-label="Gesprächsverlauf" aria-live="polite" @scroll.passive="onHistoryScroll">
      <div v-if="!messages.length" class="empty-state">
        <div class="empty-mark" aria-hidden="true">KI</div>
        <h2>Bereit für Ihre Anfrage</h2>
        <p>Wählen Sie ein Modell und beginnen Sie ein neues Gespräch.</p>
        <p v-if="modelsError" class="console-error" role="alert">{{ modelsError }}</p>
      </div>

      <TransitionGroup v-else name="message" tag="div" class="message-list">
        <article v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
          <div class="bubble">
            <div class="message-meta">
              <span>{{ message.role === 'user' ? 'Sie' : 'Assistent' }}</span>
              <time class="mono" :datetime="message.createdAt">{{ formatTime(message.createdAt) }}</time>
            </div>
            <div v-if="message.role === 'assistant'" class="markdown" @click="handleMarkdownClick($event, message)" v-html="markdownLight(message.content)"></div>
            <p v-else class="user-text">{{ message.content }}</p>
            <span v-if="message.status === 'streaming'" class="stream-cursor" aria-label="Antwort wird erstellt"></span>
            <div v-if="message.error" class="console-error" role="alert">Fehler: {{ message.error }}</div>
            <div v-if="message.role === 'assistant' && message.status !== 'streaming'" class="assistant-footer">
              <div class="stats mono">
                <span>{{ message.stats?.evalCount ?? '–' }} Tokens</span>
                <span>{{ formatDuration(message.stats?.evalDurationMs) }}</span>
                <span>{{ tokensPerSecond(message.stats) }} Tokens/s</span>
                <span>{{ message.model ?? '–' }}</span>
                <span v-if="message.status === 'aborted'" class="aborted">abgebrochen</span>
              </div>
              <button class="copy-button" type="button" :disabled="!message.content" @click="copyText(message.content, 'Antwort kopiert.')">
                <Copy :size="13" aria-hidden="true" />
                Kopieren
              </button>
            </div>
          </div>
        </article>
      </TransitionGroup>
    </section>

    <footer class="composer">
      <div v-if="!messages.length" class="examples" aria-label="Beispielanfragen">
        <button v-for="example in examples" :key="example" type="button" @click="useExample(example)">{{ example }}</button>
      </div>
      <div class="input-shell">
        <textarea
          ref="inputElement"
          v-model="input"
          rows="1"
          placeholder="Nachricht an die KI-Konsole …"
          aria-label="Nachricht"
          :disabled="!models.length"
          @keydown="onInputKeydown"
          @input="resizeInput"
        ></textarea>
        <button v-if="streaming" class="send-button stop" type="button" @click="stopStreaming">
          <Square :size="16" fill="currentColor" aria-hidden="true" />
          Stopp
        </button>
        <button v-else class="send-button" type="button" :disabled="!canSend" @click="sendMessage">
          <Send :size="16" aria-hidden="true" />
          Senden
        </button>
      </div>
      <p class="input-hint mono">Enter sendet · Umschalt + Enter fügt einen Zeilenumbruch ein</p>
    </footer>
  </main>
</template>

<style scoped>
.chat-console {
  --grund: #0b1020;
  --flaeche: #131a2e;
  --flaeche-2: #1a2340;
  --linie: #263054;
  --text: #e7ecf7;
  --text-2: #aab3cf;
  --text-3: #7f89ab;
  --akzent: #f2b84b;
  --ok: #4cc38a;
  --krit: #f26d6d;
  --info: #6fa8ff;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  height: 100vh;
  min-height: 520px;
  overflow: hidden;
  background: radial-gradient(ellipse at 50% 5%, #12203f 0%, var(--grund) 48%);
  color: var(--text);
  font-family: var(--body);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.mono { font-family: var(--mono); }

.console-header {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: 14px 24px;
  align-items: center;
  padding: 14px 26px;
  background: rgba(11, 16, 32, .9);
  border-bottom: 1px solid var(--linie);
  backdrop-filter: blur(14px);
}

.title-block h1 {
  margin: 0;
  font-family: var(--display);
  font-size: 30px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.router-state { display: flex; align-items: center; gap: 7px; margin-top: 7px; color: var(--text-3); font-size: 11px; }
.state-text { color: var(--text-2); }
.status-dot { width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%; background: var(--text-3); }
.status-dot.ok { background: var(--ok); box-shadow: 0 0 9px rgba(76, 195, 138, .65); }
.status-dot.error { background: var(--krit); box-shadow: 0 0 9px rgba(242, 109, 109, .55); }

.controls { display: flex; align-items: end; justify-content: flex-end; gap: 9px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 5px; color: var(--text-3); font-family: var(--display); font-size: 11px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; }
.field b { margin-left: 5px; color: var(--text-2); font-size: 10px; }
.model-field { width: min(260px, 28vw); }
.temperature-field { width: 145px; }

select,
.system-panel textarea {
  color: var(--text);
  background: var(--flaeche);
  border: 1px solid var(--linie);
  border-radius: 5px;
  font: 13px var(--body);
}

select { height: 34px; padding: 0 30px 0 9px; text-overflow: ellipsis; }
input[type='range'] { height: 17px; accent-color: var(--akzent); cursor: pointer; }

.button {
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 11px;
  border: 1px solid var(--linie);
  border-radius: 5px;
  background: transparent;
  color: var(--text-2);
  font: 700 13px var(--display);
  letter-spacing: .05em;
  text-decoration: none;
  text-transform: uppercase;
  cursor: pointer;
}

.button:hover { color: var(--text); border-color: #3d4b7a; background: var(--flaeche); }
.button svg { transition: transform .2s ease; }
.button svg.rotated { transform: rotate(180deg); }

.system-panel { grid-column: 1 / -1; display: grid; gap: 6px; }
.system-panel label { color: var(--text-3); font: 600 11px var(--display); letter-spacing: .1em; text-transform: uppercase; }
.system-panel textarea { width: 100%; padding: 10px 12px; resize: vertical; line-height: 1.45; }

.history { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-color: var(--linie) transparent; }
.message-list { width: min(1040px, calc(100% - 36px)); margin: 0 auto; padding: 28px 0 42px; }
.message-row { display: flex; margin-bottom: 20px; }
.message-row.user { justify-content: flex-end; }
.bubble { width: fit-content; max-width: min(82%, 800px); padding: 13px 15px 11px; border: 1px solid var(--linie); border-radius: 8px; background: var(--flaeche); box-shadow: 0 10px 30px rgba(0, 0, 0, .12); }
.user .bubble { background: #202a48; border-color: #33416d; border-bottom-right-radius: 2px; }
.assistant .bubble { border-bottom-left-radius: 2px; }
.message-meta { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 7px; color: var(--text-3); font: 600 11px var(--display); letter-spacing: .08em; text-transform: uppercase; }
.message-meta time { font-size: 10px; font-weight: 400; letter-spacing: 0; }
.user-text { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; }

.markdown { color: var(--text); line-height: 1.62; overflow-wrap: anywhere; }
.markdown :deep(strong) { color: #fff5dc; font-weight: 600; }
.markdown :deep(code) { padding: 2px 5px; border: 1px solid #303b63; border-radius: 4px; background: #0d1325; color: #d9e4ff; font: .88em var(--mono); }
.markdown :deep(ul), .markdown :deep(ol) { margin: 7px 0; padding-left: 23px; }
.markdown :deep(li) { margin: 3px 0; }
.markdown :deep(.code-block) { margin: 11px 0; overflow: hidden; border: 1px solid #2c365a; border-radius: 6px; background: #080d1a; }
.markdown :deep(.code-head) { min-height: 31px; display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 0 8px 0 11px; background: #10172b; border-bottom: 1px solid #252f50; }
.markdown :deep(.code-language) { margin-right: auto; color: var(--text-3); font: 10px var(--mono); text-transform: uppercase; }
.markdown :deep(.code-copy) { padding: 3px 6px; border: 0; background: transparent; color: var(--text-2); font: 10px var(--mono); cursor: pointer; }
.markdown :deep(.code-copy:hover) { color: var(--akzent); }
.markdown :deep(pre) { margin: 0; padding: 13px 15px; overflow-x: auto; }
.markdown :deep(pre code) { padding: 0; border: 0; background: transparent; color: #dbe5ff; font-size: 12px; line-height: 1.55; white-space: pre; }

.stream-cursor { display: inline-block; width: 7px; height: 17px; margin-left: 3px; vertical-align: -3px; background: var(--akzent); animation: blink .9s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }

.assistant-footer { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--linie); }
.stats { display: flex; gap: 6px 12px; flex-wrap: wrap; color: var(--text-3); font-size: 9px; }
.stats .aborted { color: var(--akzent); }
.copy-button { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 4px; padding: 3px 5px; border: 0; background: transparent; color: var(--text-3); font: 10px var(--body); cursor: pointer; }
.copy-button:hover { color: var(--akzent); }
.copy-button:disabled { opacity: .45; cursor: not-allowed; }
.console-error { margin: 9px 0 0; color: var(--krit); font: 11px/1.5 var(--mono); }

.empty-state { height: 100%; min-height: 260px; display: grid; place-content: center; justify-items: center; padding: 30px; text-align: center; color: var(--text-3); }
.empty-mark { width: 58px; height: 58px; display: grid; place-items: center; margin-bottom: 13px; border: 1px solid #46547f; border-radius: 50%; color: var(--akzent); font: 700 24px var(--display); box-shadow: 0 0 35px rgba(242, 184, 75, .08); }
.empty-state h2 { margin: 0; color: var(--text); font: 600 24px var(--display); letter-spacing: .04em; text-transform: uppercase; }
.empty-state p { margin: 6px 0 0; font-size: 13px; }

.composer { position: relative; z-index: 2; padding: 11px max(18px, calc((100% - 1040px) / 2)) 10px; border-top: 1px solid var(--linie); background: rgba(8, 12, 24, .94); backdrop-filter: blur(16px); }
.examples { display: flex; gap: 7px; margin-bottom: 9px; overflow-x: auto; scrollbar-width: none; }
.examples button { flex: 0 0 auto; max-width: 310px; padding: 6px 9px; overflow: hidden; border: 1px solid var(--linie); border-radius: 999px; background: var(--flaeche); color: var(--text-2); font: 11px var(--body); text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.examples button:hover { color: var(--text); border-color: #45547f; }
.input-shell { display: flex; align-items: flex-end; gap: 10px; padding: 8px; border: 1px solid #303a61; border-radius: 8px; background: var(--flaeche); }
.input-shell:focus-within { border-color: var(--akzent); box-shadow: 0 0 0 2px rgba(242, 184, 75, .12); }
.input-shell textarea { flex: 1; min-height: 37px; max-height: 192px; padding: 8px 7px; resize: none; overflow-y: auto; border: 0; outline: 0; background: transparent; color: var(--text); font: 14px/1.5 var(--body); }
.input-shell textarea::placeholder { color: var(--text-3); }
.send-button { height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 14px; border: 1px solid var(--akzent); border-radius: 5px; background: var(--akzent); color: #1a1200; font: 700 14px var(--display); letter-spacing: .06em; text-transform: uppercase; cursor: pointer; }
.send-button.stop { border-color: var(--krit); background: transparent; color: var(--krit); }
.send-button:disabled { border-color: #3b4052; background: #33394b; color: #7f8699; cursor: not-allowed; }
.input-hint { margin: 6px 2px 0; color: var(--text-3); font-size: 9px; text-align: right; }

:is(button, select, textarea, a):focus-visible { outline: 2px solid var(--akzent); outline-offset: 2px; }
:is(button, select, textarea):disabled { opacity: .65; }

.message-enter-active, .reveal-enter-active, .reveal-leave-active { transition: opacity .25s ease, transform .25s ease; }
.message-enter-from { opacity: 0; transform: translateY(8px); }
.reveal-enter-from, .reveal-leave-to { opacity: 0; transform: translateY(-5px); }

@media (max-width: 1050px) {
  .console-header { grid-template-columns: 1fr; }
  .controls { justify-content: flex-start; }
  .model-field { width: min(300px, 55vw); }
}

@media (max-width: 640px) {
  .chat-console { min-height: 100dvh; height: 100dvh; }
  .console-header { padding: 12px 14px; gap: 12px; }
  .title-block h1 { font-size: 26px; }
  .router-state { flex-wrap: wrap; }
  .state-text { width: 100%; padding-left: 15px; }
  .controls { display: grid; grid-template-columns: 1fr 1fr; align-items: end; }
  .model-field { width: auto; grid-column: 1 / -1; }
  .temperature-field { width: auto; grid-column: 1 / -1; }
  .button { padding: 0 8px; font-size: 12px; }
  .message-list { width: calc(100% - 20px); padding-top: 18px; }
  .bubble { max-width: 92%; }
  .composer { padding-inline: 10px; }
  .input-hint { display: none; }
  .send-button { width: 39px; padding: 0; justify-content: center; font-size: 0; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation: none !important; transition: none !important; }
}
</style>
