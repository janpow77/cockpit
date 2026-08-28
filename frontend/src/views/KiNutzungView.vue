<script setup lang="ts">
/**
 * KI-Nutzung: eigene Seite im Stil der Wand. Claude (Claude Code), Codex (ChatGPT) und
 * Gemini mit Limits, Reset-Zeiten, Tokens je Tag und Verlauf der Auslastung (7 Tage).
 * Daten kommen aus dem Wand-Stand (ki_nutzung) und dem Verlauf; alle 60 s aktualisiert.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getOverview, getVerlauf } from '../api/overview'
import { extractError } from '../api/client'
import { usePollStore } from '../stores/poll'
import type { KiDienst, KiNutzung, VerlaufAntwort } from '../api/types'

const REFRESH_MS = 60_000
const ki = ref<KiNutzung | null>(null)
const verlauf = ref<VerlaufAntwort | null>(null)
const error = ref<string | null>(null)
const stand = ref('')
const poll = usePollStore()
const reduziert = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

async function load() {
  try {
    const o = await getOverview()
    ki.value = o.ki_nutzung ?? null
    error.value = null
    stand.value = new Date().toLocaleTimeString('de-DE')
  } catch (err) {
    error.value = extractError(err)
  }
}
async function loadVerlauf() {
  try { verlauf.value = await getVerlauf(24 * 7, ['ki.claude.five_hour', 'ki.claude.seven_day', 'ki.codex.primary', 'ki.claude.out_heute', 'ki.codex.out_heute']) } catch { /* Verlauf ist Beiwerk */ }
}
onMounted(() => {
  if (!document.getElementById('wall-fonts')) {
    const l = document.createElement('link')
    l.id = 'wall-fonts'; l.rel = 'stylesheet'
    l.href = 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap'
    document.head.appendChild(l)
  }
  poll.start('ki', load, REFRESH_MS)
  poll.start('ki-verlauf', loadVerlauf, 5 * 60_000)
})
onBeforeUnmount(() => { poll.stop('ki'); poll.stop('ki-verlauf') })

const DIENSTE = [
  { key: 'claude', titel: 'Claude', sub: 'Claude Code · Anthropic', quelle: 'Auslastung über die Anmeldung von Claude Code, Tokens aus den Sitzungsprotokollen', verlaufKeys: [['ki.claude.five_hour', '5 Stunden'], ['ki.claude.seven_day', '7 Tage']] },
  { key: 'codex', titel: 'Codex', sub: 'ChatGPT · OpenAI', quelle: 'Limits und Tokens aus den Codex-Sitzungen (Stand der letzten Sitzung)', verlaufKeys: [['ki.codex.primary', 'Wochenfenster']] },
  { key: 'gemini', titel: 'Gemini', sub: 'Gemini CLI · Google', quelle: 'Gemini legt keine Nutzungsdaten ab – Limits nur in der App sichtbar', verlaufKeys: [] },
] as const

function dienst(key: string): KiDienst | undefined { return ki.value ? (ki.value as unknown as Record<string, KiDienst>)[key] : undefined }
function kTokens(n: number | undefined): string {
  if (n == null) return '–'
  if (n >= 1e9) return `${(n / 1e9).toFixed(2).replace('.', ',')} Mrd.`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace('.', ',')} Mio.`
  if (n >= 1e3) return `${Math.round(n / 1e3)} k`
  return String(n)
}
const de = new Intl.NumberFormat('de-DE')
function resetText(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const tage = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
  const diffH = Math.max(0, (d.getTime() - Date.now()) / 3600000)
  const in_ = diffH < 48 ? `in ${Math.round(diffH)} h` : `in ${Math.round(diffH / 24)} Tagen`
  return `Reset ${tage[d.getDay()]} ${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}. ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} (${in_})`
}
function klasse(p: number): string { return p >= 97 ? 'krit' : p >= 85 ? 'warn' : p >= 60 ? 'mittel' : 'ok' }
function bogen(p: number): string {
  // Halbkreis-Anzeige 0..100 % als SVG-Pfad (Radius 44, Mittelpunkt 50/50)
  const a = Math.PI * Math.min(100, Math.max(0, p)) / 100
  const x = 50 - 44 * Math.cos(a); const y = 50 - 44 * Math.sin(a)
  return `M 6 50 A 44 44 0 ${p > 50 ? 1 : 0} 1 ${x.toFixed(1)} ${y.toFixed(1)}`
}
function tagKurz(tag: string): string { return `${tag.slice(8, 10)}.${tag.slice(5, 7)}.` }
function reihe(key: string): number[] { const s = verlauf.value?.series[key]; return s ? s.map((p) => p[1]) : [] }
function linie(werte: number[]): string {
  if (werte.length < 2) return ''
  return werte.map((v, i) => `${i === 0 ? 'M' : 'L'} ${((i / (werte.length - 1)) * 100).toFixed(1)} ${(30 - Math.min(100, v) * 0.28).toFixed(1)}`).join(' ')
}
const modelle = computed(() => {
  const m = dienst('claude')?.heute?.modelle ?? {}
  return Object.entries(m).sort((a, b) => b[1].out - a[1].out)
})
const wocheClaude = computed(() => (dienst('claude')?.tage ?? []).reduce((s, t) => s + t.out, 0))
const wocheCodex = computed(() => (dienst('codex')?.tage ?? []).reduce((s, t) => s + t.out, 0))
</script>

<template>
  <div class="ki-seite" :class="{ reduziert }">
    <header class="kopf">
      <div class="titel"><span class="marke">flowaudit</span><span class="untertitel">KI-Nutzung</span></div>
      <div class="mitte mono dim">{{ ki?.host ? `Quelle ${ki.host}` : '' }}{{ stand ? ` · Stand ${stand}` : '' }}<span v-if="error" class="fehler"> · {{ error }}</span></div>
      <div class="rechts">
        <RouterLink to="/wall" class="knopf klein ghost">Zur Wand</RouterLink>
        <RouterLink to="/chat" class="knopf klein">KI-Konsole</RouterLink>
      </div>
    </header>

    <main v-if="ki" class="raster">
      <section v-for="d in DIENSTE" :key="d.key" class="karte einblenden" :class="{ aus: !dienst(d.key)?.verfuegbar }">
        <div class="k-kopf">
          <div><h2>{{ d.titel }}</h2><p class="mono dim">{{ d.sub }}{{ dienst(d.key)?.plan ? ` · Plan ${dienst(d.key)?.plan}` : '' }}{{ dienst(d.key)?.stufe ? ` · ${dienst(d.key)?.stufe}` : '' }}</p></div>
          <span v-if="dienst(d.key)?.verfuegbar" class="chip ok">verbunden</span><span v-else class="chip">keine Daten</span>
        </div>

        <template v-if="dienst(d.key)?.verfuegbar">
          <div class="anzeigen">
            <div v-for="(lim, lk) in dienst(d.key)?.limits ?? {}" :key="lk" class="anzeige">
              <svg viewBox="0 0 100 56" class="bogen"><path d="M 6 50 A 44 44 0 0 1 94 50" class="spur" /><path :d="bogen(lim.prozent)" :class="['wert', klasse(lim.prozent)]" /></svg>
              <div class="prozent" :class="klasse(lim.prozent)">{{ Math.round(lim.prozent) }} %</div>
              <div class="label">{{ lim.label }}</div>
              <div class="mono dim reset">{{ resetText(lim.reset) }}</div>
            </div>
            <div v-if="!Object.keys(dienst(d.key)?.limits ?? {}).length" class="dim hinweis">{{ dienst(d.key)?.hinweis || 'Keine Limitdaten gemeldet' }}</div>
          </div>

          <div class="zahlen">
            <div><em>{{ kTokens(dienst(d.key)?.heute?.out) }}</em><small>Ausgabe-Tokens heute</small></div>
            <div><em>{{ kTokens(dienst(d.key)?.heute?.kontext) }}</em><small>Kontext-Tokens heute</small></div>
            <div><em>{{ kTokens(d.key === 'claude' ? wocheClaude : wocheCodex) }}</em><small>Ausgabe · 7 Tage</small></div>
            <div v-if="dienst(d.key)?.heute?.sitzungen != null"><em>{{ de.format(dienst(d.key)?.heute?.sitzungen ?? 0) }}</em><small>Sitzungen heute</small></div>
          </div>

          <div v-if="dienst(d.key)?.tage?.length" class="tage">
            <div class="tage-kopf mono dim">Ausgabe-Tokens je Tag</div>
            <div class="balken-reihe">
              <div v-for="t in dienst(d.key)?.tage" :key="t.tag" class="tag" :title="`${tagKurz(t.tag)}: ${de.format(t.out)} Ausgabe · ${kTokens(t.kontext)} Kontext`">
                <span class="mono wert-klein">{{ kTokens(t.out) }}</span>
                <i :style="{ height: `${Math.max(3, Math.round((t.out / Math.max(1, ...(dienst(d.key)?.tage ?? []).map((x) => x.out))) * 100))}%` }" />
                <span class="mono dim">{{ t.tag.slice(8, 10) }}.{{ t.tag.slice(5, 7) }}.</span>
              </div>
            </div>
          </div>

          <div v-if="d.key === 'claude' && modelle.length" class="modelle">
            <div class="tage-kopf mono dim">Heute je Modell</div>
            <div v-for="[name, m] in modelle" :key="name" class="modell"><span class="mono">{{ name }}</span><span class="mono dim">{{ kTokens(m.out) }} Ausgabe · {{ kTokens(m.kontext) }} Kontext</span></div>
          </div>

          <div v-if="d.verlaufKeys.some(([k]) => reihe(k).length > 1)" class="verlauf">
            <div class="tage-kopf mono dim">Auslastung · 7 Tage</div>
            <svg viewBox="0 0 100 32" preserveAspectRatio="none" class="verlauf-svg">
              <line x1="0" y1="2.2" x2="100" y2="2.2" class="grenze" /><line x1="0" y1="16" x2="100" y2="16" class="grenze leicht" />
              <path v-for="([k], i) in d.verlaufKeys" :key="k" :d="linie(reihe(k))" :class="['linie', i === 0 ? 'a' : 'b']" />
            </svg>
            <div class="legende mono dim"><span v-for="([k, l], i) in d.verlaufKeys" :key="k"><i :class="i === 0 ? 'a' : 'b'" />{{ l }}</span><span class="rechts-text">100 % = Limit</span></div>
          </div>
        </template>
        <p v-else class="dim hinweis">{{ dienst(d.key)?.hinweis || 'Keine Daten' }}</p>
        <p class="quelle mono dim">{{ d.quelle }}</p>
      </section>
    </main>
    <div v-else class="warte mono dim">{{ error || 'Lade KI-Nutzung …' }}</div>
  </div>
</template>

<style scoped>
.ki-seite {
  --grund: #0B1020; --flaeche: #131A2E; --flaeche-2: #1A2340; --linie: #263054;
  --text: #E7ECF7; --text-2: #AAB3CF; --text-3: #7F89AB; --akzent: #F2B84B;
  --ok: #4CC38A; --warn: #F2B84B; --krit: #F26D6D; --info: #6FA8FF; --mittel: #B58BFF;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  min-height: 100vh; background: var(--grund); color: var(--text); font-family: var(--body);
}
.mono { font-family: var(--mono); } .dim { color: var(--text-3); }
.kopf { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 14px 26px 16px; border-bottom: 1px solid var(--linie); }
.marke { font-family: var(--display); font-size: 28px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.untertitel { margin-left: 12px; font-family: var(--mono); font-size: 12px; letter-spacing: .14em; color: var(--text-3); text-transform: uppercase; }
.mitte { text-align: center; font-size: 12px; } .fehler { color: var(--krit); }
.rechts { display: flex; justify-content: flex-end; gap: 10px; }
.knopf { font-family: var(--display); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; background: var(--akzent); color: #1A1200; border: 1px solid var(--akzent); border-radius: 5px; padding: 6px 12px; font-size: 13px; text-decoration: none; }
.knopf.ghost { background: transparent; color: var(--text-2); border-color: var(--linie); }
.raster { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 18px 26px 40px; }
.karte { background: var(--flaeche); border: 1px solid var(--linie); border-radius: 10px; padding: 16px 18px; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.karte.aus { opacity: .7; }
.k-kopf { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.k-kopf h2 { margin: 0; font-family: var(--display); font-size: 28px; font-weight: 700; letter-spacing: .03em; }
.k-kopf p { margin: 2px 0 0; font-size: 11px; }
.chip { font-family: var(--mono); font-size: 10px; padding: 2px 8px; border-radius: 10px; border: 1px solid var(--linie); color: var(--text-2); white-space: nowrap; }
.chip.ok { border-color: var(--ok); color: var(--ok); }
.anzeigen { display: flex; gap: 14px; flex-wrap: wrap; }
.anzeige { flex: 1 1 130px; background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 8px; padding: 10px 10px 8px; text-align: center; }
.bogen { width: 100%; max-width: 150px; display: block; margin: 0 auto; }
.spur { fill: none; stroke: #1E2A4A; stroke-width: 9; stroke-linecap: round; }
.wert { fill: none; stroke-width: 9; stroke-linecap: round; transition: d .8s ease; }
.wert.ok { stroke: var(--ok); } .wert.mittel { stroke: var(--info); } .wert.warn { stroke: var(--warn); } .wert.krit { stroke: var(--krit); }
.prozent { font-family: var(--display); font-size: 30px; font-weight: 700; margin-top: -26px; line-height: 1; }
.prozent.ok { color: var(--ok); } .prozent.mittel { color: var(--info); } .prozent.warn { color: var(--warn); } .prozent.krit { color: var(--krit); }
.label { font-size: 12px; color: var(--text-2); margin-top: 6px; }
.reset { font-size: 10px; margin-top: 2px; }
.zahlen { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 14px; }
.zahlen div { display: flex; flex-direction: column; }
.zahlen em { font-style: normal; font-family: var(--display); font-size: 24px; font-weight: 700; line-height: 1; }
.zahlen small { font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .06em; margin-top: 3px; }
.tage-kopf { font-size: 10px; text-transform: uppercase; letter-spacing: .1em; margin-bottom: 6px; }
.balken-reihe { display: flex; gap: 8px; align-items: flex-end; height: 92px; }
.tag { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 3px; }
.tag i { display: block; width: 100%; background: linear-gradient(180deg, #6FA8FF, #34508F); border-radius: 3px 3px 0 0; transform-box: fill-box; transform-origin: bottom; animation: wachsen .8s cubic-bezier(.2,.7,.2,1) both; }
@keyframes wachsen { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.tag span { font-size: 9px; } .wert-klein { color: var(--text-2); }
.modell { display: flex; justify-content: space-between; gap: 10px; font-size: 11px; padding: 4px 0; border-bottom: 1px solid var(--linie); }
.modell:last-child { border-bottom: 0; }
.verlauf-svg { width: 100%; height: 70px; display: block; background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 6px; }
.grenze { stroke: var(--krit); stroke-width: .4; stroke-dasharray: 2 2; } .grenze.leicht { stroke: var(--linie); }
.linie { fill: none; stroke-width: 1.4; vector-effect: non-scaling-stroke; } .linie.a { stroke: var(--info); } .linie.b { stroke: var(--akzent); }
.legende { display: flex; gap: 14px; font-size: 10px; margin-top: 4px; }
.legende i { display: inline-block; width: 12px; height: 2px; vertical-align: middle; margin-right: 4px; } .legende i.a { background: var(--info); } .legende i.b { background: var(--akzent); }
.rechts-text { margin-left: auto; }
.hinweis { font-size: 12px; } .quelle { font-size: 10px; margin-top: auto; }
.warte { display: grid; place-items: center; height: 60vh; }
.einblenden { animation: einblenden .6s cubic-bezier(.2,.7,.2,1) both; }
@keyframes einblenden { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.ki-seite.reduziert .einblenden, .ki-seite.reduziert .tag i { animation: none; }
@media (max-width: 1100px) { .raster { grid-template-columns: 1fr; } .kopf { grid-template-columns: 1fr; } .rechts { justify-content: flex-start; } }
</style>
