<script setup lang="ts">
/**
 * MCP-Einstellungen: die MCP-Server der Landschaft mit Erreichbarkeit, Werkzeugen,
 * Skills und der fertigen Verbindungszeile für Claude Code. Secrets bleiben im
 * Vault – die Seite zeigt nur, ob der Schlüssel vorhanden ist.
 */
import { computed, onMounted, ref } from 'vue'
import { Plug, RefreshCw, Copy, Check, KeyRound, Wrench, Sparkles, AlertTriangle } from 'lucide-vue-next'
import Card from '../../components/shared/Card.vue'
import Badge from '../../components/shared/Badge.vue'
import Spinner from '../../components/shared/Spinner.vue'
import EmptyState from '../../components/shared/EmptyState.vue'
import { listMcpServers } from '../../api/mcp'
import { extractError } from '../../api/client'
import { useToastStore } from '../../stores/toast'
import type { McpServerState } from '../../api/types'

const toast = useToastStore()
const servers = ref<McpServerState[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const kopiert = ref<string | null>(null)
const offen = ref<Record<string, boolean>>({})

async function load() {
  loading.value = true
  try {
    servers.value = (await listMcpServers()).servers
    error.value = null
  } catch (err) {
    error.value = extractError(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function zustand(s: McpServerState): { variant: string; text: string } {
  if (s.error) return { variant: 'red', text: 'Fehler' }
  if (s.inspect) return s.inspect.ok ? { variant: 'green', text: 'verbunden' } : { variant: 'red', text: 'nicht erreichbar' }
  if (s.health) return s.health.ok ? { variant: 'green', text: 'erreichbar' } : s.health.ok === null ? { variant: 'slate', text: 'keine Prüfung' } : { variant: 'red', text: 'nicht erreichbar' }
  return { variant: 'slate', text: 'nur beschrieben' }
}

async function kopieren(s: McpServerState) {
  try {
    await navigator.clipboard.writeText(s.snippet)
    kopiert.value = s.id
    toast.success('Verbindungszeile kopiert – <SECRET> durch den Wert aus dem Vault ersetzen')
    window.setTimeout(() => { if (kopiert.value === s.id) kopiert.value = null }, 2500)
  } catch {
    toast.error('Kopieren nicht möglich – Zeile bitte markieren')
  }
}

function skillsListe(s: McpServerState): { name: string; description: string }[] {
  const raw = s.inspect?.skills
  if (!raw) return []
  const arr = Array.isArray(raw) ? raw : (typeof raw === 'object' && Array.isArray((raw as { skills?: unknown }).skills) ? (raw as { skills: unknown[] }).skills : [])
  return (arr as unknown[]).map((e) => {
    if (typeof e === 'string') return { name: e, description: '' }
    const o = e as Record<string, unknown>
    return { name: String(o.name ?? o.id ?? o.kennung ?? '?'), description: String(o.description ?? o.beschreibung ?? o.zweck ?? '') }
  })
}

const gesamt = computed(() => ({
  server: servers.value.length,
  verbunden: servers.value.filter((s) => s.inspect?.ok || s.health?.ok).length,
  werkzeuge: servers.value.reduce((n, s) => n + (s.inspect?.tools.length ?? 0), 0),
}))
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <Card title="MCP-Server" subtitle="Werkzeuge und Skills, die Claude Code und Kira aus der Landschaft beziehen">
      <template #actions>
        <button class="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800" @click="load">
          <RefreshCw :size="14" /> Aktualisieren
        </button>
      </template>
      <div v-if="loading && !servers.length" class="flex items-center gap-2 text-slate-500"><Spinner /> Frage MCP-Server ab …</div>
      <div v-else-if="error" class="rounded-md border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 p-4 text-sm text-red-800 dark:text-red-200">
        <p class="font-semibold flex items-center gap-2"><AlertTriangle :size="16" /> Fehler beim Laden</p><p class="mt-1">{{ error }}</p>
      </div>
      <div v-else-if="!servers.length" class="py-6"><EmptyState title="Keine MCP-Server konfiguriert" message="Server werden in den Einstellungen unter „Wand & LLM-Konsole“ (mcp_servers) gepflegt." /></div>
      <div v-else class="grid grid-cols-3 gap-4 mb-2">
        <div class="rounded-lg border border-slate-200/70 dark:border-slate-800/70 p-3"><p class="text-xs uppercase tracking-wider text-slate-500">Server</p><p class="text-2xl font-bold tabular-nums">{{ gesamt.server }}</p></div>
        <div class="rounded-lg border border-slate-200/70 dark:border-slate-800/70 p-3"><p class="text-xs uppercase tracking-wider text-slate-500">Erreichbar</p><p class="text-2xl font-bold tabular-nums">{{ gesamt.verbunden }}</p></div>
        <div class="rounded-lg border border-slate-200/70 dark:border-slate-800/70 p-3"><p class="text-xs uppercase tracking-wider text-slate-500">Werkzeuge</p><p class="text-2xl font-bold tabular-nums">{{ gesamt.werkzeuge }}</p></div>
      </div>
    </Card>

    <Card v-for="s in servers" :key="s.id" :title="s.name" :subtitle="s.description || undefined">
      <template #actions>
        <Badge :variant="zustand(s).variant as any" dot>{{ zustand(s).text }}</Badge>
        <Badge variant="slate">{{ s.transport === 'http' ? 'HTTP' : 'stdio' }}</Badge>
      </template>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div class="space-y-3 text-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5"><Plug :size="12" /> Verbindung</p>
          <dl class="space-y-1.5">
            <div class="flex justify-between gap-3 border-b border-slate-100 dark:border-slate-800/60 py-1"><dt class="text-slate-500">Adresse</dt><dd class="font-mono text-xs text-right break-all">{{ s.url || s.command || '—' }}</dd></div>
            <div class="flex justify-between gap-3 border-b border-slate-100 dark:border-slate-800/60 py-1"><dt class="text-slate-500">Schlüssel</dt>
              <dd class="flex items-center gap-1.5 text-xs">
                <KeyRound :size="12" />
                <span class="font-mono">{{ s.secret_key || '—' }}</span>
                <Badge v-if="s.secret_key" :variant="s.secret_ok ? 'green' : 'amber'">{{ s.secret_ok ? 'im Vault' : 'fehlt im Vault' }}</Badge>
              </dd>
            </div>
            <div v-if="s.health" class="flex justify-between gap-3 border-b border-slate-100 dark:border-slate-800/60 py-1"><dt class="text-slate-500">Health</dt><dd class="font-mono text-xs">{{ s.health.note }}</dd></div>
            <div v-if="s.inspect?.server?.name" class="flex justify-between gap-3 border-b border-slate-100 dark:border-slate-800/60 py-1"><dt class="text-slate-500">Server meldet</dt><dd class="font-mono text-xs">{{ s.inspect.server.name }} {{ s.inspect.server.version || '' }} · MCP {{ s.inspect.protocol || '' }}</dd></div>
            <div v-if="s.inspect?.error" class="text-xs text-red-600 dark:text-red-300">{{ s.inspect.error }}</div>
            <div v-if="s.error" class="text-xs text-red-600 dark:text-red-300">{{ s.error }}</div>
          </dl>
          <div v-if="s.snippet">
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Für Claude Code</p>
            <div class="flex items-start gap-2">
              <code class="flex-1 block text-[11px] leading-5 font-mono bg-slate-100 dark:bg-slate-900 rounded-md p-2 break-all">{{ s.snippet }}</code>
              <button class="shrink-0 inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800" @click="kopieren(s)">
                <Check v-if="kopiert === s.id" :size="13" /><Copy v-else :size="13" /> Kopieren
              </button>
            </div>
            <p class="text-[11px] text-slate-400 mt-1">&lt;SECRET&gt; steht für den Wert des Vault-Schlüssels – er wird hier nie angezeigt.</p>
          </div>
        </div>

        <div class="text-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2"><Wrench :size="12" /> Werkzeuge <span class="text-slate-400 normal-case tracking-normal">· {{ s.inspect?.tools.length ?? 0 }}</span></p>
          <div v-if="!s.inspect" class="text-xs text-slate-400">Werkzeuge werden nur bei HTTP-Servern live abgefragt.</div>
          <div v-else-if="!s.inspect.tools.length" class="text-xs text-slate-400">{{ s.inspect.ok ? 'Keine Werkzeuge gemeldet.' : 'Nicht abfragbar.' }}</div>
          <ul v-else class="space-y-1 max-h-72 overflow-auto pr-1">
            <li v-for="t in s.inspect.tools" :key="t.name" class="rounded-md border border-slate-200/70 dark:border-slate-800/70 px-2.5 py-1.5">
              <p class="font-mono text-xs font-semibold">{{ t.name }}</p>
              <p v-if="t.description" class="text-[11px] text-slate-500 leading-snug">{{ t.description }}</p>
            </li>
          </ul>
        </div>

        <div class="text-sm">
          <p class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2"><Sparkles :size="12" /> Skills <span class="text-slate-400 normal-case tracking-normal">· {{ skillsListe(s).length }}</span></p>
          <div v-if="!skillsListe(s).length" class="text-xs text-slate-400">{{ s.inspect?.skills && typeof s.inspect.skills === 'string' ? s.inspect.skills : 'Kein Skill-Katalog (Werkzeug skills_list fehlt oder nicht abfragbar).' }}</div>
          <ul v-else class="space-y-1 max-h-72 overflow-auto pr-1">
            <li v-for="sk in skillsListe(s).slice(0, offen[s.id] ? 999 : 12)" :key="sk.name" class="rounded-md border border-slate-200/70 dark:border-slate-800/70 px-2.5 py-1.5">
              <p class="font-mono text-xs font-semibold">{{ sk.name }}</p>
              <p v-if="sk.description" class="text-[11px] text-slate-500 leading-snug">{{ sk.description }}</p>
            </li>
          </ul>
          <button v-if="skillsListe(s).length > 12" class="mt-2 text-xs underline text-slate-500" @click="offen[s.id] = !offen[s.id]">{{ offen[s.id] ? 'weniger' : `alle ${skillsListe(s).length} anzeigen` }}</button>
        </div>
      </div>
    </Card>
  </div>
</template>
