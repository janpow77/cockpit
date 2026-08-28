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
      <div class="kachel alarm einblenden" :class="{ ruhig: !alerts.length, krit: kritAnzahl > 0 }" style="--i: 0">
        <h4>Handlungsbedarf <span class="dim">· {{ alerts.length ? `${kritAnzahl} kritisch · ${warnAnzahl} prüfen` : 'nichts offen' }}</span></h4>
        <div v-if="!alerts.length" class="ruhe"><i class="punkt ok" /><div><b>Alles läuft.</b><span class="mono dim">Hosts, Container, Sicherungen, Dienste und Zertifikate ohne Befund</span></div></div>
        <TransitionGroup v-else name="liste" tag="div" class="alarm-liste">
          <div v-for="a in alerts" :key="a.level + a.text" :class="['alarm-zeile', a.level]">
            <i :class="['punkt', a.level]" />
            <div class="a-text"><b>{{ a.text }}</b><span v-if="a.hint" class="mono dim">{{ a.hint }}</span></div>
            <a v-if="a.url" :href="a.url" target="_blank" rel="noopener" class="p-link mono">↗</a>
          </div>
        </TransitionGroup>
      </div>

      <div class="kachel dienste einblenden" style="--i: 1">
        <h4>Öffentliche Dienste <span class="dim">· {{ diensteOk }}/{{ dienste.length }} erreichbar{{ tlsMin != null ? ` · Zertifikate ≥ ${tlsMin} Tage` : '' }}</span></h4>
        <div v-for="d in dienste" :key="d.url" class="dienst">
          <i :class="['punkt', d.ok ? (d.ms != null && d.ms > 3000 ? 'warn' : 'ok') : 'krit']" />
          <a :href="d.url" target="_blank" rel="noopener" class="d-name" :title="d.note || d.url">{{ d.host }}</a>
          <span class="mono d-ms">{{ d.ms != null ? `${zahl(d.ms)} ms` : '–' }}</span>
          <span class="mono d-tls" :class="{ warn: d.tls_tage != null && d.tls_tage < 14 }" :title="d.tls_aussteller || ''">{{ d.tls_tage != null ? `TLS ${d.tls_tage} d` : (d.note || '') }}</span>
          <svg class="funken" viewBox="0 0 96 18" preserveAspectRatio="none" :title="d.requests_24h != null ? `${zahl(d.requests_24h)} Zugriffe in 24 h` : 'keine Verkehrsdaten'"><rect v-for="(v, i) in d.verlauf" :key="i" :x="i * 4" :y="18 - hoehe(v, d.verlauf)" width="3" :height="hoehe(v, d.verlauf)" :style="{ '--i': i }" /></svg>
          <span class="mono d-req">{{ d.requests_24h != null ? `${zahl(d.requests_24h)} / 24 h` : '' }}</span>
        </div>
        <div v-if="!dienste.length" class="dim">Keine öffentlichen Adressen hinterlegt.</div>
      </div>

      <div class="kachel werkstatt einblenden" style="--i: 2">
        <h4>Werkstatt <span class="dim">· {{ werkstattSumme }}</span></h4>
        <div v-if="naechsterSchritt" class="weiter"><span class="chip pause">⏸ {{ naechsterSchritt.name }}</span><b>Nächster Schritt:</b> {{ naechsterSchritt.next_step }}</div>
        <TransitionGroup name="liste" tag="div">
          <div v-for="r in werkstattRepos" :key="r.host + '/' + r.name" class="repo-zeile">
            <div class="r-kopf">
              <a v-if="repoByName.get(r.name.toLowerCase())" :href="repoByName.get(r.name.toLowerCase())!.html_url" target="_blank" rel="noopener" class="r-name" title="Repository auf GitHub öffnen">{{ r.name }} ↗</a>
              <b v-else>{{ r.name }}</b><span class="mono dim">{{ r.host }} · {{ r.branch }}</span>
              <span v-if="r.pause" class="chip pause" :title="`Pause seit ${relativ(r.pause)}`">⏸ Pause</span>
              <span v-else-if="r.dirty" class="chip dirty">{{ r.dirty }} ungesichert</span>
              <span v-else-if="r.ahead" class="chip ahead">{{ r.ahead }} nicht gepusht</span>
            </div>
            <div class="mono dim r-sub" :title="r.next_step || r.message">{{ r.next_step ? `→ ${r.next_step}` : (r.message || '—') }} · {{ relativ(r.pause || r.last_commit) }}</div>
          </div>
        </TransitionGroup>
        <div v-if="!werkstattRepos.length" class="dim">Kein Projektverzeichnis erreichbar.</div>
        <button v-if="werkstattAeltere" class="knopf klein ghost schalter" @click="werkstattAlle = !werkstattAlle">{{ werkstattAlle ? 'nur aktive zeigen' : `+ ${werkstattAeltere} ältere zeigen` }}</button>
      </div>

      <div class="kachel sitzungen einblenden" style="--i: 3">
        <h4>Sitzungen <span class="dim">· tmux · {{ sitzungen.length }} {{ sitzungen.length === 1 ? 'Sitzung' : 'Sitzungen' }}</span></h4>
        <div v-for="t in sitzungen.slice(0, 10)" :key="t.host + '/' + t.name" class="sitzung">
          <div class="s-kopf"><i :class="['punkt', t.attached ? 'ok' : 'unbekannt']" /><b>{{ t.name }}</b><span class="mono dim">{{ t.host }} · {{ t.windows.length }} {{ t.windows.length === 1 ? 'Fenster' : 'Fenster' }}{{ t.created ? ` · seit ${seit(t.created)}` : '' }}{{ t.attached ? ' · verbunden' : '' }}</span></div>
          <div class="fenster mono">
            <button v-for="f in t.windows.slice(0, 12)" :key="f.index ?? f.name" :class="['chip', 'klick', { aktiv: f.active, offen: offenesFenster === `${t.host}|${t.name}:${f.index ?? f.name}` }]" :title="`Fenster ${f.name || '#' + (f.index ?? '')} öffnen: Ausgabe und Arbeitspaket`" @click="fensterOeffnen(t.host, `${t.name}:${f.index ?? f.name}`)">{{ f.name || `#${f.index ?? ''}` }}<em v-if="f.cmd && f.cmd !== 'bash' && f.cmd !== 'zsh'"> · {{ f.cmd }}</em> ▸</button>
          </div>
          <template v-for="f in t.windows" :key="'p' + (f.index ?? f.name)">
            <div v-if="offenesFenster === `${t.host}|${t.name}:${f.index ?? f.name}`" class="terminal">
              <div class="t-kopf mono dim"><span>{{ t.host }} · {{ t.name }}:{{ f.name || '#' + (f.index ?? '') }}{{ f.cmd ? ` · ${f.cmd}` : '' }}</span><button class="knopf klein ghost" :disabled="fensterLaden" @click="ausgabeLaden(t.host, `${t.name}:${f.index ?? f.name}`)">{{ fensterLaden ? 'lädt …' : 'Ausgabe neu laden' }}</button></div>
              <pre class="t-ausgabe mono">{{ fensterAusgabe || '(leer)' }}</pre>
              <form class="t-senden" @submit.prevent="paketSenden(t.host, `${t.name}:${f.index ?? f.name}`)">
                <input v-model="paket" class="t-eingabe mono" placeholder="Arbeitspaket – wird in diesem Fenster eingetippt und mit Enter abgeschickt …" maxlength="2000" />
                <button type="submit" class="knopf klein" :class="{ warn: paketBestaetigen }" :disabled="paketBusy || !paket.trim()">{{ paketBusy ? 'sendet …' : paketBestaetigen ? 'Wirklich senden?' : 'Senden' }}</button>
              </form>
            </div>
          </template>
        </div>
        <div v-if="!sitzungen.length" class="dim">Keine tmux-Sitzungen sichtbar (Loopback-SSH des Self-Hosts nötig).</div>
      </div>

      <div class="kachel hosts einblenden" style="--i: 4">
        <h4>Hosts</h4>
        <div v-for="h in hosts" :key="h.name" class="host-zeile">
          <div class="hz-kopf"><span><i :class="['punkt', statusKlasse(h.status)]" /><b>{{ h.name }}</b> <span class="mono dim">{{ h.ip }}</span></span><span class="mono">{{ h.stats.containers != null ? `${h.stats.containers} Container` : statusText(h.status) }}</span></div>
          <div class="hz-sub mono dim">{{ h.description || '—' }}{{ h.stats.uptime_s ? ` · Uptime ${tage(h.stats.uptime_s)}` : '' }}</div>
          <div v-if="h.stats.ok" class="balken-reihe">
            <span class="mono dim">Load</span><div class="balken"><i :style="{ width: `${Math.min(100, ((h.stats.load1 ?? 0) / (h.stats.cpus || 1)) * 100)}%` }" /></div>
            <span class="mono dim">RAM</span><div class="balken"><i :style="{ width: `${h.stats.mem_pct ?? 0}%` }" /></div>
            <span class="mono dim">Disk</span><div class="balken"><i :class="{ warn: (h.stats.disk_pct ?? 0) > 80 }" :style="{ width: `${h.stats.disk_pct ?? 0}%` }" /></div>
          </div>
          <svg v-if="reihe(`host.${h.name}.load1`).length > 1" class="host-verlauf" viewBox="0 0 100 30" preserveAspectRatio="none"><path :d="linie(reihe(`host.${h.name}.load1`))" class="verlauf" /></svg>
          <div v-if="h.stats.gpus?.length" class="balken-reihe gpu">
            <template v-for="(g, gi) in h.stats.gpus" :key="gi"><span class="mono dim">GPU{{ h.stats.gpus!.length > 1 ? gi + 1 : '' }}</span><div class="balken" :title="g.mem_total_mb ? `${gb(g.mem_used_mb)} / ${gb(g.mem_total_mb)} VRAM` : ''"><i class="gpu" :style="{ width: `${g.util_pct}%` }" /></div></template>
          </div>
        </div>
      </div>

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

      <div class="kachel einblenden" style="--i: 7">
        <h4>Sicherungen</h4>
        <div v-for="b in overview.backups" :key="b.name" class="zeile"><span><i :class="['punkt', b.status]" /><b>{{ b.name }}</b></span><span class="mono">{{ stundeMinute(b.mtime) }} · {{ bytes(b.size_bytes) }} · {{ relativ(b.mtime) }}</span></div>
        <div v-if="!overview.backups.length" class="dim">Kein Sicherungsverzeichnis eingebunden.</div>
      </div>

      <div class="kachel einblenden" style="--i: 7">
        <h4>Lokale Modelle <span class="dim">· ai-router</span></h4>
        <div class="zeile"><span><i :class="['punkt', overview.ai_router.ok ? 'ok' : 'krit']" /><b>{{ overview.ai_router.freigegeben.length }} für die Konsole freigegeben</b></span><span class="mono dim">{{ overview.ai_router.model_count }} geladen · {{ overview.ai_router.url.replace(/^https?:\/\//, '') }}</span></div>
        <div class="modelle mono">{{ overview.ai_router.freigegeben.join(' · ') || 'Whitelist leer – in den Einstellungen freigeben' }}</div>
        <RouterLink to="/chat" class="knopf klein" style="margin-top: 8px; display: inline-block">LLM-Konsole öffnen</RouterLink>
      </div>

      <div v-if="kira" class="kachel kira einblenden" style="--i: 9">
        <h4>Kira · zuletzt gelernt <span class="dim">· {{ kira.total != null ? `${zahl(kira.total)} Einträge im Gedächtnis` : (kira.note || 'nicht erreichbar') }}{{ kira.host ? ` · ${kira.host}` : '' }}</span></h4>
        <TransitionGroup name="liste" tag="div">
          <div v-for="e in kira.entries.slice(0, 5)" :key="e.id || e.text" class="kira-zeile">
            <span class="chip kat">{{ kategorie(e.category) }}</span>
            <span class="k-text" :title="e.text">{{ e.text }}</span>
            <span class="mono dim">{{ e.project || '' }}{{ e.created_at ? ` · ${relativ(e.created_at)}` : '' }}</span>
          </div>
        </TransitionGroup>
        <div v-if="!kira.entries.length" class="dim">{{ kira.note || 'Noch keine Wissenseinträge.' }}</div>
      </div>

      <div v-if="flowAgent" class="kachel flow-agent einblenden" style="--i: 10">
        <h4><a v-if="flowAgent.url" :href="flowAgent.url" target="_blank" rel="noopener">flow-agent ↗</a><span v-else>flow-agent</span> <span class="dim">{{ flowAgent.ok ? `· Control Plane ok · ${flowVersion(flowAgent.version)} · ${flowAgent.hosts.length} Hosts` : `· ${flowAgent.note || 'nicht erreichbar'}` }}</span></h4>
        <div class="flow-hosts">
          <div v-for="h in flowAgent.hosts" :key="h.host" class="flow-hostzeile">
            <i :class="['punkt', flowStatusKlasse(h.status)]" />
            <div class="flow-name"><b>{{ h.host }}</b><span v-if="h.hostname && h.hostname !== h.host" class="mono dim">{{ h.hostname }}</span></div>
            <span class="flow-metrik mono">{{ h.projekte }} Projekte · {{ h.container }} Container · {{ h.gpu }} GPU</span>
            <div class="flow-chips"><span v-for="werkzeug in h.werkzeuge_fehlen.slice(0, 5)" :key="werkzeug" class="chip dim">{{ werkzeug }} fehlt</span><span v-if="h.tmux !== 'healthy'" class="chip dim">tmux: {{ h.tmux || '–' }}</span></div>
            <span class="flow-alter mono" :class="{ warn: h.alter_s != null && h.alter_s > 300 }">{{ flowAlter(h.alter_s) }}</span>
          </div>
        </div>
        <div class="flow-frische"><b>Frische:</b> {{ flowAgent.frische.healthy }} ok · {{ flowAgent.frische.degraded }} eingeschränkt · {{ flowAgent.frische.unhealthy }} kritisch</div>
        <div v-for="(befund, index) in flowAgent.frische.befunde.slice(0, 5)" :key="`${befund.host}-${befund.label}-${index}`" class="flow-befund" :class="{ ungesund: befund.status === 'unhealthy' }">⚠ {{ befund.label }} · {{ befund.host }} — {{ befund.detail }}</div>
        <div class="flow-aktionen mono" :class="{ offen: flowAgent.meldungen.pending_actions > 0 || flowAgent.meldungen.failed_actions_recent > 0 }"><template v-if="flowAgent.meldungen.pending_actions > 0 || flowAgent.meldungen.failed_actions_recent > 0">Aktionen: {{ flowAgent.meldungen.pending_actions }} {{ flowAgent.meldungen.pending_actions === 1 ? 'wartet' : 'warten' }} auf Freigabe · {{ flowAgent.meldungen.failed_actions_recent }} fehlgeschlagen</template><template v-else>Keine offenen Aktionen</template></div>
      </div>

      <div class="kachel github einblenden" style="--i: 11">
        <h4>GitHub <span class="dim">· {{ overview.github.enabled ? `alle ${overview.github.repos.length} Repositories · nach Aktivität · ${zahl(commitAnzahl)} Commits zuletzt` : 'kein Token' }}</span></h4>
        <div v-if="!overview.github.enabled" class="dim">GITHUB_TOKEN setzen, dann erscheinen hier alle Repos mit Aktivität.</div>
        <div v-else-if="overview.github.error" class="dim">{{ overview.github.error }}</div>
        <div v-else class="repo-grid">
          <a v-for="r in repos" :key="r.full_name" :href="r.html_url" target="_blank" rel="noopener" class="repo" :class="{ still: !r.pushed_at || Date.now() - new Date(r.pushed_at).getTime() > 90 * 86400000 }" :title="r.description || r.full_name">
            <b>{{ r.name }}</b><span class="mono dim">{{ r.language || '—' }} · {{ relativ(r.pushed_at) }}{{ r.open_issues ? ` · ${r.open_issues} offen` : '' }}</span>
          </a>
        </div>
      </div>
    </section>

    <footer class="ticker mono"><span :style="{ animationDuration: `${tickerDauer}s` }">{{ tickerText }}   ·   {{ tickerText }}</span></footer>
  </div>
</template>

<style scoped>
.wand {
  --grund: #0B1020; --flaeche: #131A2E; --flaeche-2: #1A2340; --linie: #263054;
  --text: #E7ECF7; --text-2: #AAB3CF; --text-3: #7F89AB; --akzent: #F2B84B;
  --ok: #4CC38A; --warn: #F2B84B; --krit: #F26D6D; --info: #6FA8FF;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  min-height: 100vh; background: var(--grund); color: var(--text); font-family: var(--body);
  display: flex; flex-direction: column;
}
.mono { font-family: var(--mono); }
.dim { color: var(--text-3); }
.wand-kopf { position: relative; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 14px 26px 16px; border-bottom: 1px solid var(--linie); gap: 16px; }
.titel .marke { font-family: var(--display); font-size: 28px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.titel .untertitel { margin-left: 12px; font-family: var(--mono); font-size: 12px; letter-spacing: .14em; color: var(--text-3); text-transform: uppercase; }
.kopf-mitte { text-align: center; font-size: 13px; }
.kopf-rechts { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
.uhr { font-size: 15px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.fehler { color: var(--krit); font-family: var(--mono); font-size: 12px; }
.lade-balken { position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: transparent; }
.lade-balken i { display: block; height: 100%; background: var(--akzent); opacity: .7; transition: width 1s linear; }
.knopf { font-family: var(--display); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; background: var(--akzent); color: #1A1200; border: 1px solid var(--akzent); border-radius: 5px; padding: 8px 14px; font-size: 14px; cursor: pointer; text-decoration: none; }
.knopf.klein { padding: 6px 12px; font-size: 13px; }
.knopf.ghost { background: transparent; color: var(--text-2); border-color: var(--linie); }
.knopf:hover { filter: brightness(1.08); }

/* ---------- Landschaft ---------- */
.landschaft { position: relative; flex: 0 0 auto; height: min(62vh, 760px); background: radial-gradient(ellipse at 50% 45%, #12203F 0%, #070B18 72%); background-size: 120% 120%; border-bottom: 1px solid var(--linie); animation: atmen 24s ease-in-out infinite; }
@keyframes atmen { 0%, 100% { background-position: 50% 45%; } 50% { background-position: 52% 50%; } }
.karte { width: 100%; height: 100%; display: block; }
.legende { position: absolute; right: 22px; top: 14px; display: flex; gap: 16px; font-size: 11px; color: var(--text-3); z-index: 2; }
.legende .strich { display: inline-block; width: 22px; height: 0; border-top: 2px solid #34508F; vertical-align: middle; margin-right: 4px; }
.legende .strich.fluss { border-top: 2px dashed var(--akzent); }
.warte { position: absolute; inset: 0; display: grid; place-items: center; color: var(--text-3); }
.cloud { fill: #0E1530; stroke: #34508F; stroke-dasharray: 3 3; }
.kante { stroke: #34508F; stroke-width: 1.5; }
.fluss { stroke: var(--akzent); stroke-width: 2; fill: none; stroke-dasharray: 6 18; animation: fluss 2.2s linear infinite; opacity: .9; }
.fluss.langsam { animation-duration: 3.4s; }
@keyframes fluss { to { stroke-dashoffset: -48; } }
.knoten { fill: #1A2340; stroke: #5B79C9; stroke-width: 1.5; }
.knoten.hero { fill: #23306A; stroke: var(--akzent); stroke-width: 2; }
.knoten.aus { fill: #141A2C; stroke: #3A4463; }
.ring { fill: none; stroke-width: 2; opacity: .55; transform-box: fill-box; transform-origin: center; animation: ring 2.6s ease-out infinite; }
.ring.ok { stroke: var(--ok); }
.ring.warn { stroke: var(--warn); }
.ring.krit { stroke: var(--krit); animation-duration: 1.3s; }
.ring.unbekannt { stroke: #3A4463; animation: none; }
@keyframes ring { 0% { transform: scale(.96); opacity: .6; } 70% { transform: scale(1.06); opacity: 0; } 100% { transform: scale(1.06); opacity: 0; } }
.label { font-family: var(--display); font-size: 19px; font-weight: 600; fill: var(--text); letter-spacing: .04em; }
.sub { font-family: var(--mono); font-size: 11.5px; fill: var(--text-3); }
.app { font-family: var(--body); font-size: 12.5px; fill: var(--text-2); }
.kpi { font-family: var(--display); font-size: 34px; font-weight: 700; fill: var(--text); }
.dot { fill: #3A4463; }
.dot.ok { fill: var(--ok); } .dot.warn { fill: var(--warn); } .dot.krit { fill: var(--krit); }
.hero-karte { fill: #111A33; stroke: var(--akzent); stroke-width: 1.5; }
.knopf-svg { fill: var(--akzent); }
.knopf-svg.ghost { fill: transparent; stroke: var(--linie); }
.knopf-svg.busy { fill: #B9812A; }
.knopf-text { font-family: var(--display); font-size: 17px; font-weight: 700; fill: #1A1200; letter-spacing: .06em; text-transform: uppercase; }
.knopf-text.ghost { fill: var(--text-2); }
.klickbar { cursor: pointer; }
.klickbar:hover .knopf-svg { filter: brightness(1.1); }
.einblenden { animation: einblenden .7s cubic-bezier(.2,.7,.2,1) both; animation-delay: calc(var(--i, 0) * 90ms); }
.radar { animation: radar 14s linear infinite; transform-box: view-box; }
@keyframes radar { to { transform: rotate(360deg); } }
.paket { fill: #8FB4FF; opacity: .9; filter: drop-shadow(0 0 4px rgba(143,180,255,.9)); }
.paket.zurueck { fill: #5B79C9; opacity: .6; }
.paket.cloud-paket { fill: var(--akzent); filter: drop-shadow(0 0 5px rgba(242,184,75,.9)); }
.host .knoten { transition: filter .3s ease, stroke-width .3s ease; }
.host:hover .knoten { filter: drop-shadow(0 0 14px rgba(111,168,255,.75)); stroke-width: 2.5; }
.host:hover .label { fill: #fff; }
.hero-karte { animation: hero-glow 5s ease-in-out infinite; }
@keyframes hero-glow { 0%, 100% { filter: drop-shadow(0 0 0 rgba(242,184,75,0)); } 50% { filter: drop-shadow(0 0 16px rgba(242,184,75,.35)); } }
.blitz { animation: blitz 1.4s ease-out both; }
@keyframes blitz { 0% { fill: var(--akzent); } 100% { fill: var(--text); } }
@keyframes einblenden { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

/* ---------- Leitstand ---------- */
.leitstand { display: grid; grid-template-columns: 1.15fr 1.6fr 1fr; gap: 12px; padding: 14px 26px 54px; }
.kachel { background: var(--flaeche); border: 1px solid var(--linie); border-radius: 8px; padding: 12px 14px; min-width: 0; }
.kachel h4 { margin: 0 0 10px; font-family: var(--display); font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: var(--text-3); font-weight: 600; }
.kachel.projekte { grid-row: span 2; }
.kachel.hosts { grid-row: span 2; }
.kachel.github { grid-column: 1 / -1; }
.host-zeile { padding: 8px 0; border-bottom: 1px solid var(--linie); font-size: 13px; }
.host-zeile:last-child { border-bottom: 0; }
.hz-kopf { display: flex; justify-content: space-between; gap: 8px; }
.hz-sub { font-size: 11px; margin: 2px 0 6px; }
.balken-reihe { display: grid; grid-template-columns: 34px 1fr 34px 1fr 34px 1fr; gap: 6px; align-items: center; font-size: 10px; }
.balken { height: 6px; background: #1E2A4A; border-radius: 3px; overflow: hidden; }
.balken i { display: block; height: 100%; background: var(--info); border-radius: 3px; transition: width 1.2s cubic-bezier(.2,.7,.2,1); }
.balken i.warn { background: var(--warn); }
.balken i.gpu { background: linear-gradient(90deg, #6FA8FF, #B58BFF); }
.balken-reihe.gpu { grid-template-columns: 34px 1fr 34px 1fr; margin-top: 4px; }
.punkt { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: middle; background: #3A4463; }
.punkt.ok { background: var(--ok); box-shadow: 0 0 0 0 rgba(76,195,138,.55); animation: puls 2.4s ease-out infinite; }
.punkt.warn { background: var(--warn); }
.punkt.krit { background: var(--krit); box-shadow: 0 0 0 0 rgba(242,109,109,.6); animation: puls 1.2s ease-out infinite; }
@keyframes puls { 0% { box-shadow: 0 0 0 0 rgba(76,195,138,.55); } 70% { box-shadow: 0 0 0 8px rgba(76,195,138,0); } 100% { box-shadow: 0 0 0 0 rgba(76,195,138,0); } }
.projekt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 8px; }
.projekt { background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 6px; padding: 8px 10px; font-size: 12.5px; min-width: 0; }
.p-kopf { display: flex; align-items: center; gap: 6px; }
.p-kopf b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.p-sub { font-size: 11px; margin-top: 3px; }
.p-link { display: block; font-size: 11px; color: var(--info); text-decoration: none; margin-top: 3px; }
.sonde { padding: 6px 0; border-bottom: 1px solid var(--linie); font-size: 13px; }
.sonde:last-of-type { border-bottom: 0; }
.s-kopf { display: flex; align-items: center; gap: 8px; }
.s-kopf .mono { font-size: 11px; margin-left: auto; }
.s-kpis { display: flex; gap: 16px; margin-top: 4px; flex-wrap: wrap; }
.s-kpis span { display: flex; flex-direction: column; }
.kpi-klein { font-family: var(--display); font-style: normal; font-size: 22px; font-weight: 700; line-height: 1; }
.s-kpis small { font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }
.zeile { display: flex; justify-content: space-between; gap: 8px; padding: 5px 0; font-size: 13px; border-bottom: 1px solid var(--linie); }
.zeile:last-of-type { border-bottom: 0; }
.zeile .mono { font-size: 11px; color: var(--text-2); }
.modelle { font-size: 11px; color: var(--text-2); margin-top: 6px; line-height: 1.6; }
.repo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.repo { display: flex; flex-direction: column; gap: 2px; background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 6px; padding: 8px 10px; font-size: 12.5px; text-decoration: none; color: var(--text); }
.repo .mono { font-size: 11px; }
.repo:hover { border-color: var(--info); }
.repo.still { opacity: .55; }
.repo-grid { max-height: 330px; overflow: auto; }
.r-name { flex: 1; color: var(--text); text-decoration: none; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r-name:hover { color: var(--info); }
.p-intern { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 3px; }
.p-intern .p-link { display: inline; margin: 0; }

/* ---------- Mehrwert-Kacheln ---------- */
.live { display: inline-flex; align-items: center; gap: 2px; font-family: var(--mono); font-size: 11px; letter-spacing: .12em; color: var(--ok); text-transform: uppercase; }
.live em { font-style: normal; color: var(--text-3); letter-spacing: 0; margin-left: 4px; font-variant-numeric: tabular-nums; }
.kachel.alarm { border-color: rgba(242,109,109,.4); }
.kachel.alarm.krit { animation: alarm-puls 2.6s ease-in-out infinite; }
@keyframes alarm-puls { 0%, 100% { border-color: rgba(242,109,109,.35); box-shadow: 0 0 0 0 rgba(242,109,109,0); } 50% { border-color: rgba(242,109,109,.9); box-shadow: 0 0 22px rgba(242,109,109,.18); } }
.kachel.alarm.ruhig { border-color: rgba(76,195,138,.4); }
.ruhe { display: flex; align-items: center; gap: 10px; font-size: 14px; padding: 6px 0; }
.ruhe div { display: flex; flex-direction: column; }
.ruhe .mono { font-size: 11px; }
.alarm-liste { display: flex; flex-direction: column; gap: 6px; max-height: 290px; overflow: auto; }
.alarm-zeile { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; padding: 6px 8px; border-radius: 6px; background: var(--flaeche-2); border-left: 3px solid var(--warn); }
.alarm-zeile.krit { border-left-color: var(--krit); }
.alarm-zeile.info { border-left-color: var(--info); }
.alarm-zeile .punkt { margin-top: 5px; }
.a-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.a-text .mono { font-size: 11px; }
.punkt.info { background: var(--info); }
.dienst { display: grid; grid-template-columns: 14px 1fr 62px 66px 96px 78px; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--linie); font-size: 12.5px; }
.dienst:last-of-type { border-bottom: 0; }
.dienst .punkt { margin: 0; }
.d-name { color: var(--text); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.d-name:hover { color: var(--info); }
.d-ms, .d-tls, .d-req { font-size: 11px; color: var(--text-2); text-align: right; white-space: nowrap; }
.d-tls.warn { color: var(--warn); }
.funken { width: 96px; height: 18px; fill: var(--info); opacity: .75; }
.funken rect { transition: height .8s ease, y .8s ease; transform-box: fill-box; transform-origin: bottom; animation: wachsen .9s cubic-bezier(.2,.7,.2,1) both; animation-delay: calc(var(--i, 0) * 25ms); }
@keyframes wachsen { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.chip { font-family: var(--mono); font-size: 10px; padding: 1px 7px; border-radius: 10px; border: 1px solid var(--linie); color: var(--text-2); white-space: nowrap; }
.chip.pause { border-color: var(--akzent); color: var(--akzent); }
.chip.dirty { border-color: var(--warn); color: var(--warn); }
.chip.ahead { border-color: var(--info); color: var(--info); }
.chip.kat { justify-self: start; }
.repo-zeile { padding: 6px 0; border-bottom: 1px solid var(--linie); font-size: 13px; }
.repo-zeile:last-child { border-bottom: 0; }
.r-kopf { display: flex; gap: 8px; align-items: center; min-width: 0; }
.r-kopf b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r-kopf .mono { font-size: 11px; white-space: nowrap; }
.r-sub { font-size: 11px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kachel.kira { grid-column: span 2; }
.kachel.ki { grid-column: 1 / -1; }
.ki-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.ki-dienst { background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 8px; padding: 10px 12px; min-width: 0; }
.ki-kopf { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 8px; font-size: 14px; }
.ki-kopf .mono { font-size: 11px; }
.ki-limit { margin-bottom: 8px; }
.ki-limit-kopf { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px; }
.ki-limit-kopf .mono.ok { color: var(--ok); } .ki-limit-kopf .mono.warn { color: var(--warn); } .ki-limit-kopf .mono.krit { color: var(--krit); }
.balken i.ok { background: var(--ok); } .balken i.krit { background: var(--krit); }
.ki-reset { font-size: 10px; margin-top: 2px; }
.ki-heute { display: flex; flex-direction: column; margin-top: 8px; }
.ki-heute small { font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }
.ki-tage { display: flex; gap: 6px; align-items: flex-end; height: 44px; margin-top: 10px; }
.ki-tag { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.ki-tag i { display: block; width: 100%; background: linear-gradient(180deg, #6FA8FF, #34508F); border-radius: 3px 3px 0 0; }
.ki-tag span { font-size: 9px; margin-top: 2px; }
.ki-hinweis { font-size: 12px; }
.kachel.sitzungen { grid-column: 1 / -1; }
.sitzung { padding: 6px 0; border-bottom: 1px solid var(--linie); font-size: 13px; }
.sitzung:last-of-type { border-bottom: 0; }
.fenster { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.chip.aktiv { border-color: var(--ok); color: var(--ok); }
.chip.klick { cursor: pointer; background: transparent; }
.chip.klick:hover, .chip.offen { border-color: var(--akzent); color: var(--akzent); }
.terminal { margin: 8px 0 4px; border: 1px solid var(--linie); border-radius: 6px; background: #070B18; overflow: hidden; }
.t-kopf { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; font-size: 11px; border-bottom: 1px solid var(--linie); }
.t-ausgabe { margin: 0; padding: 10px 12px; max-height: 280px; overflow: auto; font-size: 11.5px; line-height: 1.45; color: var(--text-2); white-space: pre-wrap; word-break: break-word; }
.t-senden { display: flex; gap: 8px; padding: 8px 10px; border-top: 1px solid var(--linie); background: var(--flaeche); }
.t-eingabe { flex: 1; background: #0B1020; border: 1px solid var(--linie); color: var(--text); border-radius: 5px; padding: 7px 10px; font-size: 12.5px; }
.t-eingabe:focus { outline: 2px solid var(--akzent); outline-offset: 0; }
.knopf.warn { background: var(--krit); border-color: var(--krit); color: #fff; }
.chip em { font-style: normal; color: var(--text-3); }
.weiter { display: flex; gap: 8px; align-items: baseline; font-size: 12.5px; padding: 6px 8px; margin-bottom: 6px; border-radius: 6px; background: rgba(242,184,75,.08); border: 1px solid rgba(242,184,75,.35); }
.schalter { margin-top: 8px; }
.verlauf { fill: none; stroke: var(--info); stroke-width: 1.6; vector-effect: non-scaling-stroke; opacity: .85; }
.host-verlauf { width: 100%; height: 22px; margin-top: 4px; display: block; }
.kira-zeile { display: grid; grid-template-columns: 96px 1fr auto; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--linie); font-size: 12.5px; align-items: center; }
.kira-zeile:last-child { border-bottom: 0; }
.kira-zeile .mono { font-size: 11px; white-space: nowrap; }
.k-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kachel.flow-agent { grid-column: span 2; }
.flow-agent h4 a { color: var(--text-3); text-decoration: none; }.flow-agent h4 a:hover { color: var(--info); }
.flow-hostzeile { display: grid; grid-template-columns: 12px minmax(110px, .7fr) minmax(220px, auto); gap: 5px 9px; align-items: center; padding: 7px 0; border-bottom: 1px solid var(--linie); font-size: 12.5px; }.flow-hostzeile > .punkt { margin: 0; }.flow-name { display: flex; align-items: baseline; gap: 7px; min-width: 0; }.flow-name .mono { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }.flow-metrik { color: var(--text-2); font-size: 10px; text-align: right; white-space: nowrap; }.flow-chips { grid-column: 2; display: flex; flex-wrap: wrap; gap: 4px; min-height: 3px; }.flow-chips .chip { font-size: 9px; padding: 0 6px; }.flow-alter { grid-column: 3; grid-row: 2; color: var(--text-3); font-size: 10px; text-align: right; }.flow-alter.warn { color: var(--warn); }
.flow-frische { padding: 8px 0 5px; color: var(--text-2); font-size: 11.5px; }.flow-befund { padding: 4px 7px; margin-top: 3px; border-left: 2px solid var(--warn); background: var(--flaeche-2); color: var(--warn); font-size: 11px; }.flow-befund.ungesund { border-left-color: var(--krit); color: var(--krit); }.flow-aktionen { margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--linie); color: var(--text-3); font-size: 10px; }.flow-aktionen.offen { color: var(--warn); }
.liste-enter-active, .liste-leave-active, .liste-move { transition: all .55s cubic-bezier(.2,.7,.2,1); }
.liste-enter-from { opacity: 0; transform: translateX(-10px); }
.liste-leave-to { opacity: 0; transform: translateX(10px); }
.liste-leave-active { position: absolute; }

/* ---------- Ticker ---------- */
.ticker { position: fixed; left: 0; right: 0; bottom: 0; height: 36px; background: #080C18; border-top: 1px solid var(--linie); display: flex; align-items: center; overflow: hidden; font-size: 12px; color: var(--text-2); white-space: nowrap; z-index: 3; mask-image: linear-gradient(90deg, transparent, #000 3%, #000 97%, transparent); }
.ticker span { display: inline-block; padding-left: 100%; animation: lauf 240s linear infinite; }
@keyframes lauf { from { transform: translateX(0); } to { transform: translateX(-100%); } }

.wand.reduziert .fluss, .wand.reduziert .ring, .wand.reduziert .punkt, .wand.reduziert .einblenden, .wand.reduziert .ticker span, .wand.reduziert .radar, .wand.reduziert .hero-karte, .wand.reduziert .blitz, .wand.reduziert .landschaft, .wand.reduziert .funken rect, .wand.reduziert .kachel.alarm.krit { animation: none; }
.wand.reduziert .liste-enter-active, .wand.reduziert .liste-leave-active, .wand.reduziert .liste-move, .wand.reduziert .funken rect, .wand.reduziert .balken i { transition: none; }
@media (max-width: 1100px) {
  .leitstand { grid-template-columns: 1fr 1fr; }
  .kachel.sitzungen { grid-column: 1 / -1; }
  .kachel.projekte, .kachel.hosts { grid-row: auto; }
  .kachel.kira, .kachel.flow-agent { grid-column: auto; }
  .wand-kopf { grid-template-columns: 1fr; }
  .kopf-rechts { justify-content: flex-start; }
}
@media (max-width: 700px) { .flow-hostzeile { grid-template-columns: 12px 1fr; }.flow-metrik, .flow-alter { grid-column: 2; grid-row: auto; text-align: left; }.flow-chips { grid-column: 2; } }
</style>
