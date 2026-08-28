<script setup lang="ts">
/**
 * Das Cockpit: oben die Karte (Hosts als Knoten, Tailscale-Mesh, Cloudflare-Rand,
 * fließender Verkehr), darunter die Kacheln, unten das Laufband.
 * Vollbild, dunkel, alle 30 s aktualisiert. Nur Whitelist-Inhalte (Backend).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { getOverview, getVerlauf, startDemo, tmuxAusgabe, tmuxSenden } from '../api/overview'
import { extractError } from '../api/client'
import { usePollStore } from '../stores/poll'
import { useToastStore } from '../stores/toast'
import type { Overview, VerlaufAntwort, WallHost, WallProject } from '../api/types'
import BackupsKachel from '../components/wall/BackupsKachel.vue'
import DiensteKachel from '../components/wall/DiensteKachel.vue'
import FlowAgentKachel from '../components/wall/FlowAgentKachel.vue'
import GithubKachel from '../components/wall/GithubKachel.vue'
import HandlungsbedarfKachel from '../components/wall/HandlungsbedarfKachel.vue'
import HostsKachel from '../components/wall/HostsKachel.vue'
import KiraKachel from '../components/wall/KiraKachel.vue'
import SitzungenKachel from '../components/wall/SitzungenKachel.vue'
import WerkstattKachel from '../components/wall/WerkstattKachel.vue'

const REFRESH_MS = 30_000
const VERLAUF_MS = 5 * 60_000
const overview = ref<Overview | null>(null)
const verlauf = ref<VerlaufAntwort | null>(null)
const werkstattAlle = ref(false)
const error = ref<string | null>(null)
const ladeStand = ref(0) // 0..1 Fortschritt bis zum naechsten Refresh
const uhr = ref('')
const demoBusy = ref(false)
const demoMeldung = ref<string | null>(null)
const poll = usePollStore()
const toast = useToastStore()
const reduziert = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

let letzterLoad = Date.now()
let uhrTimer: number | undefined
let standTimer: number | undefined

async function load() {
  try {
    overview.value = await getOverview()
    error.value = null
    letzterLoad = Date.now()
  } catch (err) {
    error.value = extractError(err)
  }
}

function tick() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  const tage = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
  uhr.value = `${tage[d.getDay()]} ${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} · ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  ladeStand.value = Math.min(1, (Date.now() - letzterLoad) / REFRESH_MS)
  seitLoad.value = Math.floor((Date.now() - letzterLoad) / 1000)
}

onMounted(() => {
  // Schriften nur für das Cockpit (Google Fonts, mit Fallback-Stack im CSS)
  if (!document.getElementById('wall-fonts')) {
    const l = document.createElement('link')
    l.id = 'wall-fonts'
    l.rel = 'stylesheet'
    l.href = 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap'
    document.head.appendChild(l)
  }
  poll.start('wall', load, REFRESH_MS)
  poll.start('wall-verlauf', async () => { try { verlauf.value = await getVerlauf(24) } catch { /* Verlauf ist Beiwerk */ } }, VERLAUF_MS)
  tick()
  uhrTimer = window.setInterval(tick, 1000)
  window.addEventListener('keydown', tasten)
})
onBeforeUnmount(() => {
  poll.stop('wall')
  poll.stop('wall-verlauf')
  if (uhrTimer) window.clearInterval(uhrTimer)
  if (standTimer) window.clearInterval(standTimer)
  window.removeEventListener('keydown', tasten)
})

function tasten(e: KeyboardEvent) {
  const ziel = e.target
  if (e.metaKey || e.ctrlKey || e.altKey) return
  if (ziel instanceof HTMLInputElement || ziel instanceof HTMLTextAreaElement || ziel instanceof HTMLSelectElement || (ziel instanceof HTMLElement && ziel.isContentEditable)) return
  if (e.key === 'f' || e.key === 'F') vollbild()
  if (e.key === 'r' || e.key === 'R') void load()
}
function vollbild() {
  const el = document.documentElement
  if (!document.fullscreenElement) el.requestFullscreen?.()
  else document.exitFullscreen?.()
}

// ---------------------------------------------------------------- Zahlen
const de = new Intl.NumberFormat('de-DE')
function zahl(v: number | string | null | undefined): string {
  if (v == null || v === '') return '–'
  return typeof v === 'number' ? de.format(v) : String(v)
}
function gb(mb: number | null | undefined): string {
  return mb == null ? '–' : `${(mb / 1024).toFixed(mb >= 10240 ? 0 : 1).replace('.', ',')} GB`
}
function tage(s: number | null | undefined): string {
  if (s == null) return '–'
  const d = Math.floor(s / 86400)
  return d >= 1 ? `${d} Tage` : `${Math.floor(s / 3600)} h`
}
function bytes(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(1).replace('.', ',')} GB`
  if (b >= 1e6) return `${Math.round(b / 1e6)} MB`
  return `${Math.round(b / 1e3)} kB`
}
function relativ(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 90) return 'gerade eben'
  if (diff < 3600) return `vor ${Math.round(diff / 60)} Min.`
  if (diff < 86400) return `vor ${Math.round(diff / 3600)} h`
  return `vor ${Math.round(diff / 86400)} Tagen`
}
function stundeMinute(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** Hochzaehlende Kennzahl: animiert vom alten zum neuen Wert (ohne bei reduzierter Bewegung). */
function useCountUp(quelle: () => number | null) {
  const anzeige = ref<number | null>(quelle())
  let raf = 0
  watch(quelle, (neu) => {
    const alt = anzeige.value
    if (neu == null || alt == null || reduziert) { anzeige.value = neu; return }
    const start = performance.now(); const dauer = 900
    cancelAnimationFrame(raf)
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / dauer); const e = 1 - Math.pow(1 - k, 3)
      anzeige.value = Math.round(alt + (neu - alt) * e)
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  })
  return anzeige
}

// ---------------------------------------------------------------- Ableitungen
const hosts = computed(() => overview.value?.hosts ?? [])
const selbst = computed(() => hosts.value.find((h) => h.is_self) ?? hosts.value[0] ?? null)
const andere = computed(() => hosts.value.filter((h) => h !== selbst.value))
const projekte = computed(() => overview.value?.projects ?? [])
const projekteJeHost = computed(() => {
  const m: Record<string, WallProject[]> = {}
  for (const p of projekte.value) (m[p.host] ||= []).push(p)
  return m
})
const oeffentlich = computed(() => {
  const seen = new Map<string, WallProject>()
  for (const p of projekte.value) if (p.url && !seen.has(p.url)) seen.set(p.url, p)
  return [...seen.values()]
})
const tunnelAnzahl = computed(() => projekte.value.filter((p) => p.tunnel).length)
/** Cloudflare-Kasten: geprüfte Dienste (Live-Status), sonst die entdeckten Projekte mit Adresse. */
const cloudListe = computed<{ host: string; klasse: string; ms: number | null }[]>(() => {
  const d = overview.value?.dienste ?? []
  if (d.length) return d.map((x) => ({ host: x.host, klasse: x.ok ? (x.ms != null && x.ms > 3000 ? 'warn' : 'ok') : 'krit', ms: x.ms }))
  return oeffentlich.value.map((p) => ({ host: (p.url || '').replace(/^https?:\/\//, ''), klasse: statusKlasse(p.status), ms: null }))
})
const hero = computed(() => overview.value?.hero ?? null)
const heroProjekt = computed(() => hero.value?.project_state ?? null)
const heroKpis = computed(() => hero.value?.kpis ?? [])
const kpiWerte = [0, 1, 2, 3].map((i) => useCountUp(() => {
  const k = heroKpis.value[i]
  return k && typeof k.value === 'number' ? k.value : null
}))
const gesamtContainer = useCountUp(() => hosts.value.reduce((s, h) => s + (h.stats.containers ?? 0), 0) || null)
const commitAnzahl = useCountUp(() => overview.value?.github.commits.length ?? null)

// Landschaft: Positionen im 1600x900-Koordinatensystem
const MITTE = { x: 800, y: 455 }
const knoten = computed(() => {
  const list: { host: WallHost; x: number; y: number; r: number }[] = []
  if (selbst.value) list.push({ host: selbst.value, x: MITTE.x, y: MITTE.y, r: 122 })
  const n = andere.value.length
  const abstand = n <= 2 ? 300 : 210
  andere.value.forEach((h, i) => {
    const versatz = i - (n - 1) / 2 // -1 … +1 um die Mitte
    const y = Math.round(MITTE.y - 100 + versatz * abstand)
    const x = Math.round(1240 - Math.abs(versatz) * 70)
    list.push({ host: h, x, y, r: n > 4 ? 66 : 82 })
  })
  return list
})
const kanten = computed(() => {
  const k: { x1: number; y1: number; x2: number; y2: number; fluss: boolean }[] = []
  const mitte = knoten.value[0]
  if (!mitte) return k
  for (const kn of knoten.value.slice(1)) {
    const llm = kn.host.projects.some((p) => /ai-router|ollama|llm/i.test(p)) || /evo/i.test(kn.host.name)
    k.push({ x1: mitte.x, y1: mitte.y, x2: kn.x, y2: kn.y, fluss: llm })
  }
  return k
})
function statusKlasse(s: string | null | undefined): string {
  if (s === 'healthy' || s === 'online' || s === 'ok') return 'ok'
  if (s === 'degraded' || s === 'ssh-down' || s === 'warn') return 'warn'
  if (s === 'down' || s === 'offline' || s === 'unreachable' || s === 'krit') return 'krit'
  return 'unbekannt'
}
function statusText(s: string | null | undefined): string {
  const m: Record<string, string> = { healthy: 'läuft', online: 'online', degraded: 'teilweise', down: 'aus', offline: 'offline', unreachable: 'nicht erreichbar', 'ssh-down': 'SSH aus', unknown: 'unbekannt', ok: 'ok', warn: 'prüfen', krit: 'kritisch' }
  return m[s ?? 'unknown'] ?? (s ?? 'unbekannt')
}
const tickerText = computed(() => {
  const ev = overview.value?.events ?? []
  const teile: string[] = []
  for (const a of alerts.value.filter((x) => x.level !== 'info')) teile.push(`${a.level === 'krit' ? '⚠' : '△'} ${a.text}`)
  for (const k of (kira.value?.entries ?? []).slice(0, 3)) teile.push(`✦ Kira · ${kategorie(k.category)}: ${k.text.length > 110 ? k.text.slice(0, 109) + '…' : k.text}`)
  const faMeldungen: string[] = []
  const offline = flowAgent.value?.meldungen.hosts_offline ?? []
  if (offline.length) faMeldungen.push(`${offline.join(', ')} offline`)
  const ungesund = flowAgent.value?.frische.unhealthy ?? 0
  if (ungesund > 0) faMeldungen.push(`${ungesund} ${ungesund === 1 ? 'Frischeprüfung kritisch' : 'Frischeprüfungen kritisch'}`)
  if (faMeldungen.length) teile.push(`✦ flow-agent: ${faMeldungen.join(' · ')}`)
  for (const e of ev) teile.push(`${e.kind === 'commit' ? '⌥' : e.kind === 'deploy' ? '⇪' : '•'} ${stundeMinute(e.ts)} ${e.text}`)
  return teile.length ? teile.join('   ·   ') : 'Keine Ereignisse'
})
/** Laufzeit des Laufbands: rund 6 Zeichen je Sekunde, mindestens 90 s. */
const tickerDauer = computed(() => Math.max(90, Math.round((tickerText.value.length * 2) / 6)))
const repos = computed(() => [...(overview.value?.github.repos ?? [])].sort((a, b) => (b.pushed_at || '').localeCompare(a.pushed_at || '')))
const repoByName = computed(() => new Map(repos.value.map((r) => [r.name.toLowerCase(), r])))
function repoUrl(name: string): string | null { return repoByName.value.get(name.toLowerCase())?.html_url ?? null }
const alerts = computed(() => overview.value?.alerts ?? [])
const kritAnzahl = computed(() => alerts.value.filter((a) => a.level === 'krit').length)
const warnAnzahl = computed(() => alerts.value.filter((a) => a.level === 'warn').length)
const dienste = computed(() => overview.value?.dienste ?? [])
const diensteOk = computed(() => dienste.value.filter((d) => d.ok).length)
const tlsMin = computed(() => {
  const tage = dienste.value.map((d) => d.tls_tage).filter((t): t is number => t != null)
  return tage.length ? Math.min(...tage) : null
})
const werkstattHosts = computed(() => overview.value?.werkstatt ?? [])
const werkstattAlleRepos = computed(() =>
  werkstattHosts.value
    .flatMap((w) => w.repos.map((r) => ({ ...r, host: w.host })))
    .sort((a, b) => aktivitaet(b) - aktivitaet(a)),
)
const werkstattRepos = computed(() => {
  const alle = werkstattAlleRepos.value
  const aktive = alle.filter((r) => r.aktiv !== false)
  return (werkstattAlle.value ? alle : aktive).slice(0, werkstattAlle.value ? 60 : 9)
})
const werkstattAeltere = computed(() => werkstattAlleRepos.value.filter((r) => r.aktiv === false).length)
const naechsterSchritt = computed(() => werkstattAlleRepos.value.find((r) => r.pause && r.next_step) ?? null)
/** tmux-Sitzungen aller Hosts, angehängte zuerst. */
const sitzungen = computed(() =>
  hosts.value
    .flatMap((h) => (h.tmux ?? []).map((t) => ({ ...t, host: h.name })))
    .sort((a, b) => Number(b.attached) - Number(a.attached) || (b.created ?? 0) - (a.created ?? 0)),
)
function reihe(key: string): number[] {
  const s = verlauf.value?.series[key]
  return s ? s.map((p) => p[1]) : []
}
/** Verlaufslinie als SVG-Pfad (0..100 × 0..30). */
function linie(werte: number[]): string {
  if (werte.length < 2) return ''
  const min = Math.min(...werte); const max = Math.max(...werte); const span = max - min || 1
  return werte.map((v, i) => `${i === 0 ? 'M' : 'L'} ${((i / (werte.length - 1)) * 100).toFixed(1)} ${(28 - ((v - min) / span) * 26 + 1).toFixed(1)}`).join(' ')
}
function kpiKey(label: string): string {
  return 'hero.' + label.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
}
// Sitzungen: aufgeklapptes Fenster mit Terminalausgabe und Arbeitspaket-Versand
const offenesFenster = ref<string | null>(null)
const fensterAusgabe = ref('')
const fensterLaden = ref(false)
const paket = ref('')
const paketBestaetigen = ref(false)
const paketBusy = ref(false)
let paketTimer: number | undefined
async function fensterOeffnen(host: string, ziel: string) {
  const key = `${host}|${ziel}`
  if (offenesFenster.value === key) { offenesFenster.value = null; return }
  offenesFenster.value = key
  paketBestaetigen.value = false
  await ausgabeLaden(host, ziel)
}
async function ausgabeLaden(host: string, ziel: string) {
  fensterLaden.value = true
  try { fensterAusgabe.value = (await tmuxAusgabe(host, ziel)).text } catch (err) { fensterAusgabe.value = `Ausgabe nicht abrufbar: ${extractError(err)}` } finally { fensterLaden.value = false }
}
async function paketSenden(host: string, ziel: string) {
  const text = paket.value.trim()
  if (!text) return
  if (!paketBestaetigen.value) {
    paketBestaetigen.value = true
    window.clearTimeout(paketTimer)
    paketTimer = window.setTimeout(() => { paketBestaetigen.value = false }, 5000)
    return
  }
  paketBusy.value = true
  try {
    await tmuxSenden(host, ziel, text)
    toast.success(`Arbeitspaket an ${ziel} auf ${host} gesendet`)
    paket.value = ''
    paketBestaetigen.value = false
    window.setTimeout(() => void ausgabeLaden(host, ziel), 1500)
  } catch (err) { toast.error(extractError(err)) } finally { paketBusy.value = false }
}
function seit(created: number | null): string {
  return created ? relativ(new Date(created * 1000).toISOString()) : ''
}
function aktivitaet(r: { last_commit: string | null; pause: string | null }): number {
  return Math.max(r.last_commit ? new Date(r.last_commit).getTime() : 0, r.pause ? new Date(r.pause).getTime() : 0)
}
const werkstattSumme = computed(() => {
  const w = werkstattHosts.value
  if (!w.length) return 'kein Projektverzeichnis'
  const aktiv = werkstattAlleRepos.value.filter((r) => r.aktiv !== false).length
  const pausen = w.reduce((n, h) => n + h.pausen, 0)
  return `${aktiv} aktiv in 14 Tagen · ${pausen} ${pausen === 1 ? 'Pause' : 'Pausen'} · ${werkstattAlleRepos.value.length} Repos`
})
const kira = computed(() => overview.value?.kira ?? null)
const flowAgent = computed(() => overview.value?.flow_agent ?? null)
const KATEGORIE: Record<string, string> = { architecture: 'Architektur', solution: 'Lösung', problem: 'Problem', reference: 'Referenz', pattern: 'Muster', workflow: 'Ablauf', preference: 'Präferenz', feedback: 'Feedback' }
function kategorie(k: string | null): string { return (k && KATEGORIE[k]) || k || '–' }
function flowStatusKlasse(status: string): string {
  if (status === 'healthy') return 'ok'
  if (status === 'offline' || status === 'unhealthy') return 'krit'
  return 'warn'
}
function flowAlter(sekunden: number | null): string {
  if (sekunden == null) return 'Alter unbekannt'
  if (sekunden < 60) return `vor ${Math.max(0, Math.floor(sekunden))} s`
  if (sekunden < 3600) return `vor ${Math.floor(sekunden / 60)} min`
  return `vor ${Math.floor(sekunden / 3600)} h`
}
function flowVersion(version: string | null): string { return version ? (version.startsWith('v') ? version : `v${version}`) : 'Version unbekannt' }
function gpuLast(gpus: { util_pct: number }[]): number {
  return gpus.length ? Math.round(gpus.reduce((a, g) => a + g.util_pct, 0) / gpus.length) : 0
}
function hoehe(v: number, reihe: number[]): number {
  const m = Math.max(1, ...reihe)
  return Math.max(1, Math.round((v / m) * 17))
}
const seitLoad = ref(0)

const demoLink = ref<string | null>(null)
const demoSekunden = ref(0)
let demoTimer: number | undefined

async function demo(neu = false) {
  if (!hero.value || demoBusy.value) return
  const ziel = `${hero.value.url.replace(/\/$/, '')}${hero.value.demo_path}`
  if (!hero.value.demo_ready) {
    window.location.assign(ziel)
    return
  }
  demoBusy.value = true
  demoLink.value = null
  demoSekunden.value = 0
  demoTimer = window.setInterval(() => { demoSekunden.value += 1 }, 1000)
  demoMeldung.value = neu ? 'Demo wird zurückgesetzt und neu aufgebaut – danach öffnet sich das Portal in diesem Fenster' : 'Demo wird geprüft – fehlt sie, wird sie aufgebaut (1–2 Minuten)'
  try {
    const res = await startDemo(neu)
    const url = res.url || ziel
    demoLink.value = url
    demoMeldung.value = res.uebersprungen
      ? `${res.faelle.length} Demo-Fälle stehen bereits – Portal wird geöffnet …`
      : (res.ok ? `${res.faelle.length} Demo-Fälle aufgebaut (${demoSekunden.value} s) – Portal wird geöffnet …` : 'Aufbau mit Fehlern – Portal wird geöffnet …')
    // Kein neues Fenster: Das Portal ersetzt das Cockpit in diesem Tab (Zurück führt zum Cockpit).
    window.setTimeout(() => window.location.assign(url), 800)
  } catch (err) {
    demoMeldung.value = `Fehler: ${extractError(err)}`
    toast.error(extractError(err))
  } finally {
    demoBusy.value = false
    if (demoTimer) window.clearInterval(demoTimer)
  }
}
</script>

<template>
  <div class="wand" :class="{ reduziert }">
    <header class="wand-kopf">
      <div class="titel">
        <span class="marke">flowaudit</span>
        <span class="untertitel">Cockpit</span>
      </div>
      <div class="kopf-mitte">
        <span v-if="error" class="fehler">{{ error }}</span>
      </div>
      <div class="kopf-rechts">
        <span class="live" :title="`Alle ${REFRESH_MS / 1000} s aktualisiert · R = sofort`"><i :class="['punkt', error ? 'krit' : 'ok']" />{{ error ? 'GESTÖRT' : 'LIVE' }}<em>· {{ seitLoad }} s</em></span>
        <span class="mono uhr">{{ uhr }}</span>
        <RouterLink to="/chat" class="knopf klein">LLM-Konsole</RouterLink>
        <RouterLink to="/kanban" class="knopf klein ghost">Aufträge</RouterLink>
        <RouterLink to="/kompakt" class="knopf klein ghost" title="Handy-Ansicht">Kompakt</RouterLink>
        <RouterLink to="/" class="knopf klein ghost">Admin</RouterLink>
        <button class="knopf klein ghost" title="Vollbild (F)" @click="vollbild">⛶</button>
      </div>
      <div class="lade-balken"><i :style="{ width: `${ladeStand * 100}%` }" /></div>
    </header>

    <!-- ============================ Landschaft ============================ -->
    <section class="landschaft" aria-label="Cockpit-Karte">
      <div class="legende mono">
        <span><i class="strich mesh" /> Mesh (Tailscale)</span>
        <span><i class="strich fluss" /> Verkehr</span>
        <span><i class="punkt ok" /> läuft</span>
        <span><i class="punkt warn" /> teilweise</span>
        <span><i class="punkt krit" /> aus</span>
      </div>
      <svg v-if="overview" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid meet" class="karte">
        <defs>
          <radialGradient id="glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#2A3F80" stop-opacity=".55" />
            <stop offset="100%" stop-color="#0B1020" stop-opacity="0" />
          </radialGradient>
          <linearGradient id="sweep" gradientUnits="userSpaceOnUse" :x1="MITTE.x + 330" :y1="MITTE.y" :x2="MITTE.x + 330 * Math.cos(0.75)" :y2="MITTE.y + 330 * Math.sin(0.75)">
            <stop offset="0%" stop-color="#F2B84B" stop-opacity="0" />
            <stop offset="100%" stop-color="#F2B84B" stop-opacity=".16" />
          </linearGradient>
        </defs>
        <circle :cx="MITTE.x" :cy="MITTE.y" r="330" fill="url(#glow)" />
        <!-- Radar-Sweep um den Self-Host -->
        <g class="radar" :style="{ transformOrigin: `${MITTE.x}px ${MITTE.y}px` }">
          <path :d="`M ${MITTE.x} ${MITTE.y} L ${MITTE.x + 330} ${MITTE.y} A 330 330 0 0 1 ${(MITTE.x + 330 * Math.cos(0.75)).toFixed(1)} ${(MITTE.y + 330 * Math.sin(0.75)).toFixed(1)} Z`" fill="url(#sweep)" />
        </g>

        <!-- Cloudflare-Rand -->
        <g class="einblenden" style="--i: 0">
          <rect class="cloud" x="70" y="290" width="280" height="330" rx="18" />
          <text class="label" x="102" y="332">Cloudflare</text>
          <text class="sub" x="102" y="352">*.flowaudit.de · TLS · Tunnel</text>
          <template v-for="(d, i) in cloudListe.slice(0, 9)" :key="d.host">
            <circle :cx="106" :cy="380 + i * 22" r="4" :class="['dot', d.klasse]" />
            <text class="app" :x="118" :y="384 + i * 22">{{ d.host }}</text>
            <text v-if="d.ms != null" class="sub" :x="330" :y="384 + i * 22" text-anchor="end">{{ d.ms }} ms</text>
          </template>
          <text class="sub" x="102" y="598">{{ tunnelAnzahl }} Tunnel · {{ cloudListe.length }} öffentliche Dienste</text>
        </g>

        <!-- Mesh-Kanten mit laufenden Paketen -->
        <line v-for="(k, i) in kanten" :key="'k' + i" :x1="k.x1" :y1="k.y1" :x2="k.x2" :y2="k.y2" class="kante" />
        <template v-if="!reduziert">
          <template v-for="(k, i) in kanten" :key="'p' + i">
            <circle r="3.5" class="paket"><animateMotion :dur="`${3.2 + i * 0.6}s`" repeatCount="indefinite" :path="`M ${k.x1} ${k.y1} L ${k.x2} ${k.y2}`" /></circle>
            <circle r="2.5" class="paket zurueck"><animateMotion :dur="`${4.1 + i * 0.5}s`" :begin="`${1 + i * 0.4}s`" repeatCount="indefinite" :path="`M ${k.x2} ${k.y2} L ${k.x1} ${k.y1}`" /></circle>
          </template>
          <circle r="4" class="paket cloud-paket"><animateMotion dur="2.6s" repeatCount="indefinite" :path="`M 350 455 C 500 455, 560 ${MITTE.y}, ${MITTE.x - 130} ${MITTE.y}`" /></circle>
        </template>
        <!-- Verkehr Cloudflare -> Self-Host -->
        <path v-if="knoten.length" class="fluss" :d="`M 350 455 C 500 455, 560 ${MITTE.y}, ${MITTE.x - 130} ${MITTE.y}`" />
        <!-- Verkehr Self -> LLM-Host -->
        <template v-for="(k, i) in kanten" :key="'f' + i">
          <line v-if="k.fluss" :x1="k.x1" :y1="k.y1" :x2="k.x2" :y2="k.y2" class="fluss langsam" />
        </template>

        <!-- Knoten -->
        <g v-for="(kn, i) in knoten" :key="kn.host.name" class="einblenden host" :style="{ '--i': i + 1 }">
          <circle :cx="kn.x" :cy="kn.y" :r="kn.r" :class="['knoten', { hero: kn.host.is_self, aus: statusKlasse(kn.host.status) !== 'ok' }]" />
          <circle :cx="kn.x" :cy="kn.y" :r="kn.r + 10" :class="['ring', statusKlasse(kn.host.status)]" />
          <text class="label" :x="kn.x" :y="kn.y - kn.r * 0.42" text-anchor="middle" :style="{ fontSize: kn.host.is_self ? '28px' : '19px' }">{{ kn.host.name }}</text>
          <text class="sub" :x="kn.x" :y="kn.y - kn.r * 0.42 + 20" text-anchor="middle" :style="{ fontSize: kn.host.is_self ? '11.5px' : '10px' }">
            {{ kn.host.stats.cpus ? `${kn.host.stats.cpus} vCPU · ` : '' }}{{ kn.host.stats.mem_total_mb ? `${gb(kn.host.stats.mem_total_mb)} · ` : '' }}{{ kn.host.stats.gpus?.length ? `${kn.host.stats.gpus.length} GPU ${gpuLast(kn.host.stats.gpus)} % · ` : '' }}{{ kn.host.stats.containers != null ? `${kn.host.stats.containers} Ctr.` : (kn.host.description || statusText(kn.host.status)).slice(0, 34) }}
          </text>
          <template v-for="(p, j) in (projekteJeHost[kn.host.name] || []).slice(0, kn.host.is_self ? 4 : 2)" :key="p.name">
            <circle :cx="kn.x - 62" :cy="kn.y - kn.r * 0.42 + 44 + j * 20 - 4" r="4" :class="['dot', statusKlasse(p.status)]" />
            <text class="app" :x="kn.x - 52" :y="kn.y - kn.r * 0.42 + 44 + j * 20">{{ p.title.length > 26 ? p.title.slice(0, 25) + '…' : p.title }}</text>
          </template>
          <text class="sub" :x="kn.x" :y="kn.y + kn.r - 16" text-anchor="middle">
            <template v-if="kn.host.stats.load1 != null">Load {{ String(kn.host.stats.load1).replace('.', ',') }} · RAM {{ Math.round(kn.host.stats.mem_pct ?? 0) }} % · Disk {{ Math.round(kn.host.stats.disk_pct ?? 0) }} %</template>
            <template v-else>{{ statusText(kn.host.status) }}</template>
          </text>
        </g>

        <!-- Hero-Karte -->
        <g v-if="hero" class="einblenden" style="--i: 6">
          <rect x="440" y="672" width="720" height="168" rx="12" class="hero-karte" />
          <text class="label" x="466" y="712" style="font-size: 30px">{{ hero.title }}</text>
          <text class="sub" x="466" y="734">{{ hero.url.replace(/^https?:\/\//, '') }} · {{ heroProjekt ? `${heroProjekt.running}/${heroProjekt.containers} Container · ${statusText(heroProjekt.status)}` : 'nicht entdeckt' }}{{ heroProjekt?.deploy ? ` · Deploy ${heroProjekt.deploy.git_sha} ${relativ(heroProjekt.deploy.ts)}` : '' }}</text>
          <template v-for="(k, i) in heroKpis.slice(0, 4)" :key="k.label">
            <text class="kpi" :x="466 + i * 138" y="790"><tspan :key="String(k.value)" class="blitz">{{ zahl(kpiWerte[i].value ?? k.value) }}</tspan></text>
            <text class="sub" :x="466 + i * 138" y="812">{{ k.label }}</text>
            <svg v-if="reihe(kpiKey(k.label)).length > 1" :x="466 + i * 138" y="818" width="118" height="18" viewBox="0 0 100 30" preserveAspectRatio="none"><path :d="linie(reihe(kpiKey(k.label)))" class="verlauf" /></svg>
          </template>
          <text v-if="!heroKpis.length" class="sub" x="466" y="790">{{ hero.probe_note ? `Kennzahlen: ${hero.probe_note}` : 'Kennzahlen folgen mit der Sonde' }}</text>
          <a :href="hero.url" target="_blank" rel="noopener"><rect x="1010" y="690" width="126" height="36" rx="6" class="knopf-svg ghost" /><text x="1073" y="714" text-anchor="middle" class="knopf-text ghost">Öffnen ↗</text></a>
          <g class="klickbar" @click="demo(false)"><rect x="1010" y="736" width="126" height="36" rx="6" :class="['knopf-svg', { busy: demoBusy }]" /><text x="1073" y="760" text-anchor="middle" class="knopf-text">{{ demoBusy ? `läuft · ${demoSekunden} s` : 'Demo starten' }}</text></g>
          <text v-if="!demoBusy && !demoLink" class="sub klickbar" x="1073" y="794" text-anchor="middle" style="text-decoration: underline" @click="demo(true)"><title>Demo zurücksetzen: alle fünf Fälle neu aufbauen (1–2 Minuten)</title>Zurücksetzen</text>
          <a v-if="demoLink && !demoBusy" :href="demoLink"><rect x="1010" y="782" width="126" height="32" rx="6" class="knopf-svg ghost" /><text x="1073" y="803" text-anchor="middle" class="knopf-text ghost">Portal öffnen</text></a>
          <text v-if="demoMeldung" class="sub" x="466" y="832">{{ demoMeldung }}{{ demoBusy ? ' (etwa 1–2 Minuten)' : '' }}</text>
        </g>
      </svg>
      <div v-else class="warte mono">{{ error ? error : 'Lade Cockpit …' }}</div>
    </section>

    <!-- ============================ Leitstand ============================ -->
    <section v-if="overview" class="leitstand" aria-label="Cockpit">
      <HandlungsbedarfKachel :alerts="alerts" :krit-anzahl="kritAnzahl" :warn-anzahl="warnAnzahl" />
      <DiensteKachel :dienste="dienste" :dienste-ok="diensteOk" :tls-min="tlsMin" :zahl="zahl" :hoehe="hoehe" />
      <WerkstattKachel :repos="werkstattRepos" :summe="werkstattSumme" :naechster-schritt="naechsterSchritt" :aeltere="werkstattAeltere" :alle="werkstattAlle" :repo-url="repoUrl" :relativ="relativ" @umschalten="werkstattAlle = !werkstattAlle" />
      <SitzungenKachel v-model:paket="paket" :sitzungen="sitzungen" :offenes-fenster="offenesFenster" :fenster-ausgabe="fensterAusgabe" :fenster-laden="fensterLaden" :paket-bestaetigen="paketBestaetigen" :paket-busy="paketBusy" :seit="seit" @fenster-oeffnen="fensterOeffnen" @ausgabe-laden="ausgabeLaden" @paket-senden="paketSenden" />
      <HostsKachel :hosts="hosts" :status-klasse="statusKlasse" :status-text="statusText" :tage="tage" :reihe="reihe" :linie="linie" :gb="gb" />

      <div class="kachel projekte einblenden" style="--i: 5">
        <h4>Projekte je Host <span class="dim">· automatisch aus Docker</span></h4>
        <div class="projekt-grid">
          <div v-for="p in projekte" :key="p.host + '/' + p.name" class="projekt" :title="(p.names || []).join(', ')">
            <div class="p-kopf"><i :class="['punkt', statusKlasse(p.status)]" /><b>{{ p.title }}</b><span class="mono dim">{{ p.host }}</span></div>
            <div class="mono dim p-sub">{{ p.running }}/{{ p.containers }} Container{{ p.deploy ? ` · ${p.deploy.git_sha} ${relativ(p.deploy.ts)}` : '' }}{{ p.app_status && p.app_status !== p.status ? ` · Health ${statusText(p.app_status)}` : '' }}</div>
            <a v-if="p.url" :href="p.url" target="_blank" rel="noopener" class="p-link mono">{{ p.url.replace(/^https?:\/\//, '') }} ↗</a>
            <div v-else-if="p.intern && p.intern.length" class="p-intern mono">
              <a v-for="i in p.intern" :key="i.url" :href="i.url" target="_blank" rel="noopener" class="p-link" :title="`${i.service} · Port ${i.port} (Tailscale)`">:{{ i.port }} {{ i.service }} ↗</a>
            </div>
          </div>
        </div>
      </div>

      <div class="kachel einblenden" style="--i: 6">
        <h4>Sonden</h4>
        <div v-for="s in overview.probes" :key="s.id" class="sonde">
          <div class="s-kopf"><i :class="['punkt', s.ok ? 'ok' : 'warn']" /><b>{{ s.label }}</b><span v-if="s.note" class="mono dim">{{ s.note }}</span></div>
          <div class="s-kpis"><span v-for="k in s.kpis" :key="k.label"><em class="kpi-klein">{{ zahl(k.value) }}</em><small>{{ k.label }}</small></span></div>
        </div>
        <div v-if="!overview.probes.length" class="dim">Keine Sonden konfiguriert.</div>
      </div>

      <BackupsKachel :backups="overview.backups" :stunde-minute="stundeMinute" :bytes="bytes" :relativ="relativ" />

      <div class="kachel einblenden" style="--i: 7">
        <h4>Lokale Modelle <span class="dim">· ai-router</span></h4>
        <div class="zeile"><span><i :class="['punkt', overview.ai_router.ok ? 'ok' : 'krit']" /><b>{{ overview.ai_router.freigegeben.length }} für die Konsole freigegeben</b></span><span class="mono dim">{{ overview.ai_router.model_count }} geladen · {{ overview.ai_router.url.replace(/^https?:\/\//, '') }}</span></div>
        <div class="modelle mono">{{ overview.ai_router.freigegeben.join(' · ') || 'Whitelist leer – in den Einstellungen freigeben' }}</div>
        <RouterLink to="/chat" class="knopf klein" style="margin-top: 8px; display: inline-block">LLM-Konsole öffnen</RouterLink>
      </div>

      <KiraKachel v-if="kira" :kira="kira" :zahl="zahl" :kategorie="kategorie" :relativ="relativ" />
      <FlowAgentKachel v-if="flowAgent" :flow-agent="flowAgent" :flow-version="flowVersion" :flow-status-klasse="flowStatusKlasse" :flow-alter="flowAlter" />
      <GithubKachel :github="overview.github" :repos="repos" :commit-anzahl="commitAnzahl" :zahl="zahl" :relativ="relativ" />
    </section>

    <footer class="ticker mono"><span :style="{ animationDuration: `${tickerDauer}s` }">{{ tickerText }}   ·   {{ tickerText }}</span></footer>
  </div>
</template>

<style scoped src="../components/wall/wallStyles.css"></style>
