"""Vorformulierte Aufträge für das Kanban: Repo prüfen, GUI verbessern, Tests, Sicherheit, Doku …

Jede Vorlage bringt Titel, Auftragstext, Profil und Priorität mit; ``{projekt}`` wird
durch den Projektnamen ersetzt. Eigene Vorlagen lassen sich über die Wand-Einstellung
``auftrag_vorlagen`` ergänzen oder ersetzen.
"""

from __future__ import annotations

VORLAGEN: list[dict] = [
    {
        "id": "repo-pruefen",
        "titel": "Repo prüfen: {projekt}",
        "profil": "lesen",
        "prioritaet": 3,
        "text": (
            "Prüfe dieses Repository gründlich und erstelle einen Befundbericht (Deutsch, echte Umlaute, sachlich).\n"
            "1. Architektur und Struktur: Was ist unklar, doppelt oder inkonsistent?\n"
            "2. Fehlerquellen: Ausnahmen ohne Behandlung, fehlende Timeouts, Race Conditions, tote Pfade.\n"
            "3. Sicherheit: Secrets im Code, Injection, fehlende Auth, unsichere Defaults.\n"
            "4. Tests: Was ist ungetestet, welche Tests sind brüchig?\n"
            "5. Abhängigkeiten: veraltet oder riskant?\n"
            "Liefere eine priorisierte Liste (kritisch/wichtig/gering) mit Datei:Zeile, Problem und konkretem Vorschlag. "
            "Ändere KEINE Dateien – nur lesen und berichten."
        ),
    },
    {
        "id": "gui-verbessern",
        "titel": "Oberfläche verbessern: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 3,
        "text": (
            "Verbessere die Benutzeroberfläche dieses Projekts, ohne das Verhalten zu ändern. Reihenfolge:\n"
            "1. Sichte die Views/Seiten und notiere die fünf größten Schwächen (Lesbarkeit, Abstände, Konsistenz, Zustände wie leer/laden/fehler, Barrierefreiheit: Fokus, Kontrast, Tastatur).\n"
            "2. Behebe sie – konsistente Typografie und Abstände, klare Hierarchie, deutsche Texte mit echten Umlauten, Zahlen im Format de-DE, kein toFixed().\n"
            "3. Führe Type-Check, Lint und Build aus und behebe alles, was rot ist.\n"
            "4. Committe in kleinen, sprechenden Commits (Konvention des Repos beachten).\n"
            "Berichte am Ende, was geändert wurde und was du bewusst gelassen hast."
        ),
    },
    {
        "id": "tests-ergaenzen",
        "titel": "Tests ergänzen: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 3,
        "text": (
            "Erhöhe die Testabdeckung dort, wo es am meisten bringt: Kernlogik, Grenzfälle, Fehlerpfade. "
            "Erst die vorhandene Test-Suite laufen lassen und Fehler beheben, dann fehlende Tests ergänzen (gleicher Stil und dieselbe Struktur wie die bestehenden). "
            "Keine Tests, die nur Implementierungsdetails abschreiben. Am Ende: Suite grün, Commit mit Zusammenfassung, kurzer Bericht was abgedeckt ist und was offen bleibt."
        ),
    },
    {
        "id": "sicherheit",
        "titel": "Sicherheits-Audit: {projekt}",
        "profil": "lesen",
        "prioritaet": 2,
        "text": (
            "Führe ein Sicherheits-Audit durch (OWASP Top 10, Secrets, Auth/Session, Injection in Shell/SQL/HTML, SSRF, Pfad-Traversal, unsichere Defaults, Abhängigkeiten mit bekannten Lücken). "
            "Liefere je Befund: Schweregrad, Datei:Zeile, Angriffsszenario in einem Satz, konkreter Fix als Code-Vorschlag. Keine Änderungen an Dateien."
        ),
    },
    {
        "id": "doku",
        "titel": "Dokumentation aktualisieren: {projekt}",
        "profil": "bearbeiten",
        "prioritaet": 4,
        "text": (
            "Bringe README, CLAUDE.md/ARCHITEKTUR.md und Docstrings auf den Stand des Codes: Befehle, Ports, Umgebungsvariablen, Architektur, bekannte Fallstricke. "
            "Kurz, sachlich, Deutsch mit echten Umlauten (Konventionen der jeweiligen Datei beachten). Entferne Veraltetes statt es zu kommentieren. Commit mit Zusammenfassung."
        ),
    },
    {
        "id": "abhaengigkeiten",
        "titel": "Abhängigkeiten aktualisieren: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Aktualisiere die Abhängigkeiten vorsichtig: zuerst Patch- und Minor-Versionen, Major nur mit Begründung. "
            "Nach jedem Schritt Tests und Build laufen lassen; bei Bruch zurücknehmen und im Bericht nennen. Pinning-Konvention des Repos beibehalten. Commit je logischem Block."
        ),
    },
    {
        "id": "performance",
        "titel": "Performance prüfen: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Finde die drei größten Leistungsbremsen (N+1-Abfragen, fehlende Indizes, synchrone Aufrufe im Async-Pfad, unnötige Re-Renders, große Bundles). "
            "Miss vorher/nachher, wo möglich. Behebe nur, was messbar hilft, und dokumentiere die Messung im Commit."
        ),
    },
    {
        "id": "fehler-beheben",
        "titel": "Fehler beheben: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 2,
        "text": (
            "Behebe folgenden Fehler: <hier beschreiben – Symptom, Schritte, erwartetes Verhalten>.\n"
            "Vorgehen: reproduzieren (Test schreiben), Ursache finden (nicht Symptom flicken), Fix, Test grün, Commit mit Begründung. Wenn die Ursache unklar bleibt, berichte die Hypothesen."
        ),
    },
    {
        "id": "vorschlaege",
        "titel": "Vorschläge einholen: {projekt}",
        "profil": "lesen",
        "prioritaet": 3,
        "text": (
            "Analysiere dieses Repository und mache mir konkrete Vorschläge, was ich als Nächstes ändern sollte. Quellen:\n"
            "1. Git: `git log --since='21 days ago' --stat` (was ist zuletzt passiert, wo wird viel angefasst?), `git status`, offene TODO/FIXME/XXX im Code.\n"
            "2. GitHub (`gh`): offene Issues und Pull Requests (`gh issue list`, `gh pr list`), Dependabot-/Sicherheitshinweise (`gh api repos/{owner}/{repo}/dependabot/alerts` falls erlaubt), letzte Workflow-Läufe (`gh run list --limit 10`).\n"
            "3. Graphify (flow-agent analysiert alle Repos): lies `graphify-out/<neuestes Datum>/GRAPH_REPORT.md` und `manifest.json` im Projekt, bei Bedarf die MCP-Werkzeuge graphify (god_nodes, get_community, graph_stats): überladene Module, Kopplung – wo lohnt Entflechtung?\n"
            "4. Code: Tests (was ist ungetestet?), Abhängigkeiten (veraltet/riskant), Sicherheit (Secrets, Auth, Injection), Doku (stimmt README/CLAUDE.md noch?).\n"
            "Ändere KEINE Dateien. Liefere 5 bis 10 Vorschläge, nach Nutzen sortiert. Gib als ALLERLETZTES einen Block aus, exakt in diesem Format, ohne Text danach:\n"
            "```json\n[{\"titel\": \"kurz, max. 80 Zeichen\", \"text\": \"vollständiger Auftragstext für einen Agenten: was, wo (Datei:Zeile), warum, Abnahmekriterium\", \"profil\": \"lesen|bearbeiten|bearbeiten_tests\", \"prioritaet\": 1-5, \"begruendung\": \"ein Satz\"}]\n```"
        ),
    },
    {
        "id": "pr-review",
        "titel": "Offene Pull Requests prüfen: {projekt}",
        "profil": "lesen",
        "prioritaet": 2,
        "text": (
            "Prüfe alle offenen Pull Requests (`gh pr list`, `gh pr diff <nr>`, `gh pr checks <nr>`). Je PR: Zweck in einem Satz, Risiken (Verhalten, Sicherheit, Migrationen, Tests), Zustand der Checks, Empfehlung (mergen / nacharbeiten / schließen) mit Begründung. "
            "Keine Änderungen, keine Kommentare auf GitHub posten – nur Bericht."
        ),
    },
    {
        "id": "issues-triage",
        "titel": "Issues sichten: {projekt}",
        "profil": "lesen",
        "prioritaet": 3,
        "text": (
            "Sichte die offenen GitHub-Issues (`gh issue list --limit 100`, `gh issue view <nr>`). Je Issue: reproduzierbar? Ursache im Code (Datei:Zeile) vermutet? Aufwand (S/M/L), Nutzen, Vorschlag zur Umsetzung. "
            "Fasse zusammen, welche drei Issues zuerst dran sein sollten und welche geschlossen werden können. Nichts auf GitHub verändern."
        ),
    },
    {
        "id": "refactoring",
        "titel": "Aufräumen und entflechten: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Verhaltenserhaltendes Refactoring: doppelten Code zusammenführen, tote Pfade und unbenutzte Exporte entfernen, überlange Funktionen (> 80 Zeilen) sinnvoll teilen, Namen vereinheitlichen. "
            "Nutze graphify (god_nodes, Communities) oder eine eigene Abhängigkeitsanalyse, um die am stärksten gekoppelten Module zu finden. Vor jedem Schritt Tests grün, nach jedem Schritt Tests grün, ein Commit je Schritt. Kein neues Verhalten, keine neuen Abhängigkeiten."
        ),
    },
    {
        "id": "barrierefreiheit",
        "titel": "Barrierefreiheit prüfen: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Prüfe die Oberfläche gegen WCAG 2.2 AA (Tastaturbedienung, sichtbarer Fokus, Kontrast ≥ 4,5:1, Beschriftungen von Formularfeldern und Schaltflächen, ARIA nur wo nötig, Fehlermeldungen zugeordnet, Dialoge mit Fokusfalle und Escape, `prefers-reduced-motion`). "
            "Behebe die Befunde, ohne das Erscheinungsbild grundlegend zu ändern. Type-Check, Lint, Build grün. Bericht: was geprüft, was behoben, was offen."
        ),
    },
    {
        "id": "fehlerbehandlung",
        "titel": "Fehlerbehandlung und Protokollierung: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 3,
        "text": (
            "Prüfe Fehlerbehandlung und Logging: nackte `except:`, verschluckte Ausnahmen, fehlende Timeouts bei Netz-/Subprozess-Aufrufen, Fehler ohne Kontext (welcher Datensatz, welcher Host), Log-Ausgaben mit Secrets. "
            "Vereinheitliche auf die Konvention des Repos (eigene Fehlerklassen, strukturierte Meldungen, deutsche Nutzertexte mit echten Umlauten). Tests für die Fehlerpfade ergänzen. Commit je Modul."
        ),
    },
    {
        "id": "todo-aufraeumen",
        "titel": "TODO/FIXME abarbeiten: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Sammle alle TODO/FIXME/XXX/HACK-Markierungen (`rg -n 'TODO|FIXME|XXX|HACK'`). Je Markierung: erledigen, wenn klar und klein (mit Test); sonst in einen Bericht mit Aufwandsschätzung und Vorschlag übernehmen und die Markierung mit Datum und Verweis präzisieren. "
            "Veraltete Markierungen entfernen. Tests grün, Commit."
        ),
    },
    {
        "id": "ci-pruefen",
        "titel": "CI und flackernde Tests: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 3,
        "text": (
            "Prüfe die CI (`gh run list --limit 30`, `gh run view <id> --log-failed`): welche Läufe scheitern, welche Tests flackern (mal rot, mal grün)? Finde die Ursache (Zeit, Reihenfolge, Netz, gemeinsamer Zustand) und behebe sie – keine `retry`- oder `skip`-Pflaster. "
            "Beschleunige die Pipeline, wo es einfach ist (Caching, Parallelisierung). Bericht mit Vorher/Nachher."
        ),
    },
    {
        "id": "release-vorbereiten",
        "titel": "Release vorbereiten: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 2,
        "text": (
            "Bereite ein Release vor: CHANGELOG aus `git log` seit dem letzten Tag (nach Nutzen gruppiert: Neu / Verbessert / Behoben / Sicherheit; Deutsch mit echten Umlauten), Version nach der Konvention des Repos anheben (package.json, pyproject, compose-Tag), Migrationen und Konfigurationsänderungen im Abschnitt »Beim Update beachten« auflisten. "
            "Tests, Lint, Build grün. Ein Commit `chore(release): vX.Y.Z`. KEIN Tag, KEIN Push – das mache ich."
        ),
    },
    {
        "id": "datenschutz",
        "titel": "Datenschutz prüfen (DSGVO): {projekt}",
        "profil": "lesen",
        "prioritaet": 2,
        "text": (
            "Prüfe die Verarbeitung personenbezogener Daten: Welche Felder sind personenbezogen (Name, E-Mail, IP, Kennzeichen, Standort)? Wo werden sie gespeichert, protokolliert, an Dritte übertragen (APIs, LLM-Gateways, Telemetrie)? Gibt es Löschkonzept, Aufbewahrungsfristen, Zugriffsbeschränkung, Verschlüsselung, Audit-Log? "
            "Liefere ein Verarbeitungsverzeichnis in Tabellenform und Befunde mit Schweregrad und Fix-Vorschlag. Keine Änderungen."
        ),
    },
    {
        "id": "container-haerten",
        "titel": "Container und Deployment härten: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 3,
        "text": (
            "Prüfe Dockerfile, compose und Deploy-Skripte: unprivilegierter Nutzer, feste Basis-Image-Versionen, kleine Images (Multi-Stage), keine Secrets im Image oder in ENV-Defaults, Healthchecks, Ressourcenlimits, read-only wo möglich, gepinnte Abhängigkeiten, `.dockerignore`. "
            "Behebe, was ohne Verhaltensänderung geht; Build muss weiterhin laufen. Bericht mit offenen Punkten, die eine Entscheidung brauchen."
        ),
    },
    {
        "id": "api-doku",
        "titel": "API dokumentieren: {projekt}",
        "profil": "bearbeiten",
        "prioritaet": 4,
        "text": (
            "Bringe die API-Dokumentation auf Stand: OpenAPI-Beschreibungen (summary/description/Beispiele) je Endpunkt, Fehlercodes, Auth-Anforderungen; ein kurzes `docs/api.md` mit typischen Aufrufen (curl). "
            "Deutsch, sachlich, echte Umlaute. Nur Dokumentation und Schema-Beschreibungen ändern, kein Verhalten. Commit."
        ),
    },
    {
        "id": "migrationen-pruefen",
        "titel": "Datenbank-Migrationen prüfen: {projekt}",
        "profil": "lesen",
        "prioritaet": 3,
        "text": (
            "Prüfe Schema und Migrationen: Modelle gegen Migrationen (Drift?), fehlende Indizes für häufige Abfragen, fehlende Fremdschlüssel/Constraints, nicht rückwärtskompatible Migrationen, lange Sperren bei großen Tabellen, `downgrade` vorhanden und sinnvoll? "
            "Bericht mit Datei:Zeile und konkretem Migrations-Vorschlag. Keine Änderungen an alembic/versions."
        ),
    },
    {
        "id": "umlaute-sprache",
        "titel": "Sprache und Umlaute prüfen: {projekt}",
        "profil": "bearbeiten_tests",
        "prioritaet": 4,
        "text": (
            "Prüfe alle nutzersichtbaren Texte (UI, PDFs, Fehlermeldungen, DB-Werte): echte Umlaute (ä ö ü ß) statt ae/oe/ue, Behördensprache (Begünstigte, Behörde, Förderung, VerwK = Verwaltungskontrolle, Feststellungen), einheitliche Datumsformate DD.MM.JJJJ. "
            "Korrigiere und committe; Bezeichner im Code bleiben ASCII."
        ),
    },
]


def vorlagen(extra: list[dict] | None = None) -> list[dict]:
    """Vorgaben plus eigene Vorlagen aus der Konfiguration (gleiche id ersetzt die Vorgabe)."""
    out = {v["id"]: dict(v) for v in VORLAGEN}
    for v in extra or []:
        if isinstance(v, dict) and v.get("id") and v.get("text"):
            out[str(v["id"])] = {"id": str(v["id"]), "titel": str(v.get("titel") or v["id"]), "profil": str(v.get("profil") or "bearbeiten"), "prioritaet": int(v.get("prioritaet") or 3), "text": str(v["text"])}
    return list(out.values())
