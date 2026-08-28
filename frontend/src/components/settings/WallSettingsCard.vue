<script setup lang="ts">
/**
 * Einstellungen der Wand und der LLM-Konsole: Ausblendliste, Links, Hero, Sonden,
 * Demo-Start, Sicherungspfad, Modell-Whitelist, Systemprompt, MCP-Server.
 * Listen als Zeilen, Zuordnungen als JSON mit Prüfung vor dem Speichern.
 */
import { onMounted, ref } from 'vue'
import { Save, Radar } from 'lucide-vue-next'
import Card from '../shared/Card.vue'
import Spinner from '../shared/Spinner.vue'
import { getWallConfig, patchWallConfig, pushTest } from '../../api/overview'
import { useToastStore } from '../../stores/toast'
import { extractError } from '../../api/client'
import type { WallConfig } from '../../api/types'

const toast = useToastStore()
const loading = ref(true)
const saving = ref(false)
const cfg = ref<WallConfig | null>(null)

const hosts = ref('')
const hide = ref('')
const links = ref('')
const labels = ref('')
const hero = ref('')
const probes = ref('')
const demo = ref('')
const backupDir = ref('/backups')
const chatModels = ref('')
const chatSystem = ref('')
const chatNumCtx = ref(12288)
const chatThink = ref(false)
const push = ref('')
const werkstattTage = ref(14)
const verlaufTage = ref(30)
const chatMaxTokens = ref(900)
const pushBusy = ref(false)
const mcpServers = ref('')
const workDirs = ref('')
const kira = ref('')
const agentBins = ref('')
const vorschlaege = ref('')
const auftragVorlagen = ref('')
const auftragParallel = ref(3)
const codexSandbox = ref<'danger-full-access' | 'workspace-write'>('danger-full-access')
const flowAgent = ref('')
const leitinstanz = ref('')
const agentHosts = ref('')
const fehler = ref<Record<string, string>>({})

function zeilen(list: string[]): string { return list.join('\n') }
function ausZeilen(text: string): string[] { return text.split('\n').map((z) => z.trim()).filter(Boolean) }
function json(v: unknown): string { return JSON.stringify(v, null, 2) }

async function load() {
  loading.value = true
  try {
    const c = await getWallConfig()
    cfg.value = c
    hosts.value = zeilen(c.hosts)
    hide.value = zeilen(c.hide)
    links.value = json(c.links)
    labels.value = json(c.labels)
    hero.value = json(c.hero)
    probes.value = json(c.probes)
    demo.value = json(c.demo)
    backupDir.value = c.backup_dir
    chatModels.value = json(c.chat_models)
    chatSystem.value = c.chat_system
    chatNumCtx.value = c.chat_num_ctx ?? 12288
    chatThink.value = !!c.chat_think
    push.value = json(c.push ?? {})
    werkstattTage.value = c.werkstatt_aktiv_tage ?? 14
    verlaufTage.value = c.verlauf_tage ?? 30
    chatMaxTokens.value = c.chat_max_tokens ?? 900
    mcpServers.value = json(c.mcp_servers)
    workDirs.value = json(c.work_dirs)
    kira.value = json(c.kira)
    agentBins.value = json(c.agent_bins ?? {})
    vorschlaege.value = json(c.vorschlaege ?? {})
    auftragVorlagen.value = json(c.auftrag_vorlagen ?? [])
    auftragParallel.value = c.auftrag_parallel ?? 3
    codexSandbox.value = c.codex_sandbox ?? 'danger-full-access'
    flowAgent.value = json(c.flow_agent ?? {})
    leitinstanz.value = json(c.leitinstanz ?? {})
    agentHosts.value = zeilen(c.agent_hosts ?? ['nuc'])
  } catch (err) { toast.error(extractError(err)) }
  finally { loading.value = false }
}
onMounted(load)

function parse<T>(feld: string, text: string, erwartet: 'object' | 'array'): T | undefined {
  try {
    const v = JSON.parse(text)
    const istArray = Array.isArray(v)
    if ((erwartet === 'array') !== istArray || v === null || typeof v !== 'object') {
      fehler.value[feld] = erwartet === 'array' ? 'Erwartet wird eine JSON-Liste [ … ]' : 'Erwartet wird ein JSON-Objekt { … }'
      return undefined
    }
    delete fehler.value[feld]
    return v as T
  } catch (e) {
    fehler.value[feld] = `Kein gültiges JSON: ${(e as Error).message}`
    return undefined
  }
}

async function save() {
  fehler.value = {}
  const patch: Partial<WallConfig> = {
    hosts: ausZeilen(hosts.value),
    hide: ausZeilen(hide.value),
    backup_dir: backupDir.value.trim() || '/backups',
    chat_system: chatSystem.value,
    chat_num_ctx: Math.max(2048, Math.min(131072, Math.round(Number(chatNumCtx.value) || 12288))),
    chat_think: chatThink.value,
    werkstatt_aktiv_tage: Math.max(1, Math.min(365, Math.round(Number(werkstattTage.value) || 14))),
    verlauf_tage: Math.max(1, Math.min(365, Math.round(Number(verlaufTage.value) || 30))),
    chat_max_tokens: Math.max(100, Math.min(8000, Math.round(Number(chatMaxTokens.value) || 900))),
    auftrag_parallel: Math.max(1, Math.min(8, Math.round(Number(auftragParallel.value) || 3))),
    codex_sandbox: codexSandbox.value,
    agent_hosts: ausZeilen(agentHosts.value),
  }
  const pu = parse<Record<string, unknown>>('push', push.value, 'object'); if (pu) patch.push = pu
  const l = parse<Record<string, string>>('links', links.value, 'object'); if (l) patch.links = l
  const la = parse<WallConfig['labels']>('labels', labels.value, 'object'); if (la) patch.labels = la
  const h = parse<Record<string, string>>('hero', hero.value, 'object'); if (h) patch.hero = h
  const p = parse<WallConfig['probes']>('probes', probes.value, 'array'); if (p) patch.probes = p
  const d = parse<Record<string, string>>('demo', demo.value, 'object'); if (d) patch.demo = d
  const m = parse<WallConfig['chat_models']>('chat_models', chatModels.value, 'array'); if (m) patch.chat_models = m
  const s = parse<Record<string, unknown>[]>('mcp_servers', mcpServers.value, 'array'); if (s) patch.mcp_servers = s
  const wd = parse<Record<string, string>>('work_dirs', workDirs.value, 'object'); if (wd) patch.work_dirs = wd
  const k = parse<Record<string, string>>('kira', kira.value, 'object'); if (k) patch.kira = k
  const ab = parse<Record<string, string>>('agent_bins', agentBins.value, 'object'); if (ab) patch.agent_bins = ab
  const vs = parse<Record<string, unknown>>('vorschlaege', vorschlaege.value, 'object'); if (vs) patch.vorschlaege = vs
  const av = parse<Record<string, unknown>[]>('auftrag_vorlagen', auftragVorlagen.value, 'array'); if (av) patch.auftrag_vorlagen = av
  const fl = parse<Record<string, unknown>>('flow_agent', flowAgent.value, 'object'); if (fl) patch.flow_agent = fl
  const li = parse<Record<string, unknown>>('leitinstanz', leitinstanz.value, 'object'); if (li) patch.leitinstanz = li
  if (Object.keys(fehler.value).length) { toast.error('Bitte die markierten Felder korrigieren'); return }
  saving.value = true
  try {
    cfg.value = await patchWallConfig(patch)
    toast.success('Wand-Einstellungen gespeichert')
  } catch (err) { toast.error(extractError(err)) }
  finally { saving.value = false }
}

async function pushTesten() {
  pushBusy.value = true
  try { await pushTest(); toast.success('Testnachricht per Telegram gesendet') } catch (err) { toast.error(extractError(err)) } finally { pushBusy.value = false }
}

const felder: { key: string; label: string; hint: string; model: typeof links; rows: number }[] = [
  { key: 'links', label: 'Öffentliche Adressen (Projekt → URL)', hint: 'Compose-Projekt oder Container-Präfix als Schlüssel', model: links, rows: 8 },
  { key: 'labels', label: 'Anzeigenamen (Projekt → {title, sub})', hint: 'Sprechende Titel für die Wand', model: labels, rows: 8 },
  { key: 'hero', label: 'Hero-Projekt', hint: 'project, title, sub, url, demo_path, probe', model: hero, rows: 8 },
  { key: 'probes', label: 'Sonden (JSON-Endpunkte mit Kennzahlen)', hint: 'id, label, url, secret_key, header, header_prefix, fields[{key,label}]', model: probes, rows: 12 },
  { key: 'demo', label: 'Demo-Start (HPP)', hint: 'login_url, aufbau_url, user_secret, password_secret – Werte liegen im Vault', model: demo, rows: 6 },
  { key: 'chat_models', label: 'Modell-Whitelist der LLM-Konsole', hint: '[{tag, label}] – nur geladene Modelle erscheinen', model: chatModels, rows: 7 },
  { key: 'mcp_servers', label: 'MCP-Server', hint: 'id, name, transport, url|command, secret_key, header, header_prefix, health_url, skills_tool', model: mcpServers, rows: 14 },
  { key: 'work_dirs', label: 'Werkstatt (Host → Projektverzeichnis)', hint: 'git-Stand, uncommittete Änderungen und Pausen (.session_resume.md) je Host', model: workDirs, rows: 6 },
  { key: 'kira', label: 'Kira-Memory', hint: 'host, url, env_file, env_key – der Schlüssel wird auf dem Host aus der .env gelesen', model: kira, rows: 6 },
  { key: 'agent_bins', label: 'Aufträge: Agenten-Programme (claude, codex, gemini → absoluter Pfad auf dem Host)', hint: 'bash -lc über SSH kennt ~/bin und ~/.npm-global/bin nicht', model: agentBins, rows: 5 },
  { key: 'vorschlaege', label: 'Aufträge: wöchentliche Vorschlagsläufe', hint: 'aktiv, wochentag (0 = Montag … 6 = Sonntag), stunde, agent – je aktivem Werkstatt-Projekt, Ergebnis als Karten im Eingang', model: vorschlaege, rows: 5 },
  { key: 'flow_agent', label: 'flow-agent (Projektinventar aller Hosts)', hint: 'url, secret_key (Vault: Lese-Schlüssel), hosts = flow-agent-Hostname → Cockpit-Host', model: flowAgent, rows: 6 },
  { key: 'leitinstanz', label: 'Leitinstanz (Aufträge zentral)', hint: 'url leer = diese Instanz führt Aufträge selbst; sonst Weiterleitung von /admin/api/auftraege dorthin – Anmeldung über Vault (benutzer_secret, passwort_secret)', model: leitinstanz, rows: 5 },
  { key: 'auftrag_vorlagen', label: 'Aufträge: eigene Vorlagen', hint: '[{id, titel mit {projekt}, profil, prioritaet, text}] – gleiche id ersetzt die Vorgabe', model: auftragVorlagen, rows: 8 },
  { key: 'push', label: 'Push-Alarme (Telegram)', hint: 'aktiv, min_level (warn|krit), bestaetigung_laeufe (Vorgabe 2: Alarm erst nach so vielen Wand-Läufen in Folge, Entwarnung ebenso), ruhe_von/ruhe_bis (nachts nur Kritisches), token_secret, chat_secret, instanz', model: push, rows: 8 },
]
</script>

<template>
  <Card title="Wand & LLM-Konsole" subtitle="Was auf der Wand erscheint, welche Modelle die Konsole anbietet, welche MCP-Server gezeigt werden">
    <template #actions>
      <button class="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50" :disabled="saving || loading" @click="save">
        <Save :size="14" /> Speichern
      </button>
    </template>
    <div v-if="loading" class="flex items-center gap-2 text-slate-500"><Spinner /> Lade Wand-Einstellungen …</div>
    <div v-else class="space-y-5">
      <p class="text-xs text-slate-500 flex items-center gap-1.5"><Radar :size="12" /> Die Wand liegt unter <span class="font-mono">/admin/wall</span>, die Konsole unter <span class="font-mono">/admin/chat</span>, die MCP-Seite unter <span class="font-mono">/admin/mcp</span>. Secrets nur im Vault anlegen – hier stehen nur deren Schlüsselnamen.</p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Ausblenden (eine Angabe je Zeile, Teilstring)</span>
          <textarea v-model="hide" rows="6" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Projekte/Container mit diesen Namensteilen erscheinen nie auf der Wand.</span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Hosts auf der Wand (leer = alle)</span>
          <textarea v-model="hosts" rows="6" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Hostnamen wie in der Host-Verwaltung, eine Angabe je Zeile.</span>
        </label>
        <label class="block md:col-span-2">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Systemprompt der LLM-Konsole</span>
          <textarea v-model="chatSystem" rows="3" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm p-2" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Kontextfenster der Konsole bei Kira-RAG (Tokens)</span>
          <input v-model.number="chatNumCtx" type="number" min="2048" max="131072" step="1024" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Ollama num_ctx, nur gesetzt, wenn Quellen mitgegeben werden. Vorgabe 12 288.</span>
        </label>
        <label class="flex items-start gap-2">
          <input v-model="chatThink" type="checkbox" class="mt-1" />
          <span><span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Denkmodus des Modells</span><br /><span class="text-[11px] text-slate-400">Aus (Vorgabe): Antwort in Sekunden. An: Qwen „denkt“ vor der Antwort – bis zu einige Tausend versteckte Tokens, Minuten Wartezeit.</span></span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Antwortlänge der Konsole (max. Tokens)</span>
          <input v-model.number="chatMaxTokens" type="number" min="100" max="8000" step="100" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Ollama num_predict. Vorgabe 900 – bei ~11 Tokens/s etwa 80 s Obergrenze.</span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Aufträge: gleichzeitige Läufe (Basis)</span>
          <input v-model.number="auftragParallel" type="number" min="1" max="8" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Wird nach Claude-Auslastung gedrosselt: ab 60 % des 5-Stunden-Fensters Basis − 1, ab 85 % ein Lauf, ab 95 % Pause.</span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Aufträge: Hosts mit angemeldeten Agenten (eine Zeile je Host)</span>
          <textarea v-model="agentHosts" rows="3" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Nur dort sind claude, codex und agy installiert und angemeldet; Projekte auf anderen Hosts sind im Kanban nicht wählbar.</span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Aufträge: Codex-Sandbox</span>
          <select v-model="codexSandbox" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2">
            <option value="danger-full-access">ohne Isolierung (NUC: bwrap nicht verfügbar)</option>
            <option value="workspace-write">workspace-write / read-only (bwrap muss funktionieren)</option>
          </select>
          <span class="text-[11px] text-slate-400">Schutz bleibt der eigene Worktree mit Branch je Auftrag.</span>
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Werkstatt: „aktiv“ = Commit oder Pause in den letzten … Tagen</span>
          <input v-model.number="werkstattTage" type="number" min="1" max="365" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
        </label>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Verlauf aufbewahren (Tage)</span>
          <input v-model.number="verlaufTage" type="number" min="1" max="365" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">Kennzahlen je Lauf (alle 90 s) für die Verlaufslinien der Wand.</span>
        </label>
        <div class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Push-Kanal prüfen</span><br />
          <button class="mt-1 inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50" :disabled="pushBusy" @click="pushTesten">Testnachricht senden</button>
          <span class="block text-[11px] text-slate-400">Nutzt telegram_bot_token und telegram_chat_id aus dem Vault.</span>
        </div>
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">Sicherungsverzeichnis (im Container)</span>
          <input v-model="backupDir" class="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs p-2" />
          <span class="text-[11px] text-slate-400">z. B. /backups – als Volume nur lesend einbinden.</span>
        </label>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <label v-for="f in felder" :key="f.key" class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-slate-500">{{ f.label }}</span>
          <textarea v-model="f.model.value" :rows="f.rows" class="mt-1 w-full rounded-md border bg-white dark:bg-slate-900 font-mono text-xs p-2" :class="fehler[f.key] ? 'border-red-400' : 'border-slate-300 dark:border-slate-700'" />
          <span class="text-[11px]" :class="fehler[f.key] ? 'text-red-600' : 'text-slate-400'">{{ fehler[f.key] || f.hint }}</span>
        </label>
      </div>
    </div>
  </Card>
</template>
