import { client, USE_MOCKS } from './client'
import type { Auftrag, AuftraegeAntwort, LogZeile, Projekt, Vorlage } from './types'

export interface AuftragAnlegen {
  titel: string
  text: string
  host: string
  projekt: string
  agent: Auftrag['agent']
  modus: Auftrag['modus']
  profil: Auftrag['profil']
  prioritaet: number
  zeitfenster: Auftrag['zeitfenster']
}

export type AuftragPatch = Partial<Pick<Auftrag, 'status' | 'prioritaet' | 'reihenfolge' | 'titel' | 'text' | 'agent' | 'modus' | 'profil' | 'zeitfenster'>>

const jetzt = Date.now()
const iso = (versatz = 0) => new Date(jetzt + versatz).toISOString()
let mockAuftraege: Auftrag[] = [
  { id: 'a-1', titel: 'Barrierefreiheit der Formulare prüfen', text: 'Prüfe die Formulare auf Tastaturbedienung und sinnvolle Labels. Dokumentiere die Befunde.', host: 'nuc', projekt: '/home/jan/projekte/regulierung', projekt_name: 'regulierung', agent: 'claude', modus: 'bericht', profil: 'lesen', prioritaet: 3, zeitfenster: 'sofort', status: 'eingang', reihenfolge: 1, branch: null, worktree: null, session_id: null, freigegeben: null, gestartet: null, beendet: null, dauer_s: null, ergebnis: null, fehler: null, kosten_usd: null, tokens_in: null, tokens_out: null, turns: null, letzte_zeile: null, diff_url: null, erstellt: iso(-7_200_000), aktualisiert: iso(-7_200_000) },
  { id: 'a-2', titel: 'Lint-Warnungen im Cockpit beheben', text: 'Behebe die aktuellen Lint-Warnungen, führe Type-Check und Tests aus und committe mit sprechender Meldung.', host: 'nuc', projekt: '/home/jan/projekte/cockpit', projekt_name: 'cockpit', agent: 'codex', modus: 'plan_freigabe', profil: 'bearbeiten_tests', prioritaet: 2, zeitfenster: 'nachts', status: 'geplant', reihenfolge: 1, branch: null, worktree: null, session_id: null, freigegeben: null, gestartet: null, beendet: null, dauer_s: null, ergebnis: null, fehler: null, kosten_usd: null, tokens_in: null, tokens_out: null, turns: null, letzte_zeile: null, diff_url: null, erstellt: iso(-5_400_000), aktualisiert: iso(-3_600_000) },
  { id: 'a-3', titel: 'API-Tests für Exporte ergänzen', text: 'Ergänze Tests für die Export-Endpunkte und behebe gefundene Randfälle.', host: 'ccx23', projekt: '/srv/regulierung', projekt_name: 'regulierung', agent: 'claude', modus: 'umsetzen', profil: 'bearbeiten_tests', prioritaet: 1, zeitfenster: 'sofort', status: 'laeuft', reihenfolge: 1, branch: 'agent/export-tests', worktree: '/tmp/auftrag-a-3', session_id: 'codex-a-3', freigegeben: null, gestartet: iso(-754_000), beendet: null, dauer_s: null, ergebnis: null, fehler: null, kosten_usd: null, tokens_in: 18420, tokens_out: 2310, turns: 7, letzte_zeile: 'Running pytest tests/api/test_exports.py …', diff_url: null, erstellt: iso(-10_800_000), aktualisiert: iso(-20_000) },
  { id: 'a-4', titel: 'Entscheidung zur Migration nötig', text: 'Bereite die Migration auf das neue Schema vor.', host: 'nuc', projekt: '/home/jan/projekte/flowinvoice', projekt_name: 'flowinvoice', agent: 'gemini', modus: 'plan_freigabe', profil: 'voll', prioritaet: 2, zeitfenster: 'sofort', status: 'rueckfrage', reihenfolge: 1, branch: 'agent/schema-migration', worktree: '/tmp/auftrag-a-4', session_id: 'codex-a-4', freigegeben: null, gestartet: iso(-3_000_000), beendet: null, dauer_s: 1142, ergebnis: 'Für die Spalte `beleg_typ` gibt es zwei mögliche Migrationswege. Soll sie zunächst nullable bleiben?', fehler: null, kosten_usd: 0.41, tokens_in: 41200, tokens_out: 4900, turns: 12, letzte_zeile: 'Warte auf Rückmeldung.', diff_url: null, erstellt: iso(-14_400_000), aktualisiert: iso(-1_800_000) },
  { id: 'a-5', titel: 'Dokumentation der Backup-Routine', text: 'Aktualisiere die Betriebsdokumentation.', host: 'ccx23', projekt: '/srv/cockpit', projekt_name: 'cockpit', agent: 'codex', modus: 'umsetzen', profil: 'bearbeiten', prioritaet: 4, zeitfenster: 'nach_reset', status: 'fertig', reihenfolge: 1, branch: 'agent/backup-docs', worktree: '/tmp/auftrag-a-5', session_id: 'codex-a-5', freigegeben: null, gestartet: iso(-86_400_000), beendet: iso(-86_081_000), dauer_s: 319, ergebnis: 'Die Backup-Routine ist jetzt mit Wiederherstellungsschritten und Prüfkommandos dokumentiert.', fehler: null, kosten_usd: 0.18, tokens_in: 12300, tokens_out: 1800, turns: 5, letzte_zeile: 'Commit erstellt.', diff_url: 'https://github.com/example/cockpit/compare/agent/backup-docs', erstellt: iso(-90_000_000), aktualisiert: iso(-86_081_000) },
  { id: 'a-6', titel: 'Veralteten Import entfernen', text: 'Entferne den veralteten Import und prüfe den Build.', host: 'nuc', projekt: '/home/jan/projekte/audit-designer', projekt_name: 'audit-designer', agent: 'claude', modus: 'umsetzen', profil: 'bearbeiten_tests', prioritaet: 3, zeitfenster: 'sofort', status: 'fehler', reihenfolge: 2, branch: 'agent/import-cleanup', worktree: '/tmp/auftrag-a-6', session_id: 'codex-a-6', freigegeben: null, gestartet: iso(-45_000_000), beendet: iso(-44_930_000), dauer_s: 70, ergebnis: null, fehler: 'Abhängigkeit konnte nicht installiert werden: Registry nicht erreichbar.', kosten_usd: 0.06, tokens_in: 3900, tokens_out: 420, turns: 2, letzte_zeile: 'npm ERR! network timeout', diff_url: null, erstellt: iso(-46_000_000), aktualisiert: iso(-44_930_000) },
  { id: 'a-7', titel: 'Suchindex robuster aktualisieren', text: 'Analysiere die Aktualisierung des Suchindex und plane eine robuste Umsetzung.', host: 'nuc', projekt: '/home/jan/projekte/regulierung', projekt_name: 'regulierung', agent: 'claude', modus: 'plan_freigabe', profil: 'bearbeiten_tests', prioritaet: 2, zeitfenster: 'sofort', status: 'freigabe', reihenfolge: 2, branch: null, worktree: null, session_id: 'claude-a-7', freigegeben: null, gestartet: iso(-2_400_000), beendet: null, dauer_s: 388, ergebnis: '1. Index-Aktualisierung in einen idempotenten Dienst kapseln.\n2. Transaktionale Outbox für Änderungen ergänzen.\n3. Wiederholungen mit exponentiellem Backoff einbauen.\n4. Unit- und Integrationstests für Abbruch und Wiederanlauf ergänzen.', fehler: null, kosten_usd: 0.22, tokens_in: 22100, tokens_out: 3100, turns: 8, letzte_zeile: 'Plan erstellt, warte auf Freigabe.', diff_url: null, erstellt: iso(-3_600_000), aktualisiert: iso(-2_000_000) },
]

const mockProjekte: Projekt[] = [
  { host: 'nuc', pfad: '/home/jan/projekte/cockpit', name: 'cockpit', quelle: 'flow-agent', ausfuehrbar: true, branch: 'main', dirty: true, technologien: ['Vue 3', 'TypeScript', 'FastAPI', 'PostgreSQL'], graphify_stand: '2026-08-27T08:30:00Z' },
  { host: 'nuc', pfad: '/home/jan/projekte/flowinvoice', name: 'flowinvoice', quelle: 'werkstatt', ausfuehrbar: true, branch: 'develop', dirty: false, technologien: ['Python', 'FastAPI', 'Vue 3'], graphify_stand: null },
  { host: 'nuc', pfad: '/home/jan/projekte/regulierung', name: 'regulierung', quelle: 'flow-agent', ausfuehrbar: true, branch: 'main', dirty: false, technologien: ['Python', 'FastAPI', 'React', 'PostgreSQL', 'Redis'], graphify_stand: '2026-08-26T17:10:00Z' },
  { host: 'ccx23', pfad: '/srv/cockpit', name: 'cockpit', quelle: 'work_dirs', ausfuehrbar: false, branch: 'main', dirty: false, technologien: ['Vue 3', 'TypeScript'], graphify_stand: null },
  { host: 'ccx23', pfad: '/srv/regulierung', name: 'regulierung', quelle: 'werkstatt', ausfuehrbar: true, branch: 'release', dirty: true, technologien: ['Python', 'Docker', 'PostgreSQL'], graphify_stand: '2026-08-25T12:00:00Z' },
]

const mockVorlagen: Vorlage[] = [
  { id: 'fehler-beheben', titel: 'Fehler in {projekt} beheben', modus: 'plan_freigabe', profil: 'bearbeiten_tests', prioritaet: 2, text: 'Analysiere den beschriebenen Fehler, behebe die Ursache und führe die passenden Tests sowie den Linter aus. Committe mit einer sprechenden Meldung.' },
  { id: 'code-review', titel: 'Code-Review für {projekt}', modus: 'bericht', profil: 'lesen', prioritaet: 3, text: 'Prüfe die aktuellen Änderungen auf Fehler, Sicherheitsrisiken und Wartbarkeit. Ändere keine Dateien und fasse die Befunde nach Priorität zusammen.' },
  { id: 'dokumentation', titel: 'Dokumentation von {projekt} aktualisieren', modus: 'umsetzen', profil: 'bearbeiten', prioritaet: 4, text: 'Prüfe die bestehende Dokumentation auf veraltete Angaben und ergänze die fehlenden Betriebs- und Entwicklungshinweise.' },
]

function mockFinden(id: string): Auftrag {
  const auftrag = mockAuftraege.find((eintrag) => eintrag.id === id)
  if (!auftrag) throw new Error('Auftrag nicht gefunden')
  return auftrag
}

export async function listeAuftraege(): Promise<AuftraegeAntwort> {
  if (USE_MOCKS) return { auftraege: mockAuftraege.map((a) => ({ ...a })), kapazitaet: { parallel_max: 3, laufend: mockAuftraege.filter((a) => a.status === 'laeuft').length, pause_grund: null, fuenf_stunden_pct: 38, woche_pct: 62, codex_woche_pct: 17 } }
  const { data } = await client.get<AuftraegeAntwort>('/auftraege')
  return data
}

export async function anlegen(body: AuftragAnlegen): Promise<Auftrag> {
  if (USE_MOCKS) {
    const projekt = mockProjekte.find((p) => p.host === body.host && p.pfad === body.projekt)
    const neu: Auftrag = { id: `a-${Date.now()}`, ...body, projekt_name: projekt?.name ?? body.projekt.split('/').pop() ?? body.projekt, status: 'eingang', reihenfolge: mockAuftraege.length + 1, branch: null, worktree: null, session_id: null, freigegeben: null, gestartet: null, beendet: null, dauer_s: null, ergebnis: null, fehler: null, kosten_usd: null, tokens_in: null, tokens_out: null, turns: null, letzte_zeile: null, diff_url: null, erstellt: new Date().toISOString(), aktualisiert: new Date().toISOString() }
    mockAuftraege = [...mockAuftraege, neu]
    return { ...neu }
  }
  const { data } = await client.post<Auftrag>('/auftraege', body)
  return data
}

export async function vorschlaegeEinholen(body: Pick<AuftragAnlegen, 'host' | 'projekt' | 'agent'>): Promise<Auftrag> {
  if (USE_MOCKS) {
    const projekt = mockProjekte.find((eintrag) => eintrag.host === body.host && eintrag.pfad === body.projekt)
    const auftrag = await anlegen({ ...body, titel: `Vorschläge für ${projekt?.name ?? 'Projekt'} ermitteln`, text: 'Analysiere das Projekt und lege 5–10 priorisierte Vorschläge als Aufträge in den Eingang.', modus: 'bericht', profil: 'lesen', prioritaet: 3, zeitfenster: 'sofort' })
    return aendern(auftrag.id, { status: 'geplant' })
  }
  const { data } = await client.post<Auftrag>('/auftraege/vorschlaege', body)
  return data
}

export async function aendern(id: string, patch: AuftragPatch): Promise<Auftrag> {
  if (USE_MOCKS) { const auftrag = mockFinden(id); Object.assign(auftrag, patch, { aktualisiert: new Date().toISOString() }); return { ...auftrag } }
  const { data } = await client.patch<Auftrag>(`/auftraege/${id}`, patch)
  return data
}

export async function starten(id: string): Promise<Auftrag> {
  if (USE_MOCKS) { const auftrag = mockFinden(id); Object.assign(auftrag, { status: 'laeuft', gestartet: new Date().toISOString(), session_id: `codex-${id}` }); return { ...auftrag } }
  const { data } = await client.post<Auftrag>(`/auftraege/${id}/start`)
  return data
}

export async function umsetzen(id: string, hinweis?: string): Promise<Auftrag> {
  if (USE_MOCKS) {
    const auftrag = mockFinden(id)
    Object.assign(auftrag, { status: 'laeuft', freigegeben: new Date().toISOString(), letzte_zeile: hinweis?.trim() || 'Plan freigegeben, Umsetzung startet.', aktualisiert: new Date().toISOString() })
    return { ...auftrag }
  }
  const body = hinweis?.trim() ? { hinweis: hinweis.trim() } : {}
  const { data } = await client.post<Auftrag>(`/auftraege/${id}/umsetzen`, body)
  return data
}

export async function stoppen(id: string): Promise<Auftrag> {
  if (USE_MOCKS) { const auftrag = mockFinden(id); Object.assign(auftrag, { status: 'abgebrochen', beendet: new Date().toISOString() }); return { ...auftrag } }
  const { data } = await client.post<Auftrag>(`/auftraege/${id}/stop`)
  return data
}

export async function nachfragen(id: string, text: string): Promise<Auftrag> {
  if (USE_MOCKS) { const auftrag = mockFinden(id); Object.assign(auftrag, { status: 'laeuft', letzte_zeile: text, aktualisiert: new Date().toISOString() }); return { ...auftrag } }
  const { data } = await client.post<Auftrag>(`/auftraege/${id}/nachfrage`, { text })
  return data
}

export async function logLesen(id: string, zeilen = 80): Promise<{ zeilen: LogZeile[] }> {
  if (USE_MOCKS) return { zeilen: [{ ts: iso(-600_000), art: 'system', text: `Sitzung für ${id} gestartet` }, { ts: iso(-500_000), art: 'text', text: 'Ich untersuche zunächst die betroffenen Dateien.' }, { ts: iso(-350_000), art: 'tool', text: '$ rg "export" tests src' }, { ts: iso(-120_000), art: 'result', text: 'Drei betroffene Endpunkte gefunden.' }, { ts: iso(-20_000), art: 'tool', text: 'Running pytest tests/api/test_exports.py …' }] }
  const { data } = await client.get<{ zeilen: LogZeile[] }>(`/auftraege/${id}/log`, { params: { zeilen } })
  return data
}

export async function loeschen(id: string): Promise<void> {
  if (USE_MOCKS) { mockAuftraege = mockAuftraege.filter((a) => a.id !== id); return }
  await client.delete(`/auftraege/${id}`)
}

export async function projekte(): Promise<Projekt[]> {
  if (USE_MOCKS) return mockProjekte.map((p) => ({ ...p }))
  const { data } = await client.get<Projekt[]>('/auftraege/projekte')
  return data
}

export async function vorlagen(): Promise<Vorlage[]> {
  if (USE_MOCKS) return mockVorlagen.map((vorlage) => ({ ...vorlage }))
  const { data } = await client.get<Vorlage[]>('/auftraege/vorlagen')
  return data
}
