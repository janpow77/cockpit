import type { Auftrag, AuftragAgent, AuftragModus, AuftragProfil, AuftragStatus, Projekt, Zeitfenster } from '../../api/types'

export type SpaltenStatus = 'eingang' | 'geplant' | 'laeuft' | 'rueckfrage' | 'fertig'
export interface ProjektGruppe { host: string; liste: Projekt[] }
export interface AuftragFormModel {
  vorlageId?: string
  titel: string
  text: string
  projektKey?: string
  agent: AuftragAgent
  modus: AuftragModus
  profil: AuftragProfil
  prioritaet: number
  zeitfenster: Zeitfenster
}

export const SPALTEN: { id: SpaltenStatus; titel: string }[] = [
  { id: 'eingang', titel: 'Eingang' },
  { id: 'geplant', titel: 'Geplant' },
  { id: 'laeuft', titel: 'Läuft' },
  { id: 'rueckfrage', titel: 'Rückfrage / Freigabe' },
  { id: 'fertig', titel: 'Fertig' },
]
export const PROFIL_LABELS: Record<AuftragProfil, string> = { lesen: 'Lesen', bearbeiten: 'Bearbeiten', bearbeiten_tests: 'Bearbeiten + Tests', voll: 'Voll' }
export const AGENT_LABELS: Record<AuftragAgent, string> = { claude: 'Claude', codex: 'Codex', gemini: 'Gemini', auto: 'Automatisch' }
export const MODUS_LABELS: Record<AuftragModus, string> = { bericht: 'Bericht', plan_freigabe: 'Plan → Freigabe', umsetzen: 'Umsetzen' }
export const ZEIT_LABELS: Record<Zeitfenster, string> = { sofort: 'sofort', nachts: 'nachts', nach_reset: 'nach Reset' }
export const STATUS_LABELS: Record<AuftragStatus, string> = { eingang: 'Eingang', geplant: 'Geplant', laeuft: 'Läuft', rueckfrage: 'Rückfrage', freigabe: 'Plan zur Freigabe', unterbrochen: 'Unterbrochen', fertig: 'Fertig', fehler: 'Fehler', abgebrochen: 'Abgebrochen' }
export const PROFILE: { id: AuftragProfil; titel: string; text: string }[] = [
  { id: 'lesen', titel: 'Lesen', text: 'nur analysieren' },
  { id: 'bearbeiten', titel: 'Bearbeiten', text: 'Dateien ändern' },
  { id: 'bearbeiten_tests', titel: 'Bearbeiten + Tests', text: 'zusätzlich Tests, Lint und Commit erlaubt' },
  { id: 'voll', titel: 'Voll', text: 'Classifier entscheidet' },
]
export const AGENTEN: { id: AuftragAgent; titel: string; text: string }[] = [
  { id: 'claude', titel: 'Claude Code', text: 'Max-Kontingent, 5-Stunden-Fenster' },
  { id: 'codex', titel: 'Codex', text: 'ChatGPT-Kontingent, Wochenfenster' },
  { id: 'gemini', titel: 'Gemini', text: 'ein Lauf gleichzeitig' },
  { id: 'auto', titel: 'Automatisch', text: 'Runner wählt nach Aufgabentyp und Kontingent: Berichte → Codex, Umsetzung → Claude, Oberfläche/Sprache → agy' },
]
export const VORSCHLAG_AGENTEN = AGENTEN.filter((agent) => agent.id !== 'auto')
export const MODI: { id: AuftragModus; titel: string; text: string }[] = [
  { id: 'bericht', titel: 'Nur berichten', text: 'Analysiert und schlägt einen Plan vor, ändert nichts.' },
  { id: 'plan_freigabe', titel: 'Plan zeigen, dann freigeben', text: 'Erstellt zuerst den Plan; die Umsetzung startet erst nach deiner Freigabe in derselben Sitzung.' },
  { id: 'umsetzen', titel: 'Direkt umsetzen', text: 'Ändert Dateien sofort im eigenen Branch.' },
]

export function spalteVon(status: AuftragStatus): SpaltenStatus {
  if (status === 'freigabe' || status === 'unterbrochen') return 'rueckfrage'
  return status === 'fehler' || status === 'abgebrochen' ? 'fertig' : status
}
export function agentChipLabel(auftrag: Auftrag): string {
  if (!auftrag.agent_auto) return AGENT_LABELS[auftrag.agent]
  return auftrag.agent === 'auto' ? 'automatisch' : `automatisch → ${AGENT_LABELS[auftrag.agent]}`
}
export function dauer(auftrag: Auftrag, jetzt: number): number | null {
  if (auftrag.status === 'laeuft' && auftrag.gestartet) return Math.max(0, Math.floor((jetzt - new Date(auftrag.gestartet).getTime()) / 1000))
  return auftrag.dauer_s
}
export function dauerText(sekunden: number | null): string {
  if (sekunden == null) return '–'
  const stunden = Math.floor(sekunden / 3600)
  const minuten = Math.floor((sekunden % 3600) / 60)
  const rest = Math.floor(sekunden % 60)
  return stunden ? `${stunden}:${String(minuten).padStart(2, '0')}:${String(rest).padStart(2, '0')}` : `${String(minuten).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}
export function tokens(anzahl: number | null): string {
  if (anzahl == null) return '–'
  if (anzahl >= 1_000_000) return `${(anzahl / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio.`
  if (anzahl >= 1000) return `${(anzahl / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} k`
  return String(anzahl)
}
export function kosten(wert: number | null): string { return wert == null ? '–' : `${wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $` }
export function datum(iso: string | null): string { return iso ? new Date(iso).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }) : '–' }
export function zeitAusLog(iso: string | null): string { return iso ? new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }
export function projektKey(projekt: Projekt): string { return `${projekt.host}\u0000${projekt.pfad}` }
export function projektOption(projekt: Projekt): string { return `${projekt.name}${projekt.branch ? ` — ${projekt.branch}` : ''}${projekt.dirty ? ' · uncommittet' : ''}${projekt.ausfuehrbar ? '' : ` (${projekt.grund || 'nicht ausführbar'})`}` }
export function quellenLabel(quelle: Projekt['quelle']): string { return quelle === 'werkstatt' ? 'Werkstatt' : quelle }
export function graphifyDatum(iso: string | null | undefined): string {
  if (!iso) return '–'
  const wert = new Date(iso)
  return Number.isNaN(wert.getTime()) ? '–' : wert.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
