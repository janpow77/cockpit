<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getOverview, getVerlauf } from '../../api/overview'
import { extractError } from '../../api/client'
import type { KiDienst, KiNutzung, VerlaufAntwort } from '../../api/types'
import { usePollStore } from '../../stores/poll'

defineProps<{ offen: boolean }>()

const REFRESH_MS = 60_000
type DienstKey = 'claude' | 'codex' | 'gemini'

const DIENSTE: { key: DienstKey; titel: string; sub: string; quelle: string; verlaufKeys: [string, string][] }[] = [
  { key: 'claude', titel: 'Claude', sub: 'Claude Code · Anthropic', quelle: 'Auslastung über die Anmeldung von Claude Code, Tokens aus den Sitzungsprotokollen', verlaufKeys: [['ki.claude.five_hour', '5 Stunden'], ['ki.claude.seven_day', '7 Tage']] },
  { key: 'codex', titel: 'Codex', sub: 'ChatGPT · OpenAI', quelle: 'Limits und Tokens aus den Codex-Sitzungen (Stand der letzten Sitzung)', verlaufKeys: [['ki.codex.primary', 'Wochenfenster']] },
  { key: 'gemini', titel: 'Gemini', sub: 'Antigravity CLI (agy) · Google-Abo', quelle: 'agy legt keine Nutzungsdaten ab – Kontingent nur in agy (/usage) sichtbar', verlaufKeys: [] },
]

const ki = ref<KiNutzung | null>(null)
const verlauf = ref<VerlaufAntwort | null>(null)
const error = ref<string | null>(null)
const stand = ref('')
const poll = usePollStore()
const de = new Intl.NumberFormat('de-DE')

async function laden() {
  try {
    const overview = await getOverview()
    ki.value = overview.ki_nutzung ?? null
    error.value = null
    stand.value = new Date().toLocaleTimeString('de-DE')
  } catch (err) { error.value = extractError(err) }
}
async function verlaufLaden() {
  try { verlauf.value = await getVerlauf(24 * 7, ['ki.claude.five_hour', 'ki.claude.seven_day', 'ki.codex.primary', 'ki.claude.out_heute', 'ki.codex.out_heute']) }
  catch { /* Verlauf ist ergänzend; die aktuellen Limits bleiben sichtbar. */ }
}

onMounted(() => {
  poll.start('kanban-ki', laden, REFRESH_MS)
  poll.start('kanban-ki-verlauf', verlaufLaden, 5 * 60_000)
})
onBeforeUnmount(() => { poll.stop('kanban-ki'); poll.stop('kanban-ki-verlauf') })

function dienst(key: DienstKey): KiDienst | undefined { return ki.value?.[key] }
function kTokens(n: number | undefined): string {
  if (n == null) return '–'
  if (n >= 1e9) return `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(n / 1e9)} Mrd.`
  if (n >= 1e6) return `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(n / 1e6)} Mio.`
  if (n >= 1e3) return `${Math.round(n / 1e3)} k`
  return String(n)
}
function resetText(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const tage = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
  const diffH = Math.max(0, (d.getTime() - Date.now()) / 3600000)
  const verbleibend = diffH < 48 ? `in ${Math.round(diffH)} h` : `in ${Math.round(diffH / 24)} Tagen`
  return `Reset ${tage[d.getDay()]} ${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}. ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} (${verbleibend})`
}
function klasse(p: number): string { return p >= 97 ? 'krit' : p >= 85 ? 'warn' : p >= 60 ? 'mittel' : 'ok' }
function kompaktLabel(key: DienstKey, limitKey: string, fallback: string): string {
  if (key === 'claude' && limitKey === 'five_hour') return '5 h'
  if (key === 'claude' && limitKey === 'seven_day') return '7 Tage'
  if (key === 'codex') return 'Woche'
  return fallback
}
function rund(v: number): number { return Math.round(v * 10) / 10 }
function bogen(p: number): string {
  const a = Math.PI * Math.min(100, Math.max(0, p)) / 100
  const x = 50 - 44 * Math.cos(a); const y = 50 - 44 * Math.sin(a)
  // Halbkreis von links (6,50) über oben nach rechts: der Wertbogen überspannt höchstens 180°, Large-Arc-Flag daher immer 0
  return `M 6 50 A 44 44 0 0 1 ${rund(x)} ${rund(y)}`
}
function tagKurz(tag: string): string { return `${tag.slice(8, 10)}.${tag.slice(5, 7)}.` }
function reihe(key: string): number[] { return verlauf.value?.series[key]?.map((punkt) => punkt[1]) ?? [] }
function linie(werte: number[]): string {
  if (werte.length < 2) return ''
  return werte.map((wert, index) => `${index === 0 ? 'M' : 'L'} ${rund((index / (werte.length - 1)) * 100)} ${rund(30 - Math.min(100, wert) * .28)}`).join(' ')
}
const modelle = computed(() => Object.entries(dienst('claude')?.heute?.modelle ?? {}).sort((a, b) => b[1].out - a[1].out))
const wocheClaude = computed(() => (dienst('claude')?.tage ?? []).reduce((summe, tag) => summe + tag.out, 0))
const wocheCodex = computed(() => (dienst('codex')?.tage ?? []).reduce((summe, tag) => summe + tag.out, 0))
</script>

<template>
  <div class="ki-panel">
    <div v-if="ki" class="kompakt-limits">
      <section v-for="d in DIENSTE" :key="d.key" class="dienst-kompakt" :class="{ aus: !dienst(d.key)?.verfuegbar }">
        <div class="dienst-name"><b>{{ d.titel }}</b><span class="mono dim">{{ d.sub }}{{ dienst(d.key)?.plan ? ` · ${dienst(d.key)?.plan}` : '' }}</span></div>
        <div v-if="dienst(d.key)?.verfuegbar && Object.keys(dienst(d.key)?.limits ?? {}).length" class="anzeigen">
          <div v-for="(limit, limitKey) in dienst(d.key)?.limits ?? {}" :key="limitKey" class="anzeige">
            <svg viewBox="0 0 100 56" class="bogen"><path d="M 6 50 A 44 44 0 0 1 94 50" class="spur" /><path :d="bogen(limit.prozent)" :class="['wert', klasse(limit.prozent)]" /></svg>
            <div class="prozent" :class="klasse(limit.prozent)">{{ Math.round(limit.prozent) }} %</div>
            <div class="label">{{ kompaktLabel(d.key, String(limitKey), limit.label) }}</div><div class="mono dim reset">{{ resetText(limit.reset) }}</div>
          </div>
        </div>
        <p v-else class="dienst-hinweis dim">{{ dienst(d.key)?.hinweis || (d.key === 'gemini' ? 'Limits nur in Gemini sichtbar' : 'Keine Limitdaten gemeldet') }}</p>
      </section>
    </div>
    <div v-else class="ladezustand mono" :class="{ fehler: error }">{{ error || 'Lade LLM-Nutzung …' }}</div>

    <Transition name="details">
      <div v-if="offen && ki" class="detail-raster">
        <section v-for="d in DIENSTE" :key="d.key" class="detail-karte" :class="{ aus: !dienst(d.key)?.verfuegbar }">
          <div class="detail-kopf"><div><h3>{{ d.titel }}</h3><p class="mono dim">{{ d.sub }}</p></div><span v-if="dienst(d.key)?.verfuegbar" class="chip ok">verbunden</span><span v-else class="chip">keine Daten</span></div>
          <template v-if="dienst(d.key)?.verfuegbar">
            <div class="zahlen"><div><em>{{ kTokens(dienst(d.key)?.heute?.out) }}</em><small>Ausgabe-Tokens heute</small></div><div><em>{{ kTokens(dienst(d.key)?.heute?.kontext) }}</em><small>Kontext-Tokens heute</small></div><div><em>{{ kTokens(d.key === 'claude' ? wocheClaude : wocheCodex) }}</em><small>Ausgabe · 7 Tage</small></div><div v-if="dienst(d.key)?.heute?.sitzungen != null"><em>{{ de.format(dienst(d.key)?.heute?.sitzungen ?? 0) }}</em><small>Sitzungen heute</small></div></div>
            <div v-if="dienst(d.key)?.tage?.length" class="tage"><div class="abschnitt-titel mono dim">Ausgabe-Tokens je Tag</div><div class="balken-reihe"><div v-for="tag in dienst(d.key)?.tage" :key="tag.tag" class="tag" :title="`${tagKurz(tag.tag)}: ${de.format(tag.out)} Ausgabe · ${kTokens(tag.kontext)} Kontext`"><span class="mono wert-klein">{{ kTokens(tag.out) }}</span><i :style="{ height: `${Math.max(3, Math.round((tag.out / Math.max(1, ...(dienst(d.key)?.tage ?? []).map((eintrag) => eintrag.out))) * 100))}%` }" /><span class="mono dim">{{ tagKurz(tag.tag) }}</span></div></div></div>
            <div v-if="d.key === 'claude' && modelle.length" class="modelle"><div class="abschnitt-titel mono dim">Heute je Modell</div><div v-for="[name, modell] in modelle" :key="name" class="modell"><span class="mono">{{ name }}</span><span class="mono dim">{{ kTokens(modell.out) }} Ausgabe · {{ kTokens(modell.kontext) }} Kontext</span></div></div>
            <div v-if="d.verlaufKeys.some(([key]) => reihe(key).length > 1)" class="verlauf"><div class="abschnitt-titel mono dim">Auslastung · 7 Tage</div><svg viewBox="0 0 100 32" preserveAspectRatio="none" class="verlauf-svg"><line x1="0" y1="2.2" x2="100" y2="2.2" class="grenze" /><line x1="0" y1="16" x2="100" y2="16" class="grenze leicht" /><path v-for="([key], index) in d.verlaufKeys" :key="key" :d="linie(reihe(key))" :class="['linie', index === 0 ? 'a' : 'b']" /></svg><div class="legende mono dim"><span v-for="([key, label], index) in d.verlaufKeys" :key="key"><i :class="index === 0 ? 'a' : 'b'" />{{ label }}</span><span class="rechts-text">100 % = Limit</span></div></div>
          </template>
          <p v-else class="dim hinweis">{{ dienst(d.key)?.hinweis || 'Keine Daten' }}</p><p class="quelle mono dim">{{ d.quelle }}</p>
        </section>
      </div>
    </Transition>
    <p class="stand mono dim">{{ ki?.host ? `Quelle ${ki.host}` : '' }}{{ stand ? ` · Stand ${stand}` : '' }}<span v-if="error" class="fehler"> · {{ error }}</span></p>
  </div>
</template>

<style scoped>
.ki-panel { color: var(--text); }.mono { font-family: var(--mono); }.dim { color: var(--text-3); }.fehler { color: var(--krit); }
.kompakt-limits { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }.dienst-kompakt { display: grid; grid-template-columns: minmax(95px, .55fr) 1fr; align-items: center; gap: 10px; min-width: 0; padding: 9px 11px; border: 1px solid var(--linie); border-radius: 7px; background: var(--flaeche); }.dienst-kompakt.aus, .detail-karte.aus { opacity: .68; }.dienst-name { display: flex; flex-direction: column; min-width: 0; }.dienst-name b { font-family: var(--display); font-size: 19px; }.dienst-name span { font-size: 8px; line-height: 1.4; }.anzeigen { display: flex; gap: 7px; min-width: 0; }.anzeige { flex: 1; min-width: 74px; text-align: center; }.bogen { display: block; width: 100%; max-width: 100px; height: 45px; margin: 0 auto; }.spur { fill: none; stroke: #1E2A4A; stroke-width: 9; stroke-linecap: round; }.wert { fill: none; stroke-width: 9; stroke-linecap: round; }.wert.ok { stroke: var(--ok); }.wert.mittel { stroke: var(--info); }.wert.warn { stroke: var(--warn); }.wert.krit { stroke: var(--krit); }.prozent { margin-top: -20px; font-family: var(--display); font-size: 21px; font-weight: 700; line-height: 1; }.prozent.ok { color: var(--ok); }.prozent.mittel { color: var(--info); }.prozent.warn { color: var(--warn); }.prozent.krit { color: var(--krit); }.label { margin-top: 5px; color: var(--text-2); font-size: 9px; }.reset { margin-top: 1px; font-size: 7px; line-height: 1.3; }.dienst-hinweis { margin: 0; font-size: 10px; line-height: 1.45; }.ladezustand { padding: 18px; color: var(--text-3); text-align: center; font-size: 11px; }
.detail-raster { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }.detail-karte { display: flex; flex-direction: column; gap: 13px; min-width: 0; padding: 13px 14px; border: 1px solid var(--linie); border-radius: 8px; background: var(--flaeche); }.detail-kopf { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }.detail-kopf h3 { margin: 0; font-family: var(--display); font-size: 22px; }.detail-kopf p { margin: 1px 0 0; font-size: 9px; }.chip { padding: 2px 7px; border: 1px solid var(--linie); border-radius: 10px; color: var(--text-2); font-family: var(--mono); font-size: 8px; white-space: nowrap; }.chip.ok { border-color: var(--ok); color: var(--ok); }.zahlen { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 12px; }.zahlen div { display: flex; flex-direction: column; }.zahlen em { font-family: var(--display); font-size: 21px; font-style: normal; font-weight: 700; line-height: 1; }.zahlen small { margin-top: 3px; color: var(--text-3); font-size: 8px; letter-spacing: .05em; text-transform: uppercase; }.abschnitt-titel { margin-bottom: 5px; font-size: 8px; letter-spacing: .1em; text-transform: uppercase; }.balken-reihe { display: flex; align-items: flex-end; gap: 6px; height: 82px; }.tag { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 2px; }.tag i { display: block; width: 100%; border-radius: 3px 3px 0 0; background: linear-gradient(180deg, var(--info), #34508F); transform-origin: bottom; animation: wachsen .7s cubic-bezier(.2,.7,.2,1) both; }.tag span { font-size: 7px; }.wert-klein { color: var(--text-2); }.modell { display: flex; justify-content: space-between; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--linie); font-size: 9px; }.modell:last-child { border-bottom: 0; }.verlauf-svg { display: block; width: 100%; height: 62px; border: 1px solid var(--linie); border-radius: 5px; background: var(--flaeche-2); }.grenze { stroke: var(--krit); stroke-width: .4; stroke-dasharray: 2 2; }.grenze.leicht { stroke: var(--linie); }.linie { fill: none; stroke-width: 1.3; vector-effect: non-scaling-stroke; }.linie.a { stroke: var(--info); }.linie.b { stroke: var(--akzent); }.legende { display: flex; gap: 10px; margin-top: 4px; font-size: 8px; }.legende i { display: inline-block; width: 10px; height: 2px; margin-right: 3px; vertical-align: middle; }.legende i.a { background: var(--info); }.legende i.b { background: var(--akzent); }.rechts-text { margin-left: auto; }.quelle { margin: auto 0 0; font-size: 8px; }.hinweis { font-size: 10px; }.stand { margin: 7px 1px 0; font-size: 8px; text-align: right; }
.details-enter-active, .details-leave-active { transition: opacity .18s ease, transform .18s ease; }.details-enter-from, .details-leave-to { opacity: 0; transform: translateY(-4px); }@keyframes wachsen { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@media (max-width: 1100px) { .kompakt-limits, .detail-raster { grid-template-columns: 1fr; }.dienst-kompakt { grid-template-columns: 140px 1fr; }.anzeigen { max-width: 360px; } }
@media (max-width: 600px) { .dienst-kompakt { grid-template-columns: 1fr; }.anzeigen { max-width: none; }.detail-raster { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .ki-panel *, .ki-panel *::before, .ki-panel *::after { animation-duration: .001ms !important; transition-duration: .001ms !important; } }
</style>
