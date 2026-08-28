<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import { extractError } from '../api/client'
import { getOverview } from '../api/overview'
import type { Overview, WallAlert, WallDienst, WallHost } from '../api/types'
import { usePollStore } from '../stores/poll'

const REFRESH_MS = 60_000
const overview = ref<Overview | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
const clock = ref('')
const updatedAt = ref<Date | null>(null)
const poll = usePollStore()
const numberFormat = new Intl.NumberFormat('de-DE')
const decimalFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 })
let clockTimer: number | undefined

const alerts = computed<WallAlert[]>(() => overview.value?.alerts ?? [])
const dienste = computed<WallDienst[]>(() => overview.value?.dienste ?? [])
const hosts = computed<WallHost[]>(() => overview.value?.hosts ?? [])

function time(date: Date): string {
  return new Intl.DateTimeFormat('de-DE', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
}

function tick(): void {
  clock.value = time(new Date())
}

async function load(): Promise<void> {
  if (loading.value) return
  loading.value = true
  try {
    overview.value = await getOverview()
    updatedAt.value = new Date()
    error.value = null
  } catch (err) {
    error.value = extractError(err)
  } finally {
    loading.value = false
  }
}

function value(value: number | string): string {
  return typeof value === 'number' ? numberFormat.format(value) : value
}

function bounded(value: number | null | undefined): number {
  return Math.min(100, Math.max(0, value ?? 0))
}

function loadPercent(host: WallHost): number {
  return bounded(((host.stats.load1 ?? 0) / (host.stats.cpus || 1)) * 100)
}

function hostOnline(host: WallHost): boolean {
  return host.stats.ok || host.status === 'online' || host.status === 'healthy' || host.status === 'ok'
}

function milliseconds(dienst: WallDienst): string {
  return dienst.ms == null ? '– ms' : `${numberFormat.format(dienst.ms)} ms`
}

onMounted(() => {
  if (!document.getElementById('wall-fonts')) {
    const link = document.createElement('link')
    link.id = 'wall-fonts'
    link.rel = 'stylesheet'
    link.href = 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap'
    document.head.appendChild(link)
  }
  poll.start('kompakt', load, REFRESH_MS)
  tick()
  clockTimer = window.setInterval(tick, 1000)
})

onBeforeUnmount(() => {
  poll.stop('kompakt')
  if (clockTimer !== undefined) window.clearInterval(clockTimer)
})
</script>

<template>
  <main class="kompakt">
    <header class="kopf">
      <div>
        <h1>flowaudit · Cockpit</h1>
        <div class="live-row mono"><span class="live-dot" aria-hidden="true"></span>LIVE · {{ clock }}</div>
      </div>
      <button class="reload" type="button" :disabled="loading" @click="load">
        <RefreshCw :size="17" aria-hidden="true" />
        Neu laden
      </button>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="!overview && loading" class="loading" aria-live="polite">Cockpit wird geladen …</div>

    <template v-if="overview">
      <section class="card alerts-card">
        <h2>Handlungsbedarf</h2>
        <div v-if="alerts.length" class="alert-list">
          <article v-for="alert in alerts" :key="`${alert.level}-${alert.host}-${alert.text}`" class="alert" :class="alert.level">
            <strong>{{ alert.text }}</strong>
            <p v-if="alert.hint">{{ alert.hint }}</p>
          </article>
        </div>
        <p v-else class="all-good"><span aria-hidden="true">●</span> Alles läuft</p>
      </section>

      <section class="card hero-card">
        <div class="section-head">
          <div><span class="eyebrow">HPP</span><h2>{{ overview.hero.title }}</h2></div>
          <a :href="overview.hero.url" target="_blank" rel="noopener">Öffnen ↗</a>
        </div>
        <div class="kpis">
          <div v-for="kpi in overview.hero.kpis.slice(0, 4)" :key="kpi.label" class="kpi">
            <strong>{{ value(kpi.value) }}</strong>
            <span>{{ kpi.label }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>Dienste</h2>
        <div class="rows">
          <div v-for="dienst in dienste" :key="dienst.url" class="service-row">
            <span class="status-dot" :class="dienst.ok ? 'ok' : 'bad'" aria-hidden="true"></span>
            <strong>{{ dienst.host }}</strong>
            <span class="mono">{{ milliseconds(dienst) }}</span>
            <span class="mono" :class="{ warning: dienst.tls_tage != null && dienst.tls_tage < 14 }">TLS {{ dienst.tls_tage ?? '–' }} d</span>
          </div>
          <p v-if="!dienste.length" class="empty">Keine Dienste gemeldet.</p>
        </div>
      </section>

      <section class="card">
        <h2>Hosts</h2>
        <div class="hosts">
          <article v-for="host in hosts" :key="host.name" class="host">
            <div class="host-head">
              <span class="status-dot" :class="hostOnline(host) ? 'ok' : 'bad'" aria-hidden="true"></span>
              <strong>{{ host.name }}</strong>
              <span class="mono">{{ host.stats.containers == null ? '–' : numberFormat.format(host.stats.containers) }} Container</span>
            </div>
            <div class="meters">
              <span>Load</span><div class="meter"><i :style="{ width: `${loadPercent(host)}%` }"></i></div><b>{{ decimalFormat.format(host.stats.load1 ?? 0) }}</b>
              <span>RAM</span><div class="meter"><i :style="{ width: `${bounded(host.stats.mem_pct)}%` }"></i></div><b>{{ decimalFormat.format(host.stats.mem_pct ?? 0) }} %</b>
              <span>Disk</span><div class="meter"><i :class="{ warning: (host.stats.disk_pct ?? 0) > 80 }" :style="{ width: `${bounded(host.stats.disk_pct)}%` }"></i></div><b>{{ decimalFormat.format(host.stats.disk_pct ?? 0) }} %</b>
            </div>
          </article>
          <p v-if="!hosts.length" class="empty">Keine Hosts gemeldet.</p>
        </div>
      </section>
    </template>

    <footer class="footer mono">
      <span>Stand {{ updatedAt ? time(updatedAt) : '–' }}</span>
      <RouterLink to="/wall">Zur Wand</RouterLink>
    </footer>
  </main>
</template>

<style scoped>
.kompakt {
  --grund: #0B1020; --flaeche: #131A2E; --flaeche-2: #1A2340; --linie: #263054;
  --text: #E7ECF7; --text-2: #AAB3CF; --text-3: #7F89AB; --akzent: #F2B84B;
  --ok: #4CC38A; --warn: #F2B84B; --krit: #F26D6D; --info: #6FA8FF;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  width: min(100%, 480px); min-height: 100vh; min-height: 100dvh; margin: 0 auto; padding: 0 12px;
  overflow-x: hidden; background: var(--grund); color: var(--text); font-family: var(--body); box-sizing: border-box;
}
.kompakt *, .kompakt *::before, .kompakt *::after { box-sizing: border-box; }
.mono { font-family: var(--mono); }
.kopf { min-height: 82px; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--linie); }
h1, h2, p { margin: 0; }
h1 { font: 700 22px/1 var(--display); letter-spacing: .035em; text-transform: uppercase; }
h2 { font: 700 18px/1.1 var(--display); letter-spacing: .065em; text-transform: uppercase; }
.live-row { display: flex; align-items: center; gap: 6px; margin-top: 8px; color: var(--text-3); font-size: 10px; }
.live-dot, .status-dot { display: inline-block; flex: 0 0 auto; border-radius: 50%; background: var(--krit); }
.live-dot { width: 7px; height: 7px; background: var(--ok); box-shadow: 0 0 8px rgba(76, 195, 138, .65); animation: pulse 2s ease-in-out infinite; }
.status-dot { width: 8px; height: 8px; }
.status-dot.ok { background: var(--ok); }
.status-dot.bad { background: var(--krit); }
.reload { min-height: 44px; display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; gap: 6px; padding: 0 11px; border: 1px solid var(--linie); border-radius: 5px; background: var(--flaeche); color: var(--text); font: 700 12px var(--display); letter-spacing: .04em; text-transform: uppercase; cursor: pointer; }
.reload:disabled { opacity: .55; cursor: wait; }
.reload:not(:disabled):hover { border-color: var(--akzent); color: var(--akzent); }
.reload:not(:disabled):active { transform: translateY(1px); }
.card { margin-top: 12px; padding: 15px 13px; overflow: hidden; border: 1px solid var(--linie); border-radius: 7px; background: var(--flaeche); }
.card > h2 { margin-bottom: 12px; }
.alert-list { display: grid; gap: 8px; }
.alert { padding: 8px 9px 8px 12px; border-left: 3px solid var(--info); background: var(--flaeche-2); overflow-wrap: anywhere; }
.alert.krit { border-color: var(--krit); }
.alert.warn { border-color: var(--warn); }
.alert.info { border-color: var(--info); }
.alert strong { font-size: 13px; line-height: 1.4; }
.alert p { margin-top: 4px; color: var(--text-2); font-size: 11px; line-height: 1.4; }
.all-good { min-height: 44px; display: flex; align-items: center; gap: 9px; color: var(--ok); font-weight: 600; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.section-head h2 { margin-top: 3px; color: var(--text); text-transform: none; }
.eyebrow { color: var(--akzent); font: 600 10px var(--mono); letter-spacing: .12em; }
a { color: var(--akzent); text-decoration: none; }
.section-head a, .footer a { min-height: 44px; display: inline-flex; align-items: center; padding: 0 7px; font: 600 12px var(--body); }
.kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.kpi { min-width: 0; padding: 10px; border: 1px solid var(--linie); border-radius: 5px; background: #10172a; }
.kpi strong { display: block; overflow: hidden; color: var(--text); font: 700 clamp(25px, 9vw, 38px)/1 var(--display); text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
.kpi span { display: block; margin-top: 6px; color: var(--text-3); font-size: 10px; line-height: 1.25; }
.rows, .hosts { display: grid; }
.service-row { min-height: 44px; display: grid; grid-template-columns: 9px minmax(0, 1fr) auto auto; align-items: center; gap: 8px; border-top: 1px solid var(--linie); font-size: 11px; }
.service-row:first-child { border-top: 0; }
.service-row strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.service-row .mono { color: var(--text-2); font-size: 9px; white-space: nowrap; }
.warning { color: var(--warn) !important; }
.host { padding: 12px 0; border-top: 1px solid var(--linie); }
.host:first-child { padding-top: 0; border-top: 0; }
.host:last-child { padding-bottom: 0; }
.host-head { min-height: 28px; display: grid; grid-template-columns: 9px minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.host-head .mono { color: var(--text-2); font-size: 9px; }
.meters { display: grid; grid-template-columns: 28px minmax(0, 1fr) 48px; align-items: center; gap: 5px 8px; margin: 7px 0 0 17px; color: var(--text-3); font: 9px var(--mono); }
.meters b { color: var(--text-2); font-weight: 400; text-align: right; }
.meter { height: 4px; overflow: hidden; border-radius: 999px; background: #293352; }
.meter i { display: block; height: 100%; border-radius: inherit; background: var(--ok); transition: width .35s ease; }
.meter i.warning { background: var(--warn); }
.empty, .loading { color: var(--text-3); font-size: 12px; }
.loading { min-height: 160px; display: grid; place-items: center; }
.error { margin-top: 12px; padding: 10px; border-left: 3px solid var(--krit); background: rgba(242, 109, 109, .08); color: var(--krit); font: 11px/1.45 var(--mono); overflow-wrap: anywhere; }
.footer { min-height: 62px; display: flex; align-items: center; justify-content: space-between; margin-top: 12px; border-top: 1px solid var(--linie); color: var(--text-3); font-size: 10px; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--akzent); outline-offset: 2px; }
@keyframes pulse { 50% { opacity: .55; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation: none !important; transition: none !important; }
}
</style>
