import { API_BASE, client, getToken, USE_MOCKS } from './client'
import type { ChatModelsResponse, ChatStreamChunk } from './types'

export async function listChatModels(): Promise<ChatModelsResponse> {
  if (USE_MOCKS) {
    return {
      router: 'http://100.99.159.80:7842', router_ok: true,
      models: [
        { tag: 'qwen3.8-heretic:27b', label: 'Qwen 3.8 · 27B', parameter_size: '26.9B', size_bytes: 17_176_000_000 },
        { tag: 'qwen3:14b', label: 'Qwen 3 · 14B', parameter_size: '14.8B', size_bytes: 9_276_000_000 },
      ],
      system: 'Du bist die KI-Konsole des flowaudit-Cockpits.',
    }
  }
  const { data } = await client.get<ChatModelsResponse>('/chat/models')
  return data
}

export interface ChatSendOptions {
  model: string
  messages: { role: 'user' | 'assistant'; content: string }[]
  system?: string
  temperature?: number
  /** Kira-RAG vor der Antwort befragen: 'memory' (Projektgedächtnis), 'knowledge' (Wissensbasis), 'both' oder 'off' */
  rag?: 'off' | 'memory' | 'knowledge' | 'both'
  ragProject?: string
  signal?: AbortSignal
  onChunk: (chunk: ChatStreamChunk) => void
}

/** Streamt die Antwort als Server-Sent Events; axios kann keine Streams, daher fetch. */
export async function streamChat(opts: ChatSendOptions): Promise<void> {
  if (USE_MOCKS) {
    const text = 'Das ist eine Beispielantwort der KI-Konsole im Mock-Modus. '
    if (opts.rag && opts.rag !== 'off') {
      opts.onChunk({ sources: [{ quelle: 'memory', titel: 'Demo-Modus per ASGITransport', text: 'Der Demo-Modus fährt die eigene API in-process …', category: 'architecture', project: 'regulierung', created_at: new Date().toISOString(), score: 0.82, id: '1', ref: null }] })
    }
    for (const wort of text.split(' ')) {
      await new Promise((r) => setTimeout(r, 60))
      opts.onChunk({ delta: wort + ' ' })
    }
    opts.onChunk({ done: true, eval_count: 12, eval_duration_ms: 700 })
    return
  }
  const token = getToken()
  const resp = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ model: opts.model, messages: opts.messages, system: opts.system, temperature: opts.temperature, rag: opts.rag ?? 'off', rag_project: opts.ragProject || null }),
    signal: opts.signal,
  })
  if (!resp.ok || !resp.body) {
    let detail = `HTTP ${resp.status}`
    try { const j = await resp.json(); if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* leer */ }
    opts.onChunk({ error: detail })
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let puffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    puffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = puffer.indexOf('\n\n')) >= 0) {
      const block = puffer.slice(0, idx)
      puffer = puffer.slice(idx + 2)
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue
        try {
          const chunk = JSON.parse(line.slice(5).trim()) as ChatStreamChunk
          opts.onChunk(chunk)
          if (chunk.done || chunk.error) return
        } catch { /* unvollstaendige Zeile ignorieren */ }
      }
    }
  }
}
