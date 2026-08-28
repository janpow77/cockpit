<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ChevronDown, Lightbulb, X } from 'lucide-vue-next'
import { aendern, anlegen, aufraeumen, fortsetzen, listeAuftraege, loeschen, logLesen, nachfragen, prErstellen, projekte, pruefen, runnerSchalten, starten, stoppen, umsetzen, vorlagen as vorlagenAbrufen, vorschlaegeEinholen } from '../api/auftraege'
import { extractError } from '../api/client'
import type { Auftrag, AuftragAgent, AuftragModus, AuftragProfil, AuftragStatus, AuftraegeAntwort, LogZeile, Projekt, Vorlage, Zeitfenster } from '../api/types'
import { usePollStore } from '../stores/poll'
import { useToastStore } from '../stores/toast'
import KiNutzungPanel from '../components/kanban/KiNutzungPanel.vue'
import AuftragDetail from '../components/kanban/AuftragDetail.vue'
import AuftragFormular from '../components/kanban/AuftragFormular.vue'
import AuftragSpalte from '../components/kanban/AuftragSpalte.vue'
import VorschlaegePanel from '../components/kanban/VorschlaegePanel.vue'
import { SPALTEN, projektKey, spalteVon, type SpaltenStatus } from '../components/kanban/labels'

const REFRESH_MS = 10_000

const antwort = ref<AuftraegeAntwort | null>(null)
const projektListe = ref<Projekt[]>([])
const vorlagenListe = ref<Vorlage[]>([])
const vorlagenGeladen = ref(false)
const fehler = ref<string | null>(null)
const panel = ref<'neu' | 'vorschlaege' | 'detail' | null>(null)
const ausgewaehltId = ref<string | null>(null)
const busy = ref(false)
const runnerBusy = ref(false)
const mutationLaeuft = ref(0)
const tastaturStatus = ref('')
const branchLoeschenBestaetigen = ref(false)
const bearbeitenAktiv = ref(false)
const nachfrageText = ref('')
const umsetzungHinweis = ref('')
const logs = ref<LogZeile[]>([])
const jetzt = ref(Date.now())
const gezogenId = ref<string | null>(null)
const dropSpalte = ref<SpaltenStatus | null>(null)
const verschoben = ref(false)
const kiDetailsOffen = ref(false)
const poll = usePollStore()
const toast = useToastStore()
const reduziert = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const neuForm = reactive({ vorlageId: '', titel: '', text: '', projektKey: '', agent: 'auto' as AuftragAgent, modus: 'plan_freigabe' as AuftragModus, profil: 'bearbeiten_tests' as AuftragProfil, prioritaet: 3, zeitfenster: 'sofort' as Zeitfenster })
const vorschlaegeForm = reactive({ projektKey: '', agent: 'claude' as AuftragAgent })
const editForm = reactive({ titel: '', text: '', agent: 'claude' as AuftragAgent, modus: 'plan_freigabe' as AuftragModus, profil: 'lesen' as AuftragProfil, prioritaet: 3, zeitfenster: 'sofort' as Zeitfenster })

let uhrTimer: number | undefined
let logTimer: number | undefined
let logGeneration = 0
let ladeId = 0

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
  if (mutationLaeuft.value > 0) return
  const aktuelleLadeId = ++ladeId
  try {
    const neu = await listeAuftraege()
    if (aktuelleLadeId !== ladeId || mutationLaeuft.value > 0) return
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
    if (aktuelleLadeId !== ladeId || mutationLaeuft.value > 0) return
    fehler.value = extractError(err)
  }
}

async function mutieren<T>(aktion: () => Promise<T>): Promise<T> {
  mutationLaeuft.value += 1
  ladeId += 1
  try { return await aktion() }
  finally { mutationLaeuft.value = Math.max(0, mutationLaeuft.value - 1) }
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

function projektAuswahl(key = neuForm.projektKey): Projekt | undefined { return projektListe.value.find((p) => projektKey(p) === key) }
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
  panel.value = null; ausgewaehltId.value = null; bearbeitenAktiv.value = false; nachfrageText.value = ''; umsetzungHinweis.value = ''; branchLoeschenBestaetigen.value = false; logs.value = []; logPollingStoppen()
}
function neuOeffnen() { schliessen(); panel.value = 'neu'; void vorlagenLaden() }
function vorschlaegeOeffnen() { schliessen(); vorschlaegeForm.agent = 'claude'; panel.value = 'vorschlaege' }
function detailOeffnen(auftrag: Auftrag) {
  if (verschoben.value) return
  panel.value = 'detail'; ausgewaehltId.value = auftrag.id; bearbeitenAktiv.value = false; nachfrageText.value = ''; branchLoeschenBestaetigen.value = false
}

function editieren() {
  const a = ausgewaehlt.value
  if (!a) return
  Object.assign(editForm, { titel: a.titel, text: a.text, agent: a.agent_auto ? 'auto' : a.agent, modus: a.modus, profil: a.profil, prioritaet: a.prioritaet, zeitfenster: a.zeitfenster })
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
    lokalAktualisieren(await mutieren(() => aendern(a.id, { titel: editForm.titel.trim(), text: editForm.text.trim(), agent: editForm.agent, modus: editForm.modus, profil: editForm.modus === 'bericht' ? 'lesen' : editForm.profil, prioritaet: editForm.prioritaet, zeitfenster: editForm.zeitfenster })))
    bearbeitenAktiv.value = false; toast.success('Auftrag gespeichert')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function neuAnlegen(planen: boolean) {
  const projekt = projektAuswahl()
  if (!neuForm.titel.trim() || !neuForm.text.trim() || !projekt) { toast.warning('Titel, Projekt und Auftragstext sind Pflicht.'); return }
  busy.value = true
  try {
    const auftrag = await mutieren(async () => {
      let angelegt = await anlegen({ titel: neuForm.titel.trim(), text: neuForm.text.trim(), host: projekt.host, projekt: projekt.pfad, agent: neuForm.agent, modus: neuForm.modus, profil: neuForm.modus === 'bericht' ? 'lesen' : neuForm.profil, prioritaet: neuForm.prioritaet, zeitfenster: neuForm.zeitfenster })
      if (planen) angelegt = await aendern(angelegt.id, { status: 'geplant' })
      return angelegt
    })
    lokalAktualisieren(auftrag)
    toast.success(planen ? 'Auftrag ist geplant' : 'Auftrag liegt im Eingang')
    Object.assign(neuForm, { vorlageId: '', titel: '', text: '', agent: 'auto', modus: 'plan_freigabe', profil: 'bearbeiten_tests', prioritaet: 3, zeitfenster: 'sofort' })
    schliessen()
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function analyseStarten() {
  const projekt = projektAuswahl(vorschlaegeForm.projektKey)
  if (!projekt) { toast.warning('Bitte ein Projekt auswählen.'); return }
  busy.value = true
  try {
    await mutieren(() => vorschlaegeEinholen({ host: projekt.host, projekt: projekt.pfad, agent: vorschlaegeForm.agent }))
    await laden()
    schliessen()
    toast.success(`Analyse für ${projekt.name} eingeplant – Vorschläge erscheinen im Eingang.`)
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function startenAktion() { await auftragAktion((id) => starten(id), 'Auftrag gestartet') }
async function fortsetzenAktion() { await auftragAktion((id) => fortsetzen(id), 'Lauf wird fortgesetzt') }
async function stoppenAktion() { await auftragAktion((id) => stoppen(id), 'Auftrag gestoppt') }
async function pruefenAktion() { await auftragAktion((id) => pruefen(id), 'Prüfung abgeschlossen') }
async function prErstellenAktion() { await auftragAktion((id) => prErstellen(id), 'Pull Request erstellt') }
async function statusSetzen(status: AuftragStatus, meldung: string) { await auftragAktion((id) => aendern(id, { status }), meldung) }
async function umsetzenAktion() {
  const id = ausgewaehltId.value
  if (!id) return
  busy.value = true
  try {
    lokalAktualisieren(await mutieren(() => umsetzen(id, umsetzungHinweis.value)))
    umsetzungHinweis.value = ''
    toast.success('Plan freigegeben – Umsetzung gestartet')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}
async function auftragAktion(fn: (id: string) => Promise<Auftrag>, meldung: string) {
  const id = ausgewaehltId.value
  if (!id) return
  busy.value = true
  try { lokalAktualisieren(await mutieren(() => fn(id))); toast.success(meldung) } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function aufraeumenAktion(branchLoeschen: boolean) {
  const id = ausgewaehltId.value
  if (!id) return
  if (branchLoeschen && !branchLoeschenBestaetigen.value) { branchLoeschenBestaetigen.value = true; return }
  busy.value = true
  try {
    lokalAktualisieren(await mutieren(() => aufraeumen(id, branchLoeschen)))
    branchLoeschenBestaetigen.value = false
    toast.success(branchLoeschen ? 'Worktree und Branch aufgeräumt' : 'Worktree aufgeräumt')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function runnerUmschalten() {
  if (!antwort.value) return
  runnerBusy.value = true
  try {
    const kapazitaet = await mutieren(() => runnerSchalten(!antwort.value!.kapazitaet.angehalten))
    antwort.value = { ...antwort.value, kapazitaet }
    toast.success(kapazitaet.angehalten ? 'Runner angehalten' : 'Runner fortgesetzt')
  } catch (err) { toast.error(extractError(err)) } finally { runnerBusy.value = false }
}

async function nachfrageSenden() {
  const a = ausgewaehlt.value
  const text = nachfrageText.value.trim()
  if (!a || !text) { toast.warning('Bitte eine Antwort oder Nachfrage eingeben.'); return }
  busy.value = true
  try { lokalAktualisieren(await mutieren(() => nachfragen(a.id, text))); nachfrageText.value = ''; toast.success('Nachricht an die Sitzung gesendet') }
  catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

async function loeschenAktion() {
  const a = ausgewaehlt.value
  if (!a || !window.confirm(`Auftrag „${a.titel}“ wirklich löschen?`)) return
  busy.value = true
  try {
    await mutieren(() => loeschen(a.id))
    if (antwort.value) antwort.value.auftraege = antwort.value.auftraege.filter((eintrag) => eintrag.id !== a.id)
    schliessen(); toast.success('Auftrag gelöscht')
  } catch (err) { toast.error(extractError(err)) } finally { busy.value = false }
}

watch(() => `${ausgewaehltId.value ?? ''}:${ausgewaehlt.value?.status ?? ''}`, () => {
  logPollingStoppen()
  logs.value = []
  if (!ausgewaehltId.value) return
  void logsLaden(true)
  if (ausgewaehlt.value?.status === 'laeuft') logPollingStarten()
})

function logPollingStarten() {
  const generation = ++logGeneration
  const run = async () => {
    await logsLaden(false)
    if (generation !== logGeneration || ausgewaehlt.value?.status !== 'laeuft') return
    logTimer = window.setTimeout(() => { void run() }, 5000)
  }
  logTimer = window.setTimeout(() => { void run() }, 5000)
}
function logPollingStoppen() {
  logGeneration += 1
  if (logTimer) window.clearTimeout(logTimer)
  logTimer = undefined
}
async function logsLaden(fehlerZeigen: boolean) {
  const id = ausgewaehltId.value
  if (!id) return
  try {
    const ergebnis = await logLesen(id, 80)
    if (ausgewaehltId.value !== id) return
    logs.value = ergebnis.zeilen
  } catch (err) { if (fehlerZeigen) toast.error(extractError(err)) }
}

function dragStart(event: DragEvent, auftrag: Auftrag) {
  gezogenId.value = auftrag.id; verschoben.value = false
  event.dataTransfer?.setData('text/plain', auftrag.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function dragEnd() { gezogenId.value = null; dropSpalte.value = null; window.setTimeout(() => { verschoben.value = false }, 50) }
function darfVerschieben(quelle: Auftrag, ziel: SpaltenStatus): boolean {
  const start = spalteVon(quelle.status)
  return start === ziel || ((start === 'eingang' || start === 'geplant') && (ziel === 'eingang' || ziel === 'geplant'))
}
function darfAblegen(ziel: SpaltenStatus): boolean {
  const quelle = antwort.value?.auftraege.find((a) => a.id === gezogenId.value)
  return quelle ? darfVerschieben(quelle, ziel) : false
}
function dragOver(event: DragEvent, ziel: SpaltenStatus) {
  if (!darfAblegen(ziel)) return
  event.preventDefault(); dropSpalte.value = ziel
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}
async function karteVerschieben(id: string, ziel: SpaltenStatus, position: number): Promise<number | null> {
  if (!antwort.value) return null
  const quelle = antwort.value.auftraege.find((a) => a.id === id)
  if (!quelle || !darfVerschieben(quelle, ziel)) return null
  const bisher = spalteVon(quelle.status)
  const zielListe = spaltenInhalt.value[ziel].filter((a) => a.id !== id)
  const neuePosition = Math.max(0, Math.min(position, zielListe.length))
  zielListe.splice(neuePosition, 0, quelle)
  const patches = zielListe.map((a, index) => ({ a, patch: { reihenfolge: index + 1, ...(a.id === id && bisher !== ziel ? { status: ziel as AuftragStatus } : {}) } }))
  if (bisher !== ziel) quelle.status = ziel as AuftragStatus
  zielListe.forEach((a, index) => { a.reihenfolge = index + 1 })
  try {
    await mutieren(() => Promise.all(patches.map(({ a, patch }) => aendern(a.id, patch))))
    await laden()
    return neuePosition + 1
  } catch (err) {
    toast.error(extractError(err))
    await laden()
    return null
  }
}
async function karteTastatur(event: KeyboardEvent, auftrag: Auftrag) {
  if (event.target !== event.currentTarget || !event.ctrlKey || event.metaKey || event.altKey) return
  const spalte = spalteVon(auftrag.status)
  const liste = spaltenInhalt.value[spalte]
  const index = liste.findIndex((eintrag) => eintrag.id === auftrag.id)
  let ziel: SpaltenStatus | null = null
  let position = index
  if (event.key === 'ArrowLeft' && spalte === 'geplant') ziel = 'eingang'
  else if (event.key === 'ArrowRight' && spalte === 'eingang') ziel = 'geplant'
  else if (event.key === 'ArrowUp' && index > 0) { ziel = spalte; position = index - 1 }
  else if (event.key === 'ArrowDown' && index >= 0 && index < liste.length - 1) { ziel = spalte; position = index + 1 }
  if (!ziel) return
  if (ziel !== spalte) position = Math.min(index, spaltenInhalt.value[ziel].length)
  event.preventDefault()
  event.stopPropagation()
  const neuePosition = await karteVerschieben(auftrag.id, ziel, position)
  if (neuePosition != null) {
    const spaltenTitel = SPALTEN.find((eintrag) => eintrag.id === ziel)?.titel ?? ziel
    tastaturStatus.value = `Karte nach ${spaltenTitel}, Position ${neuePosition}`
  }
}
async function drop(event: DragEvent, ziel: SpaltenStatus, vorId?: string) {
  event.preventDefault()
  if (!darfAblegen(ziel) || !gezogenId.value || !antwort.value) return
  const id = gezogenId.value
  if (vorId === id) { dragEnd(); return }
  const zielListe = spaltenInhalt.value[ziel].filter((a) => a.id !== id)
  const position = vorId ? Math.max(0, zielListe.findIndex((a) => a.id === vorId)) : zielListe.length
  verschoben.value = true; gezogenId.value = null; dropSpalte.value = null
  await karteVerschieben(id, ziel, position)
}
</script>

<template>
  <div class="kanban-seite" :class="{ reduziert }">
    <header class="kopf">
      <div class="titel"><span class="marke">flowaudit</span><span class="untertitel">Aufträge</span></div>
      <div class="kopf-mitte mono"><span v-if="fehler" class="fehler">{{ fehler }}</span><span v-else class="dim">LLM-Aufträge steuern und verfolgen</span></div>
      <nav class="kopf-rechts" aria-label="Seitennavigation">
        <RouterLink to="/wall" class="knopf klein ghost">Zum Cockpit</RouterLink>
        <RouterLink to="/chat" class="knopf klein ghost">LLM-Konsole</RouterLink>
        <button class="knopf klein ghost" type="button" @click="vorschlaegeOeffnen"><Lightbulb :size="14" /> Vorschläge einholen</button>
        <button class="knopf klein" type="button" @click="neuOeffnen">Neuer Auftrag</button>
      </nav>
    </header>

    <section class="kapazitaet" :class="{ angehalten: antwort?.kapazitaet.angehalten }" aria-label="Kapazität">
      <strong class="mono">läuft {{ antwort?.kapazitaet.laufend ?? '–' }} / max {{ antwort?.kapazitaet.parallel_max ?? '–' }}</strong>
      <span v-if="antwort?.kapazitaet.angehalten" class="runner-warnung">· Runner angehalten – geplante Aufträge starten nicht</span><span v-else-if="antwort?.kapazitaet.pause_grund" class="pause">· {{ antwort.kapazitaet.pause_grund }}</span>
      <button class="runner-schalter" type="button" :disabled="runnerBusy || !antwort" @click="runnerUmschalten">{{ antwort?.kapazitaet.angehalten ? 'Runner fortsetzen' : 'Runner anhalten' }}</button>
    </section>

    <section class="ki-nutzung-bereich" aria-labelledby="ki-nutzung-titel">
      <header class="ki-bereich-kopf"><div><h2 id="ki-nutzung-titel">LLM-Nutzung</h2><span class="mono dim">Kontingente und Tokenverbrauch</span></div><button class="details-knopf" type="button" :aria-expanded="kiDetailsOffen" aria-controls="ki-nutzung-inhalt" @click="kiDetailsUmschalten">Details <ChevronDown :size="15" :class="{ gedreht: kiDetailsOffen }" /></button></header>
      <div id="ki-nutzung-inhalt"><KiNutzungPanel :offen="kiDetailsOffen" /></div>
    </section>

    <p class="sr-only" aria-live="polite" aria-atomic="true">{{ tastaturStatus }}</p>

    <main class="board" aria-label="Kanban-Board">
      <AuftragSpalte
        v-for="spalte in SPALTEN"
        :id="spalte.id"
        :key="spalte.id"
        :titel="spalte.titel"
        :auftraege="spaltenInhalt[spalte.id]"
        :drop-ziel="dropSpalte === spalte.id"
        :gezogen-id="gezogenId"
        :jetzt="jetzt"
        @dragover="dragOver($event, spalte.id)"
        @dragleave="dropSpalte = null"
        @drop="drop($event.event, spalte.id, $event.vorId)"
        @dragstart="dragStart($event.event, $event.auftrag)"
        @dragend="dragEnd"
        @oeffnen="detailOeffnen"
        @keydown-verschieben="karteTastatur($event.event, $event.auftrag)"
        @neu="neuOeffnen"
      />
    </main>

    <Transition name="blende"><button v-if="panel" class="panel-blende" aria-label="Panel schließen" @click="schliessen" /></Transition>
    <Transition name="panel">
      <aside v-if="panel" class="panel" :class="{ 'panel-klein': panel === 'vorschlaege' }" :aria-label="panel === 'neu' ? 'Neuer Auftrag' : panel === 'vorschlaege' ? 'Vorschläge einholen' : 'Auftragsdetails'">
        <header v-if="panel !== 'detail'" class="panel-kopf"><div><span class="mono dim">{{ panel === 'neu' ? 'NEU' : 'ANALYSE' }}</span><h2>{{ panel === 'neu' ? 'Neuer Auftrag' : 'Vorschläge einholen' }}</h2></div><button class="icon-knopf" type="button" aria-label="Schließen" @click="schliessen"><X :size="21" /></button></header>

        <AuftragFormular
          v-if="panel === 'neu'"
          variante="neu"
          :form="neuForm"
          :busy="busy"
          :vorlagen="vorlagenListe"
          :projekt-gruppen="projektGruppen"
          :projekt="neuProjekt"
          @vorlage="vorlageAnwenden"
          @submit="neuAnlegen"
        />
        <VorschlaegePanel
          v-else-if="panel === 'vorschlaege'"
          :form="vorschlaegeForm"
          :busy="busy"
          :projekt-gruppen="projektGruppen"
          :projekt="vorschlaegeProjekt"
          @submit="analyseStarten"
          @abbrechen="schliessen"
        />
        <AuftragDetail
          v-else-if="ausgewaehlt"
          :auftrag="ausgewaehlt"
          :bearbeiten-aktiv="bearbeitenAktiv"
          :edit-form="editForm"
          :busy="busy"
          :logs="logs"
          :jetzt="jetzt"
          :branch-loeschen-bestaetigen="branchLoeschenBestaetigen"
          v-model:nachfrage-text="nachfrageText"
          v-model:umsetzung-hinweis="umsetzungHinweis"
          @speichern="speichern"
          @bearbeiten-abbrechen="bearbeitenAktiv = false"
          @umsetzen="umsetzenAktion"
          @status-setzen="statusSetzen"
          @fortsetzen="fortsetzenAktion"
          @pruefen="pruefenAktion"
          @pr-erstellen="prErstellenAktion"
          @nachfrage="nachfrageSenden"
          @starten="startenAktion"
          @editieren="editieren"
          @loeschen="loeschenAktion"
          @stoppen="stoppenAktion"
          @aufraeumen="aufraeumenAktion"
          @schliessen="schliessen"
        />
      </aside>
    </Transition>
  </div>
</template>

<style scoped src="../components/kanban/kanbanViewStyles.css"></style>
