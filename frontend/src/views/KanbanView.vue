<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ChevronDown, Edit3, ExternalLink, GripVertical, Lightbulb, Play, Send, Square, Trash2, X } from 'lucide-vue-next'
import { aendern, anlegen, listeAuftraege, loeschen, logLesen, nachfragen, projekte, starten, stoppen, umsetzen, vorlagen as vorlagenAbrufen, vorschlaegeEinholen } from '../api/auftraege'
import { extractError } from '../api/client'
import type { Auftrag, AuftragAgent, AuftragModus, AuftragProfil, AuftragStatus, AuftraegeAntwort, LogZeile, Projekt, Vorlage, Zeitfenster } from '../api/types'
import { usePollStore } from '../stores/poll'
import { useToastStore } from '../stores/toast'
import KiNutzungPanel from '../components/kanban/KiNutzungPanel.vue'

const REFRESH_MS = 10_000
type SpaltenStatus = 'eingang' | 'geplant' | 'laeuft' | 'rueckfrage' | 'fertig'

const SPALTEN: { id: SpaltenStatus; titel: string }[] = [
  { id: 'eingang', titel: 'Eingang' },
  { id: 'geplant', titel: 'Geplant' },
  { id: 'laeuft', titel: 'Läuft' },
  { id: 'rueckfrage', titel: 'Rückfrage / Freigabe' },
  { id: 'fertig', titel: 'Fertig' },
]
const PROFIL_LABELS: Record<AuftragProfil, string> = { lesen: 'Lesen', bearbeiten: 'Bearbeiten', bearbeiten_tests: 'Bearbeiten + Tests', voll: 'Voll' }
const AGENT_LABELS: Record<AuftragAgent, string> = { claude: 'Claude', codex: 'Codex', gemini: 'Gemini' }
const MODUS_LABELS: Record<AuftragModus, string> = { bericht: 'Bericht', plan_freigabe: 'Plan → Freigabe', umsetzen: 'Umsetzen' }
const ZEIT_LABELS: Record<Zeitfenster, string> = { sofort: 'sofort', nachts: 'nachts', nach_reset: 'nach Reset' }
const STATUS_LABELS: Record<AuftragStatus, string> = { eingang: 'Eingang', geplant: 'Geplant', laeuft: 'Läuft', rueckfrage: 'Rückfrage', freigabe: 'Plan zur Freigabe', fertig: 'Fertig', fehler: 'Fehler', abgebrochen: 'Abgebrochen' }
const PROFILE: { id: AuftragProfil; titel: string; text: string }[] = [
  { id: 'lesen', titel: 'Lesen', text: 'nur analysieren' },
  { id: 'bearbeiten', titel: 'Bearbeiten', text: 'Dateien ändern' },
  { id: 'bearbeiten_tests', titel: 'Bearbeiten + Tests', text: 'zusätzlich Tests, Lint und Commit erlaubt' },
  { id: 'voll', titel: 'Voll', text: 'Classifier entscheidet' },
]
const AGENTEN: { id: AuftragAgent; titel: string; text: string }[] = [
  { id: 'claude', titel: 'Claude Code', text: 'Max-Kontingent, 5-Stunden-Fenster' },
  { id: 'codex', titel: 'Codex', text: 'ChatGPT-Kontingent, Wochenfenster' },
  { id: 'gemini', titel: 'Gemini', text: 'ein Lauf gleichzeitig' },
]
const MODI: { id: AuftragModus; titel: string; text: string }[] = [
  { id: 'bericht', titel: 'Nur berichten', text: 'Analysiert und schlägt einen Plan vor, ändert nichts.' },
  { id: 'plan_freigabe', titel: 'Plan zeigen, dann freigeben', text: 'Erstellt zuerst den Plan; die Umsetzung startet erst nach deiner Freigabe in derselben Sitzung.' },
  { id: 'umsetzen', titel: 'Direkt umsetzen', text: 'Ändert Dateien sofort im eigenen Branch.' },
]

const antwort = ref<AuftraegeAntwort | null>(null)
const projektListe = ref<Projekt[]>([])
const vorlagenListe = ref<Vorlage[]>([])
const vorlagenGeladen = ref(false)
const fehler = ref<string | null>(null)
const panel = ref<'neu' | 'vorschlaege' | 'detail' | null>(null)
const ausgewaehltId = ref<string | null>(null)
const busy = ref(false)
const bearbeitenAktiv = ref(false)
const nachfrageText = ref('')
const umsetzungHinweis = ref('')
const logs = ref<LogZeile[]>([])
const logElement = ref<HTMLElement | null>(null)
const jetzt = ref(Date.now())
const gezogenId = ref<string | null>(null)
const dropSpalte = ref<SpaltenStatus | null>(null)
const verschoben = ref(false)
const kiDetailsOffen = ref(false)
const poll = usePollStore()
const toast = useToastStore()
const reduziert = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const neuForm = reactive({ vorlageId: '', titel: '', text: '', projektKey: '', agent: 'claude' as AuftragAgent, modus: 'plan_freigabe' as AuftragModus, profil: 'bearbeiten_tests' as AuftragProfil, prioritaet: 3, zeitfenster: 'sofort' as Zeitfenster })
const vorschlaegeForm = reactive({ projektKey: '', agent: 'claude' as AuftragAgent })
const editForm = reactive({ titel: '', text: '', agent: 'claude' as AuftragAgent, modus: 'plan_freigabe' as AuftragModus, profil: 'lesen' as AuftragProfil, prioritaet: 3, zeitfenster: 'sofort' as Zeitfenster })

let uhrTimer: number | undefined
let logTimer: number | undefined

function spalteVon(status: AuftragStatus): SpaltenStatus {
  if (status === 'freigabe') return 'rueckfrage'
  return status === 'fehler' || status === 'abgebrochen' ? 'fertig' : status
}

function deduplizieren(liste: Auftrag[]): Auftrag[] {
  const nachId = new Map<string, Auftrag>()
  for (const auftrag of liste) nachId.set(auftrag.id, auftrag)
  return [...nachId.values()]
}

const eindeutigeAuftraege = computed(() => deduplizieren(antwort.value?.auftraege ?? []))
const spaltenInhalt = computed<Record<SpaltenStatus, Auftrag[]>>(() => {
  const result: Record<SpaltenStatus, Auftrag[]> = { eingang: [], geplant: [], laeuft: [], rueckfrage: [], fertig: [] }
  for (const auftrag of eindeutigeAuftraege.value) result[spalteVon(auftrag.status)].push(auftrag)
  for (const liste of Object.values(result)) liste.sort((a, b) => a.reihenfolge - b.reihenfolge || a.erstellt.localeCompare(b.erstellt))
  return result
})
const ausgewaehlt = computed(() => eindeutigeAuftraege.value.find((a) => a.id === ausgewaehltId.value) ?? null)
const projektGruppen = computed(() => {
  const gruppen = new Map<string, Projekt[]>()
  for (const projekt of projektListe.value) {
    const liste = gruppen.get(projekt.host) ?? []
    liste.push(projekt)
    gruppen.set(projekt.host, liste)
  }
  return [...gruppen.entries()].map(([host, liste]) => ({ host, liste }))
})
const neuProjekt = computed(() => projektAuswahl(neuForm.projektKey))
const vorschlaegeProjekt = computed(() => projektAuswahl(vorschlaegeForm.projektKey))

async function laden() {
  try {
    const neu = await listeAuftraege()
    const bisher = new Map(eindeutigeAuftraege.value.map((auftrag) => [auftrag.id, auftrag]))
    const zusammengefuehrt = deduplizieren(neu.auftraege).map((auftrag) => {
      const lokal = bisher.get(auftrag.id)
      if (!lokal) return auftrag
      Object.assign(lokal, auftrag)
      return lokal
    })
    antwort.value = { ...neu, auftraege: zusammengefuehrt }
    fehler.value = null
    if (ausgewaehltId.value && !ausgewaehlt.value) schliessen()
  } catch (err) {
    fehler.value = extractError(err)
  }
}

async function projekteLaden() {
  try {
    projektListe.value = await projekte()
    const standard = projektListe.value.find((projekt) => projekt.ausfuehrbar) ?? projektListe.value[0]
    if (!neuForm.projektKey && standard) neuForm.projektKey = projektKey(standard)
    if (!vorschlaegeForm.projektKey && standard) vorschlaegeForm.projektKey = projektKey(standard)
  } catch (err) { toast.error(extractError(err)) }
}

async function vorlagenLaden() {
  if (vorlagenGeladen.value) return
  try { vorlagenListe.value = await vorlagenAbrufen(); vorlagenGeladen.value = true }
  catch (err) { toast.error(extractError(err)) }
}

function projektKey(projekt: Projekt): string { return `${projekt.host}\u0000${projekt.pfad}` }
function projektAuswahl(key = neuForm.projektKey): Projekt | undefined { return projektListe.value.find((p) => projektKey(p) === key) }
function projektOption(projekt: Projekt): string {
  return `${projekt.name}${projekt.branch ? ` — ${projekt.branch}` : ''}${projekt.dirty ? ' · uncommittet' : ''}${projekt.ausfuehrbar ? '' : ` (${projekt.grund || 'nicht ausführbar'})`}`
}
function quellenLabel(quelle: Projekt['quelle']): string { return quelle === 'werkstatt' ? 'Werkstatt' : quelle }
function graphifyDatum(iso: string | null | undefined): string {
  if (!iso) return '–'
  const wert = new Date(iso)
  if (Number.isNaN(wert.getTime())) return '–'
  return wert.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function projektName(key: string): string { return projektListe.value.find((p) => projektKey(p) === key)?.name ?? 'Projekt' }
function vorlagenTitel(vorlage: Vorlage, projekt: string): string { return vorlage.titel.replace(/\{projekt\}/g, projekt) }
function vorlageAnwenden() {
  const vorlage = vorlagenListe.value.find((eintrag) => eintrag.id === neuForm.vorlageId)
  if (!vorlage) return
  Object.assign(neuForm, { titel: vorlagenTitel(vorlage, projektName(neuForm.projektKey)), text: vorlage.text, modus: vorlage.modus, profil: vorlage.profil, prioritaet: vorlage.prioritaet })
}

watch(() => neuForm.projektKey, (neuerKey, alterKey) => {
  const vorlage = vorlagenListe.value.find((eintrag) => eintrag.id === neuForm.vorlageId)
  if (!vorlage || neuForm.titel !== vorlagenTitel(vorlage, projektName(alterKey))) return
  neuForm.titel = vorlagenTitel(vorlage, projektName(neuerKey))
})

onMounted(() => {
  if (!document.getElementById('wall-fonts')) {
    const link = document.createElement('link')
    link.id = 'wall-fonts'; link.rel = 'stylesheet'
    link.href = 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap'
    document.head.appendChild(link)
  }
  poll.start('kanban', laden, REFRESH_MS)
  void projekteLaden()
  try { kiDetailsOffen.value = window.localStorage.getItem('cockpit-kanban-ki-details') === 'offen' } catch { /* Speicherung ist optional. */ }
  uhrTimer = window.setInterval(() => { jetzt.value = Date.now() }, 1000)
  window.addEventListener('keydown', tastatur)
})

onBeforeUnmount(() => {
  poll.stop('kanban')
  if (uhrTimer) window.clearInterval(uhrTimer)
  logPollingStoppen()
  window.removeEventListener('keydown', tastatur)
})

function tastatur(event: KeyboardEvent) { if (event.key === 'Escape') schliessen() }
function kiDetailsUmschalten() {
  kiDetailsOffen.value = !kiDetailsOffen.value
  try { window.localStorage.setItem('cockpit-kanban-ki-details', kiDetailsOffen.value ? 'offen' : 'kompakt') } catch { /* Private Modi können localStorage sperren. */ }
}
function schliessen() {
  panel.value = null; ausgewaehltId.value = null; bearbeitenAktiv.value = false; nachfrageText.value = ''; umsetzungHinweis.value = ''; logs.value = []; logPollingStoppen()
}
function neuOeffnen() { schliessen(); panel.value = 'neu'; void vorlagenLaden() }
function vorschlaegeOeffnen() { schliessen(); vorschlaegeForm.agent = 'claude'; panel.value = 'vorschlaege' }
function detailOeffnen(auftrag: Auftrag) {
  if (verschoben.value) return
  panel.value = 'detail'; ausgewaehltId.value = auftrag.id; bearbeitenAktiv.value = false; nachfrageText.value = ''
}

function editieren() {
  const a = ausgewaehlt.value
  if (!a) return
  Object.assign(editForm, { titel: a.titel, text: a.text, agent: a.agent, modus: a.modus, profil: a.profil, prioritaet: a.prioritaet, zeitfenster: a.zeitfenster })
  bearbeitenAktiv.value = true
}

function lokalAktualisieren(auftrag: Auftrag) {
  if (!antwort.value) return
  const nachId = new Map(deduplizieren(antwort.value.auftraege).map((eintrag) => [eintrag.id, eintrag]))
  nachId.set(auftrag.id, auftrag)
  antwort.value.auftraege = [...nachId.values()]
}

async function speichern() {
  const a = ausgewaehlt.value
  if (!a || !editForm.titel.trim() || !editForm.text.trim()) { toast.warning('Titel und Auftragstext sind Pflicht.'); return }
  busy.value = true
  try {
    lokalAktualisieren(await aendern(a.id, { titel: editForm.titel.trim(), text: editForm.text.trim(), agent: editForm.agent, modus: editForm.modus, profil: editForm.modus === 'bericht' ? 'lesen' : editForm.profil, prioritaet: editForm.prioritaet, zeitfenster: editForm.zeitfenster }))
    bearbeitenAktiv.value = false; toast.success('Auftrag gespeichert')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function neuAnlegen(planen: boolean) {
  const projekt = projektAuswahl()
  if (!neuForm.titel.trim() || !neuForm.text.trim() || !projekt) { toast.warning('Titel, Projekt und Auftragstext sind Pflicht.'); return }
  busy.value = true
  try {
    let auftrag = await anlegen({ titel: neuForm.titel.trim(), text: neuForm.text.trim(), host: projekt.host, projekt: projekt.pfad, agent: neuForm.agent, modus: neuForm.modus, profil: neuForm.modus === 'bericht' ? 'lesen' : neuForm.profil, prioritaet: neuForm.prioritaet, zeitfenster: neuForm.zeitfenster })
    if (planen) auftrag = await aendern(auftrag.id, { status: 'geplant' })
    lokalAktualisieren(auftrag)
    toast.success(planen ? 'Auftrag ist geplant' : 'Auftrag liegt im Eingang')
    Object.assign(neuForm, { vorlageId: '', titel: '', text: '', agent: 'claude', modus: 'plan_freigabe', profil: 'bearbeiten_tests', prioritaet: 3, zeitfenster: 'sofort' })
    schliessen()
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function analyseStarten() {
  const projekt = projektAuswahl(vorschlaegeForm.projektKey)
  if (!projekt) { toast.warning('Bitte ein Projekt auswählen.'); return }
  busy.value = true
  try {
    await vorschlaegeEinholen({ host: projekt.host, projekt: projekt.pfad, agent: vorschlaegeForm.agent })
    await laden()
    schliessen()
    toast.success(`Analyse für ${projekt.name} eingeplant – Vorschläge erscheinen im Eingang.`)
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function startenAktion() { await auftragAktion((id) => starten(id), 'Auftrag gestartet') }
async function stoppenAktion() { await auftragAktion((id) => stoppen(id), 'Auftrag gestoppt') }
async function statusSetzen(status: AuftragStatus, meldung: string) { await auftragAktion((id) => aendern(id, { status }), meldung) }
async function umsetzenAktion() {
  const id = ausgewaehltId.value
  if (!id) return
  busy.value = true
  try {
    lokalAktualisieren(await umsetzen(id, umsetzungHinweis.value))
    umsetzungHinweis.value = ''
    toast.success('Plan freigegeben – Umsetzung gestartet')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}
async function auftragAktion(fn: (id: string) => Promise<Auftrag>, meldung: string) {
  const id = ausgewaehltId.value
  if (!id) return
  busy.value = true
  try { lokalAktualisieren(await fn(id)); toast.success(meldung) } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function nachfrageSenden() {
  const a = ausgewaehlt.value
  const text = nachfrageText.value.trim()
  if (!a || !text) { toast.warning('Bitte eine Antwort oder Nachfrage eingeben.'); return }
  busy.value = true
  try { lokalAktualisieren(await nachfragen(a.id, text)); nachfrageText.value = ''; toast.success('Nachricht an die Sitzung gesendet') }
  catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function loeschenAktion() {
  const a = ausgewaehlt.value
  if (!a || !window.confirm(`Auftrag „${a.titel}“ wirklich löschen?`)) return
  busy.value = true
  try {
    await loeschen(a.id)
    if (antwort.value) antwort.value.auftraege = antwort.value.auftraege.filter((eintrag) => eintrag.id !== a.id)
    schliessen(); toast.success('Auftrag gelöscht')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

watch(() => `${ausgewaehltId.value ?? ''}:${ausgewaehlt.value?.status ?? ''}`, () => {
  logPollingStoppen()
  logs.value = []
  if (!ausgewaehltId.value) return
  void logsLaden(true)
  if (ausgewaehlt.value?.status === 'laeuft') logTimer = window.setInterval(() => { void logsLaden(false) }, 5000)
})

function logPollingStoppen() { if (logTimer) { window.clearInterval(logTimer); logTimer = undefined } }
async function logsLaden(fehlerZeigen: boolean) {
  const id = ausgewaehltId.value
  if (!id) return
  try {
    logs.value = (await logLesen(id, 80)).zeilen
    await nextTick()
    if (logElement.value) logElement.value.scrollTop = logElement.value.scrollHeight
  } catch (err) { if (fehlerZeigen) toast.error(extractError(err)) }
}

function dauer(auftrag: Auftrag): number | null {
  if (auftrag.status === 'laeuft' && auftrag.gestartet) return Math.max(0, Math.floor((jetzt.value - new Date(auftrag.gestartet).getTime()) / 1000))
  return auftrag.dauer_s
}
function dauerText(sekunden: number | null): string {
  if (sekunden == null) return '–'
  const stunden = Math.floor(sekunden / 3600)
  const minuten = Math.floor((sekunden % 3600) / 60)
  const rest = Math.floor(sekunden % 60)
  return stunden ? `${stunden}:${String(minuten).padStart(2, '0')}:${String(rest).padStart(2, '0')}` : `${String(minuten).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}
function tokens(anzahl: number | null): string {
  if (anzahl == null) return '–'
  if (anzahl >= 1_000_000) return `${(anzahl / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio.`
  if (anzahl >= 1000) return `${(anzahl / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} k`
  return String(anzahl)
}
function datum(iso: string | null): string { return iso ? new Date(iso).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }) : '–' }
function kosten(wert: number | null): string { return wert == null ? '–' : `${wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $` }
function zeitAusLog(iso: string | null): string { return iso ? new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }

function dragStart(event: DragEvent, auftrag: Auftrag) {
  gezogenId.value = auftrag.id; verschoben.value = false
  event.dataTransfer?.setData('text/plain', auftrag.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function dragEnd() { gezogenId.value = null; dropSpalte.value = null; window.setTimeout(() => { verschoben.value = false }, 50) }
function darfAblegen(ziel: SpaltenStatus): boolean {
  const quelle = antwort.value?.auftraege.find((a) => a.id === gezogenId.value)
  if (!quelle) return false
  const start = spalteVon(quelle.status)
  return start === ziel || ((start === 'eingang' || start === 'geplant') && (ziel === 'eingang' || ziel === 'geplant'))
}
function dragOver(event: DragEvent, ziel: SpaltenStatus) {
  if (!darfAblegen(ziel)) return
  event.preventDefault(); dropSpalte.value = ziel
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}
async function drop(event: DragEvent, ziel: SpaltenStatus, vorId?: string) {
  event.preventDefault()
  if (!darfAblegen(ziel) || !gezogenId.value || !antwort.value) return
  const id = gezogenId.value
  if (vorId === id) { dragEnd(); return }
  const quelle = antwort.value.auftraege.find((a) => a.id === id)
  if (!quelle) return
  const bisher = spalteVon(quelle.status)
  const zielListe = spaltenInhalt.value[ziel].filter((a) => a.id !== id)
  const position = vorId ? Math.max(0, zielListe.findIndex((a) => a.id === vorId)) : zielListe.length
  zielListe.splice(position, 0, quelle)
  const patches = zielListe.map((a, index) => ({ a, patch: { reihenfolge: index + 1, ...(a.id === id && bisher !== ziel ? { status: ziel as AuftragStatus } : {}) } }))
  if (bisher !== ziel) quelle.status = ziel
  zielListe.forEach((a, index) => { a.reihenfolge = index + 1 })
  verschoben.value = true; gezogenId.value = null; dropSpalte.value = null
  try {
    await Promise.all(patches.map(({ a, patch }) => aendern(a.id, patch)))
    await laden()
  } catch (err) { toast.error(extractError(err)); await laden() }
}
</script>

<template>
  <div class="kanban-seite" :class="{ reduziert }">
    <header class="kopf">
      <div class="titel"><span class="marke">flowaudit</span><span class="untertitel">Aufträge</span></div>
      <div class="kopf-mitte mono"><span v-if="fehler" class="fehler">{{ fehler }}</span><span v-else class="dim">LLM-Aufträge steuern und verfolgen</span></div>
      <nav class="kopf-rechts" aria-label="Seitennavigation">
        <RouterLink to="/wall" class="knopf klein ghost">Zur Wand</RouterLink>
        <RouterLink to="/chat" class="knopf klein ghost">LLM-Konsole</RouterLink>
        <button class="knopf klein ghost" type="button" @click="vorschlaegeOeffnen"><Lightbulb :size="14" /> Vorschläge einholen</button>
        <button class="knopf klein" type="button" @click="neuOeffnen">Neuer Auftrag</button>
      </nav>
    </header>

    <section class="kapazitaet" aria-label="Kapazität">
      <strong class="mono">läuft {{ antwort?.kapazitaet.laufend ?? '–' }} / max {{ antwort?.kapazitaet.parallel_max ?? '–' }}</strong>
      <span v-if="antwort?.kapazitaet.pause_grund" class="pause">· {{ antwort.kapazitaet.pause_grund }}</span>
    </section>

    <section class="ki-nutzung-bereich" aria-labelledby="ki-nutzung-titel">
      <header class="ki-bereich-kopf"><div><h2 id="ki-nutzung-titel">LLM-Nutzung</h2><span class="mono dim">Kontingente und Tokenverbrauch</span></div><button class="details-knopf" type="button" :aria-expanded="kiDetailsOffen" aria-controls="ki-nutzung-inhalt" @click="kiDetailsUmschalten">Details <ChevronDown :size="15" :class="{ gedreht: kiDetailsOffen }" /></button></header>
      <div id="ki-nutzung-inhalt"><KiNutzungPanel :offen="kiDetailsOffen" /></div>
    </section>

    <main class="board" aria-label="Kanban-Board">
      <section v-for="spalte in SPALTEN" :key="spalte.id" class="spalte" :class="{ ziel: dropSpalte === spalte.id }" @dragover="dragOver($event, spalte.id)" @dragleave.self="dropSpalte = null" @drop="drop($event, spalte.id)">
        <header class="spalten-kopf"><h2>{{ spalte.titel }}</h2><span class="mono">{{ spaltenInhalt[spalte.id].length }}</span></header>
        <TransitionGroup name="karten" tag="div" class="karten" :css="false">
          <article v-for="auftrag in spaltenInhalt[spalte.id]" :key="auftrag.id" class="auftrag" :class="[`status-${auftrag.status}`, { gezogen: gezogenId === auftrag.id }]" draggable="true" tabindex="0" @dragstart="dragStart($event, auftrag)" @dragend="dragEnd" @dragover="dragOver($event, spalte.id)" @drop.stop="drop($event, spalte.id, auftrag.id)" @click="detailOeffnen(auftrag)" @keydown.enter="detailOeffnen(auftrag)">
            <div class="karten-titel"><GripVertical :size="15" class="griff" aria-hidden="true" /><h3>{{ auftrag.titel }}</h3><span v-if="auftrag.titel.startsWith('Vorschlag: ')" class="vorschlag-marke"><Lightbulb :size="10" /> Vorschlag</span><span v-if="auftrag.status === 'freigabe'" class="status-marke freigabe">Plan liegt vor</span><span v-else-if="auftrag.status === 'fehler'" class="status-marke rot">Fehler</span><span v-else-if="auftrag.status === 'abgebrochen'" class="status-marke grau">Abgebrochen</span></div>
            <p class="projekt mono">{{ auftrag.projekt_name }} · {{ auftrag.host }}</p>
            <div class="chips"><span :class="['agent-chip', `agent-${auftrag.agent}`]">{{ AGENT_LABELS[auftrag.agent] }}</span><span class="modus-chip">{{ MODUS_LABELS[auftrag.modus] }}</span><span>{{ PROFIL_LABELS[auftrag.profil] }}</span><span>P{{ auftrag.prioritaet }}</span><span>{{ ZEIT_LABELS[auftrag.zeitfenster] }}</span></div>
            <template v-if="auftrag.status === 'laeuft'">
              <div class="lauf"><i /><span>läuft</span><strong class="mono">{{ dauerText(dauer(auftrag)) }}</strong></div>
              <p v-if="auftrag.letzte_zeile" class="letzte mono" :title="auftrag.letzte_zeile">{{ auftrag.letzte_zeile }}</p>
            </template>
            <template v-if="spalte.id === 'fertig'">
              <p v-if="auftrag.fehler" class="karten-fehler">{{ auftrag.fehler }}</p>
              <div class="abschluss mono"><span>{{ dauerText(dauer(auftrag)) }}</span><span>{{ kosten(auftrag.kosten_usd) }}</span><span>{{ tokens((auftrag.tokens_in ?? 0) + (auftrag.tokens_out ?? 0)) }} Tok.</span><a v-if="auftrag.diff_url" :href="auftrag.diff_url" target="_blank" rel="noopener" @click.stop>Diff ↗</a></div>
            </template>
          </article>
        </TransitionGroup>
        <button v-if="!spaltenInhalt[spalte.id].length" class="leere-spalte" type="button" @click="spalte.id === 'eingang' ? neuOeffnen() : undefined">{{ spalte.id === 'eingang' ? '+ Auftrag anlegen' : 'Keine Aufträge' }}</button>
      </section>
    </main>

    <Transition name="blende"><button v-if="panel" class="panel-blende" aria-label="Panel schließen" @click="schliessen" /></Transition>
    <Transition name="panel">
      <aside v-if="panel" class="panel" :class="{ 'panel-klein': panel === 'vorschlaege' }" :aria-label="panel === 'neu' ? 'Neuer Auftrag' : panel === 'vorschlaege' ? 'Vorschläge einholen' : 'Auftragsdetails'">
        <header class="panel-kopf"><div><span class="mono dim">{{ panel === 'neu' ? 'NEU' : panel === 'vorschlaege' ? 'ANALYSE' : ausgewaehlt ? STATUS_LABELS[ausgewaehlt.status].toUpperCase() : '' }}</span><h2>{{ panel === 'neu' ? 'Neuer Auftrag' : panel === 'vorschlaege' ? 'Vorschläge einholen' : ausgewaehlt?.titel }}</h2></div><button class="icon-knopf" type="button" aria-label="Schließen" @click="schliessen"><X :size="21" /></button></header>

        <form v-if="panel === 'neu'" class="formular" @submit.prevent="neuAnlegen(false)">
          <label>Vorlage<select v-model="neuForm.vorlageId" @change="vorlageAnwenden"><option value="">– ohne Vorlage –</option><option v-for="vorlage in vorlagenListe" :key="vorlage.id" :value="vorlage.id">{{ vorlage.titel }}</option></select></label>
          <label>Titel<input v-model="neuForm.titel" required placeholder="Kurzer, eindeutiger Auftrag" /></label>
          <label>Projekt<select v-model="neuForm.projektKey" required><optgroup v-for="gruppe in projektGruppen" :key="gruppe.host" :label="gruppe.host"><option v-for="projekt in gruppe.liste" :key="projektKey(projekt)" :value="projektKey(projekt)" :disabled="!projekt.ausfuehrbar">{{ projektOption(projekt) }}</option></optgroup></select></label>
          <div v-if="neuProjekt" class="projekt-details"><span :class="['quellen-chip', `quelle-${neuProjekt.quelle}`]">{{ quellenLabel(neuProjekt.quelle) }}</span><span v-for="technik in (neuProjekt.technologien ?? []).slice(0, 4)" :key="technik" class="technik-chip">{{ technik }}</span><span class="graphify mono">graphify: {{ graphifyDatum(neuProjekt.graphify_stand) }}</span></div>
          <p class="projekt-hinweis">Projektliste aus flow-agent (alle Hosts) und Werkstatt.</p>
          <label>Auftragstext<textarea v-model="neuForm.text" required rows="7" placeholder="Behebe …, führe die Tests aus, committe mit sprechender Meldung" /></label>
          <fieldset class="agent-auswahl"><legend>Agent</legend><label v-for="agent in AGENTEN" :key="agent.id" class="agent-radio" :class="{ aktiv: neuForm.agent === agent.id }"><input v-model="neuForm.agent" type="radio" name="agent" :value="agent.id" /><span><strong>{{ agent.titel }}</strong><small>{{ agent.text }}</small></span></label></fieldset>
          <p v-if="neuForm.agent === 'codex'" class="formular-hinweis codex-hinweis mono">Läuft auf dem NUC ohne Sandbox-Isolierung (bwrap nicht verfügbar) – Schutz durch eigenen Worktree und Branch.</p>
          <p v-if="neuForm.agent === 'gemini'" class="formular-hinweis mono">Gemini CLI muss auf dem Host angemeldet sein (API-Schlüssel in ~/.gemini/.env oder Antigravity-Login).</p>
          <fieldset class="agent-auswahl modus-auswahl"><legend>Vorgehen</legend><label v-for="modus in MODI" :key="modus.id" class="agent-radio modus-radio" :class="{ aktiv: neuForm.modus === modus.id }"><input v-model="neuForm.modus" type="radio" name="modus" :value="modus.id" /><span><strong>{{ modus.titel }}</strong><small>{{ modus.text }}</small></span></label></fieldset>
          <p class="formular-hinweis modus-hinweis">Das Profil gilt für die Umsetzung; Bericht und Plan laufen immer lesend.</p>
          <fieldset v-if="neuForm.modus !== 'bericht'"><legend>Profil</legend><label v-for="profil in PROFILE" :key="profil.id" class="radio"><input v-model="neuForm.profil" type="radio" name="profil" :value="profil.id" /><span><strong>{{ profil.titel }}</strong><small>{{ profil.text }}</small></span></label></fieldset>
          <div class="formular-zeile"><label>Priorität<select v-model.number="neuForm.prioritaet"><option v-for="p in 5" :key="p" :value="p">P{{ p }}</option></select></label><label>Zeitfenster<select v-model="neuForm.zeitfenster"><option value="sofort">sofort</option><option value="nachts">nachts</option><option value="nach_reset">nach Reset</option></select></label></div>
          <div class="aktionen"><button class="knopf" type="submit" :disabled="busy">In Eingang legen</button><button class="knopf ghost" type="button" :disabled="busy" @click="neuAnlegen(true)">Sofort planen</button></div>
        </form>

        <form v-else-if="panel === 'vorschlaege'" class="formular vorschlaege-form" @submit.prevent="analyseStarten">
          <p class="erklaerung">Der Agent liest Git-Verlauf, GitHub (Issues, PRs, CI), graphify-Analyse und Code und legt 5–10 priorisierte Vorschläge als Karten in den Eingang. Es wird nichts geändert.</p>
          <label>Projekt<select v-model="vorschlaegeForm.projektKey" required><optgroup v-for="gruppe in projektGruppen" :key="gruppe.host" :label="gruppe.host"><option v-for="projekt in gruppe.liste" :key="projektKey(projekt)" :value="projektKey(projekt)" :disabled="!projekt.ausfuehrbar">{{ projektOption(projekt) }}</option></optgroup></select></label>
          <div v-if="vorschlaegeProjekt" class="projekt-details"><span :class="['quellen-chip', `quelle-${vorschlaegeProjekt.quelle}`]">{{ quellenLabel(vorschlaegeProjekt.quelle) }}</span><span v-for="technik in (vorschlaegeProjekt.technologien ?? []).slice(0, 4)" :key="technik" class="technik-chip">{{ technik }}</span><span class="graphify mono">graphify: {{ graphifyDatum(vorschlaegeProjekt.graphify_stand) }}</span></div>
          <p class="projekt-hinweis">Projektliste aus flow-agent (alle Hosts) und Werkstatt.</p>
          <fieldset class="agent-auswahl"><legend>Agent</legend><label v-for="agent in AGENTEN" :key="agent.id" class="agent-radio" :class="{ aktiv: vorschlaegeForm.agent === agent.id }"><input v-model="vorschlaegeForm.agent" type="radio" name="vorschlaege-agent" :value="agent.id" /><span><strong>{{ agent.titel }}</strong><small>{{ agent.text }}</small></span></label></fieldset>
          <p v-if="vorschlaegeForm.agent === 'codex'" class="formular-hinweis codex-hinweis mono">Läuft auf dem NUC ohne Sandbox-Isolierung (bwrap nicht verfügbar) – Schutz durch eigenen Worktree und Branch.</p>
          <div class="aktionen"><button class="knopf" type="submit" :disabled="busy">Analyse starten</button><button class="knopf ghost" type="button" @click="schliessen">Abbrechen</button></div>
        </form>

        <div v-else-if="ausgewaehlt" class="detail">
          <form v-if="bearbeitenAktiv" class="formular edit-form" @submit.prevent="speichern">
            <label>Titel<input v-model="editForm.titel" required /></label><label>Auftragstext<textarea v-model="editForm.text" rows="7" required /></label>
            <div class="formular-zeile"><label>Agent<select v-model="editForm.agent"><option v-for="agent in AGENTEN" :key="agent.id" :value="agent.id">{{ agent.titel }}</option></select></label><label>Vorgehen<select v-model="editForm.modus"><option v-for="modus in MODI" :key="modus.id" :value="modus.id">{{ modus.titel }}</option></select></label></div>
            <label v-if="editForm.modus !== 'bericht'">Profil<select v-model="editForm.profil"><option v-for="profil in PROFILE" :key="profil.id" :value="profil.id">{{ profil.titel }}</option></select></label>
            <label>Priorität<select v-model.number="editForm.prioritaet"><option v-for="p in 5" :key="p" :value="p">P{{ p }}</option></select></label>
            <label>Zeitfenster<select v-model="editForm.zeitfenster"><option value="sofort">sofort</option><option value="nachts">nachts</option><option value="nach_reset">nach Reset</option></select></label>
            <div class="aktionen"><button class="knopf" :disabled="busy">Speichern</button><button class="knopf ghost" type="button" @click="bearbeitenAktiv = false">Abbrechen</button></div>
          </form>
          <template v-else>
            <div class="detail-chips chips"><span :class="['agent-chip', `agent-${ausgewaehlt.agent}`]">{{ AGENT_LABELS[ausgewaehlt.agent] }}</span><span class="modus-chip">{{ MODUS_LABELS[ausgewaehlt.modus] }}</span><span>{{ PROFIL_LABELS[ausgewaehlt.profil] }}</span><span>P{{ ausgewaehlt.prioritaet }}</span><span>{{ ZEIT_LABELS[ausgewaehlt.zeitfenster] }}</span></div>
            <section class="detail-block"><h3>Auftrag</h3><p class="prosa">{{ ausgewaehlt.text }}</p></section>
            <section v-if="ausgewaehlt.status === 'freigabe'" class="detail-block freigabe-block"><h3>Plan zur Freigabe</h3><pre class="plan mono">{{ ausgewaehlt.ergebnis || 'Der Plan wurde noch nicht übermittelt.' }}</pre><label>Hinweis zur Umsetzung (optional)<textarea v-model="umsetzungHinweis" rows="3" placeholder="Ergänzung oder Einschränkung für die Umsetzung …" /></label><div class="aktionen"><button class="knopf" type="button" :disabled="busy" @click="umsetzenAktion">Umsetzen</button><button class="knopf ghost" type="button" :disabled="busy" @click="statusSetzen('fertig', 'Plan als Bericht behalten')">Nur Bericht behalten</button></div></section>
            <dl class="metadaten"><div><dt>ID</dt><dd class="mono">{{ ausgewaehlt.id }}</dd></div><div><dt>Status · Reihenfolge</dt><dd>{{ STATUS_LABELS[ausgewaehlt.status] }} · {{ ausgewaehlt.reihenfolge }}</dd></div><div><dt>Projekt</dt><dd>{{ ausgewaehlt.projekt_name }} · {{ ausgewaehlt.host }}</dd></div><div><dt>Pfad</dt><dd class="mono">{{ ausgewaehlt.projekt }}</dd></div><div><dt>Branch</dt><dd class="mono">{{ ausgewaehlt.branch ?? '–' }}</dd></div><div><dt>Worktree</dt><dd class="mono">{{ ausgewaehlt.worktree ?? '–' }}</dd></div><div><dt>Sitzung</dt><dd class="mono">{{ ausgewaehlt.session_id ?? '–' }}</dd></div><div><dt>Freigegeben</dt><dd>{{ datum(ausgewaehlt.freigegeben) }}</dd></div><div><dt>Erstellt</dt><dd>{{ datum(ausgewaehlt.erstellt) }}</dd></div><div><dt>Aktualisiert</dt><dd>{{ datum(ausgewaehlt.aktualisiert) }}</dd></div><div><dt>Gestartet</dt><dd>{{ datum(ausgewaehlt.gestartet) }}</dd></div><div><dt>Beendet</dt><dd>{{ datum(ausgewaehlt.beendet) }}</dd></div><div><dt>Dauer</dt><dd class="mono">{{ dauerText(dauer(ausgewaehlt)) }}</dd></div><div><dt>Kosten</dt><dd class="mono">{{ kosten(ausgewaehlt.kosten_usd) }}</dd></div><div><dt>Tokens</dt><dd class="mono">{{ tokens(ausgewaehlt.tokens_in) }} ein · {{ tokens(ausgewaehlt.tokens_out) }} aus</dd></div><div><dt>Turns</dt><dd>{{ ausgewaehlt.turns ?? '–' }}</dd></div><div><dt>Letzte Zeile</dt><dd class="mono">{{ ausgewaehlt.letzte_zeile ?? '–' }}</dd></div></dl>
            <section v-if="ausgewaehlt.status !== 'freigabe' && (ausgewaehlt.ergebnis || ausgewaehlt.fehler)" class="detail-block"><h3>{{ ausgewaehlt.fehler ? 'Fehler' : 'Ergebnis' }}</h3><p class="prosa" :class="{ 'fehler-text': ausgewaehlt.fehler }">{{ ausgewaehlt.fehler ?? ausgewaehlt.ergebnis }}</p><a v-if="ausgewaehlt.diff_url" class="diff-link" :href="ausgewaehlt.diff_url" target="_blank" rel="noopener"><ExternalLink :size="14" /> Diff öffnen</a></section>
            <section class="detail-block protokoll-block"><div class="block-kopf"><h3>Protokoll</h3><span v-if="ausgewaehlt.status === 'laeuft'" class="live-klein"><i /> LIVE</span></div><div ref="logElement" class="protokoll mono"><p v-for="(zeile, index) in logs" :key="`${zeile.ts}-${index}`" :class="`log-${zeile.art}`"><time>{{ zeitAusLog(zeile.ts) }}</time><span>{{ zeile.text }}</span></p><p v-if="!logs.length" class="dim">Noch keine Protokollzeilen.</p></div></section>
            <div v-if="ausgewaehlt.status === 'rueckfrage' || ['fertig', 'fehler', 'abgebrochen'].includes(ausgewaehlt.status)" class="nachfrage"><label>{{ ausgewaehlt.status === 'rueckfrage' ? 'Antwort / Nachfrage' : 'Nachfrage an dieselbe Sitzung' }}<textarea v-model="nachfrageText" rows="3" placeholder="Nachricht eingeben …" /></label><button class="knopf" type="button" :disabled="busy" @click="nachfrageSenden"><Send :size="14" /> Senden</button></div>
            <div class="aktionen detail-aktionen">
              <template v-if="ausgewaehlt.status === 'eingang' || ausgewaehlt.status === 'geplant'"><button class="knopf" type="button" :disabled="busy" @click="startenAktion"><Play :size="14" /> Starten</button><button class="knopf ghost" type="button" @click="editieren"><Edit3 :size="14" /> Bearbeiten</button><button class="knopf gefahr ghost" type="button" :disabled="busy" @click="loeschenAktion"><Trash2 :size="14" /> Löschen</button></template>
              <button v-else-if="ausgewaehlt.status === 'laeuft'" class="knopf gefahr" type="button" :disabled="busy" @click="stoppenAktion"><Square :size="13" /> Stoppen</button>
              <template v-else-if="ausgewaehlt.status === 'rueckfrage'"><button class="knopf" type="button" :disabled="busy" @click="statusSetzen('fertig', 'Auftrag als fertig markiert')">Als fertig markieren</button></template>
              <template v-else-if="ausgewaehlt.status === 'freigabe'" />
              <template v-else><button class="knopf ghost" type="button" :disabled="busy" @click="statusSetzen('eingang', 'Auftrag liegt wieder im Eingang')">Erneut in Eingang</button><button class="knopf gefahr ghost" type="button" :disabled="busy" @click="loeschenAktion"><Trash2 :size="14" /> Löschen</button></template>
            </div>
          </template>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.kanban-seite {
  --grund: #0B1020; --flaeche: #131A2E; --flaeche-2: #1A2340; --linie: #263054;
  --text: #E7ECF7; --text-2: #AAB3CF; --text-3: #7F89AB; --akzent: #F2B84B;
  --ok: #4CC38A; --warn: #F2B84B; --krit: #F26D6D; --info: #6FA8FF;
  --display: 'Barlow Condensed', 'Arial Narrow', Arial, sans-serif;
  --body: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', SFMono-Regular, Consolas, monospace;
  min-height: 100vh; background: var(--grund); color: var(--text); font-family: var(--body); overflow-x: hidden;
}
button, input, textarea, select { font: inherit; } button { cursor: pointer; } button:disabled { cursor: wait; opacity: .55; }
.mono { font-family: var(--mono); } .dim { color: var(--text-3); }
.kopf { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 14px 26px 16px; border-bottom: 1px solid var(--linie); }
.marke { font-family: var(--display); font-size: 28px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.untertitel { margin-left: 12px; font-family: var(--mono); font-size: 12px; letter-spacing: .14em; color: var(--text-3); text-transform: uppercase; }
.kopf-mitte { text-align: center; font-size: 12px; }.kopf-rechts { display: flex; justify-content: flex-end; align-items: center; gap: 8px; }
.fehler, .fehler-text { color: var(--krit); }
.knopf { display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-family: var(--display); font-weight: 700; letter-spacing: .06em; text-transform: uppercase; background: var(--akzent); color: #1A1200; border: 1px solid var(--akzent); border-radius: 5px; padding: 8px 14px; font-size: 14px; text-decoration: none; white-space: nowrap; }
.knopf.klein { padding: 6px 12px; font-size: 13px; }.knopf.ghost { background: transparent; color: var(--text-2); border-color: var(--linie); }.knopf:hover { filter: brightness(1.08); }.knopf.gefahr { background: var(--krit); border-color: var(--krit); color: white; }.knopf.gefahr.ghost { background: transparent; color: var(--krit); }
.kapazitaet { min-height: 34px; display: flex; align-items: center; gap: 7px; padding: 5px 26px; border-bottom: 1px solid var(--linie); background: #0D1428; font-size: 11px; color: var(--text-2); }
.kapazitaet > strong { color: var(--ok); font-size: 10px; text-transform: uppercase; letter-spacing: .05em; }.pause { color: var(--warn); font-family: var(--mono); }
.ki-nutzung-bereich { padding: 10px 18px 11px; border-bottom: 1px solid var(--linie); background: #0D1428; }.ki-bereich-kopf { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }.ki-bereich-kopf > div { display: flex; align-items: baseline; gap: 9px; }.ki-bereich-kopf h2 { margin: 0; font-family: var(--display); font-size: 18px; letter-spacing: .06em; text-transform: uppercase; }.ki-bereich-kopf span { font-size: 8px; }.details-knopf { display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; border: 1px solid var(--linie); border-radius: 5px; background: transparent; color: var(--text-2); font-family: var(--display); font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }.details-knopf:hover { border-color: var(--akzent); color: var(--akzent); }.details-knopf svg { transition: transform .18s ease; }.details-knopf svg.gedreht { transform: rotate(180deg); }
.board { display: grid; grid-template-columns: repeat(5, minmax(245px, 1fr)); gap: 12px; padding: 16px 18px 40px; align-items: start; overflow-x: auto; }
.spalte { min-width: 0; min-height: calc(100vh - 150px); background: rgba(19, 26, 46, .68); border: 1px solid var(--linie); border-radius: 9px; padding: 10px; transition: border-color .15s, background .15s; }.spalte.ziel { border-color: var(--akzent); background: rgba(242, 184, 75, .045); }
.spalten-kopf { display: flex; align-items: center; justify-content: space-between; padding: 2px 3px 10px; }.spalten-kopf h2 { margin: 0; font-family: var(--display); font-size: 20px; letter-spacing: .05em; text-transform: uppercase; }.spalten-kopf span { min-width: 22px; padding: 2px 6px; text-align: center; color: var(--text-3); background: var(--flaeche-2); border-radius: 10px; font-size: 10px; }
.karten { display: flex; flex-direction: column; gap: 9px; }.auftrag { position: relative; background: var(--flaeche-2); border: 1px solid var(--linie); border-radius: 7px; padding: 11px 11px 10px; box-shadow: 0 5px 16px rgba(0,0,0,.12); cursor: pointer; transition: transform .16s ease, border-color .16s ease, opacity .16s ease; }.auftrag:hover, .auftrag:focus-visible { border-color: #42517F; transform: translateY(-1px); outline: none; }.auftrag.gezogen { opacity: .35; }.auftrag.status-laeuft { border-left: 2px solid var(--ok); }.auftrag.status-rueckfrage, .auftrag.status-freigabe { border-left: 2px solid var(--akzent); }.auftrag.status-freigabe { box-shadow: inset 0 0 18px rgba(242,184,75,.035), 0 5px 16px rgba(0,0,0,.12); }.auftrag.status-fehler { border-left: 2px solid var(--krit); }.auftrag.status-abgebrochen { border-left: 2px solid var(--text-3); }
.karten-titel { display: flex; align-items: flex-start; gap: 5px; }.karten-titel h3 { flex: 1; margin: 0; font-family: var(--display); font-size: 17px; line-height: 1.12; letter-spacing: .015em; }.griff { flex: 0 0 auto; margin: 1px 1px 0 -5px; color: var(--text-3); cursor: grab; }.projekt { margin: 7px 0 8px; color: var(--text-3); font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.chips { display: flex; flex-wrap: wrap; gap: 4px; }.chips span, .status-marke { border: 1px solid #334067; border-radius: 10px; padding: 2px 6px; color: var(--text-2); font-family: var(--mono); font-size: 8px; line-height: 1.3; }.status-marke { margin-left: 4px; text-transform: uppercase; }.status-marke.rot { color: var(--krit); border-color: rgba(242,109,109,.45); }.status-marke.grau { color: var(--text-3); }
.status-marke.freigabe { color: var(--akzent); border-color: rgba(242,184,75,.6); background: rgba(242,184,75,.1); }.chips .modus-chip { color: #D7C8A2; border-color: rgba(242,184,75,.32); }
.vorschlag-marke { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 3px; padding: 2px 5px; border: 1px solid rgba(242,184,75,.45); border-radius: 9px; background: rgba(242,184,75,.08); color: var(--akzent); font-family: var(--mono); font-size: 7px; text-transform: uppercase; }
.chips .agent-chip.agent-claude { color: #F2AA6B; border-color: rgba(231,154,90,.55); background: rgba(231,154,90,.08); }.chips .agent-chip.agent-codex { color: #60D5B7; border-color: rgba(76,195,165,.55); background: rgba(76,195,165,.08); }.chips .agent-chip.agent-gemini { color: #7DB5FF; border-color: rgba(111,168,255,.55); background: rgba(111,168,255,.08); }
.lauf { display: flex; align-items: center; gap: 6px; margin-top: 9px; color: var(--ok); font-size: 10px; text-transform: uppercase; }.lauf i, .live-klein i { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 3px rgba(76,195,138,.13); animation: puls 1.6s ease-in-out infinite; }.lauf strong { margin-left: auto; font-size: 10px; }.letzte { margin: 7px 0 0; padding: 5px 6px; background: #0E1528; color: var(--text-3); border-radius: 3px; font-size: 9px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }.karten-fehler { margin: 8px 0 0; color: var(--krit); font-size: 10px; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }.abschluss { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; padding-top: 7px; border-top: 1px solid var(--linie); color: var(--text-3); font-size: 8px; }.abschluss a { margin-left: auto; color: var(--akzent); text-decoration: none; }.leere-spalte { width: 100%; padding: 25px 5px; border: 1px dashed var(--linie); border-radius: 6px; color: var(--text-3); background: transparent; font-size: 11px; }
.karten-move { transition: transform .25s ease; }.karten-enter-active, .karten-leave-active { transition: opacity .18s ease, transform .18s ease; }.karten-enter-from, .karten-leave-to { opacity: 0; transform: scale(.97); }
.panel-blende { position: fixed; z-index: 30; inset: 0; border: 0; background: rgba(4, 7, 16, .6); backdrop-filter: blur(2px); }.panel { position: fixed; z-index: 31; top: 0; right: 0; width: min(620px, 94vw); height: 100vh; overflow-y: auto; background: #10172B; border-left: 1px solid var(--linie); box-shadow: -18px 0 50px rgba(0,0,0,.4); }.panel-kopf { position: sticky; z-index: 2; top: 0; display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 19px 22px 16px; background: rgba(16,23,43,.96); border-bottom: 1px solid var(--linie); backdrop-filter: blur(8px); }.panel-kopf h2 { margin: 2px 0 0; font-family: var(--display); font-size: 27px; line-height: 1.1; }.panel-kopf span { font-size: 9px; letter-spacing: .14em; }.icon-knopf { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid var(--linie); border-radius: 5px; background: transparent; color: var(--text-2); }.panel-enter-active, .panel-leave-active, .blende-enter-active, .blende-leave-active { transition: transform .24s cubic-bezier(.2,.7,.2,1), opacity .2s ease; }.panel-enter-from, .panel-leave-to { transform: translateX(100%); }.blende-enter-from, .blende-leave-to { opacity: 0; }
.panel.panel-klein { width: min(540px, 94vw); }.erklaerung { margin: 0; padding: 11px 12px; border-left: 2px solid var(--akzent); background: rgba(242,184,75,.05); color: var(--text-2); font-size: 11px; line-height: 1.55; }.formular-hinweis { margin: -8px 0 0; color: #7DB5FF; font-size: 9px; line-height: 1.5; }
.codex-hinweis { color: #60D5B7; }.projekt-details { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; margin-top: -9px; color: var(--text-3); font-size: 9px; }.quellen-chip, .technik-chip { padding: 2px 6px; border: 1px solid var(--linie); border-radius: 9px; font-family: var(--mono); }.quellen-chip { color: var(--akzent); border-color: rgba(242,184,75,.4); }.quelle-flow-agent { color: #60D5B7; border-color: rgba(76,195,165,.45); }.quelle-work_dirs { color: #7DB5FF; border-color: rgba(111,168,255,.45); }.graphify { margin-left: auto; }.projekt-hinweis { margin: -10px 0 0; color: var(--text-3); font-size: 9px; }
.formular, .detail { padding: 20px 22px 35px; }.formular { display: flex; flex-direction: column; gap: 15px; }.formular label, .nachfrage label { display: flex; flex-direction: column; gap: 6px; color: var(--text-2); font-size: 11px; font-weight: 600; letter-spacing: .03em; }.formular input, .formular textarea, .formular select, .nachfrage textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--linie); border-radius: 5px; background: var(--flaeche); color: var(--text); padding: 9px 10px; outline: none; font-size: 13px; font-weight: 400; letter-spacing: 0; }.formular input:focus, .formular textarea:focus, .formular select:focus, .nachfrage textarea:focus { border-color: var(--akzent); }.formular textarea, .nachfrage textarea { resize: vertical; line-height: 1.5; }.formular fieldset { margin: 0; padding: 11px 12px; border: 1px solid var(--linie); border-radius: 6px; }.formular legend { padding: 0 5px; color: var(--text-2); font-size: 11px; font-weight: 600; }.formular .radio { display: grid; grid-template-columns: auto 1fr; align-items: start; gap: 9px; padding: 6px 2px; cursor: pointer; }.radio input { width: auto; margin-top: 3px; accent-color: var(--akzent); }.radio span { display: flex; flex-direction: column; gap: 1px; }.radio strong { color: var(--text); font-size: 12px; }.radio small { color: var(--text-3); font-size: 10px; }.formular-zeile { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.aktionen { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }.edit-form { padding: 0 0 24px; border-bottom: 1px solid var(--linie); }
.formular .agent-auswahl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }.formular .agent-radio { position: relative; min-width: 0; padding: 9px; border: 1px solid var(--linie); border-radius: 5px; background: var(--flaeche); cursor: pointer; }.agent-radio.aktiv { background: rgba(242,184,75,.06); }.agent-radio input { position: absolute; opacity: 0; pointer-events: none; }.agent-radio span { display: flex; flex-direction: column; gap: 3px; }.agent-radio strong { color: var(--text); font-family: var(--display); font-size: 15px; letter-spacing: .03em; }.agent-radio small { color: var(--text-3); font-size: 9px; line-height: 1.35; }.agent-radio:nth-of-type(1).aktiv { border-color: #E79A5A; }.agent-radio:nth-of-type(2).aktiv { border-color: #4CC3A5; }.agent-radio:nth-of-type(3).aktiv { border-color: #6FA8FF; }
.formular .modus-radio.aktiv { border-color: var(--akzent); }.modus-hinweis { color: var(--text-3); }
.detail-chips { margin-bottom: 17px; }.detail-block { padding: 15px 0; border-top: 1px solid var(--linie); }.detail-block h3, .block-kopf h3 { margin: 0 0 9px; font-family: var(--display); font-size: 16px; letter-spacing: .06em; text-transform: uppercase; }.prosa { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text-2); font-size: 13px; line-height: 1.62; }.metadaten { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; margin: 0 0 12px; }.metadaten div { min-width: 0; padding: 8px 0; border-top: 1px solid var(--linie); }.metadaten dt { color: var(--text-3); font-size: 9px; text-transform: uppercase; letter-spacing: .08em; }.metadaten dd { margin: 3px 0 0; color: var(--text-2); font-size: 11px; overflow-wrap: anywhere; }.diff-link { display: inline-flex; align-items: center; gap: 5px; margin-top: 12px; color: var(--akzent); font-size: 11px; text-decoration: none; }.block-kopf { display: flex; align-items: center; justify-content: space-between; }.live-klein { display: flex; align-items: center; gap: 6px; color: var(--ok); font-family: var(--mono); font-size: 9px; }.protokoll { max-height: 310px; overflow-y: auto; padding: 9px 10px; border: 1px solid var(--linie); border-radius: 5px; background: #090E1C; scroll-behavior: smooth; }.protokoll p { display: grid; grid-template-columns: 64px 1fr; gap: 7px; margin: 0; padding: 3px 0; font-size: 9px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }.protokoll time { color: #526080; }.log-text span { color: var(--text); }.log-tool span, .log-system span { color: var(--text-3); }.log-result span { color: var(--akzent); }.log-fehler span { color: var(--krit); }.nachfrage { display: flex; align-items: flex-end; gap: 8px; padding: 15px 0; border-top: 1px solid var(--linie); }.nachfrage label { flex: 1; }.nachfrage .knopf { margin-bottom: 1px; }.detail-aktionen { padding-top: 16px; border-top: 1px solid var(--linie); }
.freigabe-block { padding: 16px; border: 1px solid rgba(242,184,75,.42); border-radius: 7px; background: rgba(242,184,75,.045); }.freigabe-block .plan { margin: 0 0 14px; padding: 11px; border: 1px solid var(--linie); border-radius: 5px; background: #090E1C; color: var(--text); font-size: 10px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }.freigabe-block label { display: flex; flex-direction: column; gap: 6px; color: var(--text-2); font-size: 11px; }.freigabe-block textarea { box-sizing: border-box; width: 100%; padding: 9px 10px; resize: vertical; border: 1px solid var(--linie); border-radius: 5px; outline: none; background: var(--flaeche); color: var(--text); }.freigabe-block textarea:focus { border-color: var(--akzent); }
@keyframes puls { 50% { opacity: .35; transform: scale(.82); } }
@media (max-width: 1100px) {
  .kopf { grid-template-columns: 1fr; }.kopf-mitte { text-align: left; }.kopf-rechts { justify-content: flex-start; flex-wrap: wrap; }.kapazitaet { flex-wrap: wrap; }.board { grid-template-columns: 1fr; overflow: visible; }.spalte { min-height: 120px; }.karten { display: grid; grid-template-columns: repeat(auto-fill, minmax(245px, 1fr)); }.leere-spalte { padding: 14px; }
}
@media (max-width: 620px) { .kopf { padding: 13px 15px; }.kapazitaet { padding: 6px 15px; }.ki-nutzung-bereich { padding: 9px 10px; }.ki-bereich-kopf > div { align-items: flex-start; flex-direction: column; gap: 1px; }.board { padding: 12px 10px 28px; }.karten { grid-template-columns: 1fr; }.formular, .detail { padding-left: 16px; padding-right: 16px; }.metadaten, .formular-zeile, .formular .agent-auswahl { grid-template-columns: 1fr; }.nachfrage { align-items: stretch; flex-direction: column; } }
@media (prefers-reduced-motion: reduce) { .kanban-seite *, .kanban-seite *::before, .kanban-seite *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; transition-duration: .001ms !important; } }
</style>
