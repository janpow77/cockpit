"""Vorformulierte Aufträge für das Kanban: Repo prüfen, GUI verbessern, Tests, Sicherheit, Doku …

Jede Vorlage bringt Titel, Kurzbeschreibung, Auftragstext, Profil und Priorität mit; ``{projekt}`` wird
durch den Projektnamen ersetzt. Eigene Vorlagen lassen sich über die Wand-Einstellung
``auftrag_vorlagen`` ergänzen oder ersetzen.
"""

from __future__ import annotations

VORLAGEN: list[dict] = [
    {
        "id": "repo-pruefen",
        "titel": "Repo prüfen: {projekt}",
        "kurz": "Prüft Architektur, Fehlerquellen, Sicherheit, Tests und Abhängigkeiten des Repositories.",
        "profil": "lesen",
        "modus": "bericht",
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
        "kurz": "Verbessert Lesbarkeit, Konsistenz und Barrierefreiheit der Benutzeroberfläche.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
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
        "kurz": "Ergänzt aussagekräftige Tests für Kernlogik, Grenzfälle und Fehlerpfade.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
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
        "kurz": "Untersucht das Projekt auf Sicherheitslücken und unsichere Voreinstellungen.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 2,
        "text": (
            "Führe ein Sicherheits-Audit durch (OWASP Top 10, Secrets, Auth/Session, Injection in Shell/SQL/HTML, SSRF, Pfad-Traversal, unsichere Defaults, Abhängigkeiten mit bekannten Lücken). "
            "Liefere je Befund: Schweregrad, Datei:Zeile, Angriffsszenario in einem Satz, konkreter Fix als Code-Vorschlag. Keine Änderungen an Dateien."
        ),
    },
    {
        "id": "doku",
        "titel": "Dokumentation aktualisieren: {projekt}",
        "kurz": "Gleicht Dokumentation und Docstrings mit dem aktuellen Stand des Codes ab.",
        "profil": "bearbeiten",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Bringe README, CLAUDE.md/ARCHITEKTUR.md und Docstrings auf den Stand des Codes: Befehle, Ports, Umgebungsvariablen, Architektur, bekannte Fallstricke. "
            "Kurz, sachlich, Deutsch mit echten Umlauten (Konventionen der jeweiligen Datei beachten). Entferne Veraltetes statt es zu kommentieren. Commit mit Zusammenfassung."
        ),
    },
    {
        "id": "abhaengigkeiten",
        "titel": "Abhängigkeiten aktualisieren: {projekt}",
        "kurz": "Aktualisiert Abhängigkeiten schrittweise und prüft ihre Verträglichkeit.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Aktualisiere die Abhängigkeiten vorsichtig: zuerst Patch- und Minor-Versionen, Major nur mit Begründung. "
            "Nach jedem Schritt Tests und Build laufen lassen; bei Bruch zurücknehmen und im Bericht nennen. Pinning-Konvention des Repos beibehalten. Commit je logischem Block."
        ),
    },
    {
        "id": "performance",
        "titel": "Performance prüfen: {projekt}",
        "kurz": "Findet und behebt die größten messbaren Leistungsbremsen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Finde die drei größten Leistungsbremsen (N+1-Abfragen, fehlende Indizes, synchrone Aufrufe im Async-Pfad, unnötige Re-Renders, große Bundles). "
            "Miss vorher/nachher, wo möglich. Behebe nur, was messbar hilft, und dokumentiere die Messung im Commit."
        ),
    },
    {
        "id": "fehler-beheben",
        "titel": "Fehler beheben: {projekt}",
        "kurz": "Reproduziert einen beschriebenen Fehler und behebt dessen Ursache mit einem Test.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 2,
        "text": (
            "Behebe folgenden Fehler: <hier beschreiben – Symptom, Schritte, erwartetes Verhalten>.\n"
            "Vorgehen: reproduzieren (Test schreiben), Ursache finden (nicht Symptom flicken), Fix, Test grün, Commit mit Begründung. Wenn die Ursache unklar bleibt, berichte die Hypothesen."
        ),
    },
    {
        "id": "vorschlaege",
        "titel": "Vorschläge einholen: {projekt}",
        "kurz": "Ermittelt und priorisiert konkrete nächste Verbesserungen für das Repository.",
        "profil": "lesen",
        "modus": "bericht",
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
        "kurz": "Bewertet offene Pull Requests hinsichtlich Zweck, Risiken und Prüfstatus.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 2,
        "text": (
            "Prüfe alle offenen Pull Requests (`gh pr list`, `gh pr diff <nr>`, `gh pr checks <nr>`). Je PR: Zweck in einem Satz, Risiken (Verhalten, Sicherheit, Migrationen, Tests), Zustand der Checks, Empfehlung (mergen / nacharbeiten / schließen) mit Begründung. "
            "Keine Änderungen, keine Kommentare auf GitHub posten – nur Bericht."
        ),
    },
    {
        "id": "issues-triage",
        "titel": "Issues sichten: {projekt}",
        "kurz": "Sichtet offene Issues und priorisiert sie nach Nutzen und Aufwand.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 3,
        "text": (
            "Sichte die offenen GitHub-Issues (`gh issue list --limit 100`, `gh issue view <nr>`). Je Issue: reproduzierbar? Ursache im Code (Datei:Zeile) vermutet? Aufwand (S/M/L), Nutzen, Vorschlag zur Umsetzung. "
            "Fasse zusammen, welche drei Issues zuerst dran sein sollten und welche geschlossen werden können. Nichts auf GitHub verändern."
        ),
    },
    {
        "id": "refactoring",
        "titel": "Aufräumen und entflechten: {projekt}",
        "kurz": "Vereinfacht und entflechtet den Code ohne sein Verhalten zu verändern.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Verhaltenserhaltendes Refactoring: doppelten Code zusammenführen, tote Pfade und unbenutzte Exporte entfernen, überlange Funktionen (> 80 Zeilen) sinnvoll teilen, Namen vereinheitlichen. "
            "Nutze graphify (god_nodes, Communities) oder eine eigene Abhängigkeitsanalyse, um die am stärksten gekoppelten Module zu finden. Vor jedem Schritt Tests grün, nach jedem Schritt Tests grün, ein Commit je Schritt. Kein neues Verhalten, keine neuen Abhängigkeiten."
        ),
    },
    {
        "id": "barrierefreiheit",
        "titel": "Barrierefreiheit prüfen: {projekt}",
        "kurz": "Prüft und verbessert die Oberfläche gemäß WCAG 2.2 AA.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Prüfe die Oberfläche gegen WCAG 2.2 AA (Tastaturbedienung, sichtbarer Fokus, Kontrast ≥ 4,5:1, Beschriftungen von Formularfeldern und Schaltflächen, ARIA nur wo nötig, Fehlermeldungen zugeordnet, Dialoge mit Fokusfalle und Escape, `prefers-reduced-motion`). "
            "Behebe die Befunde, ohne das Erscheinungsbild grundlegend zu ändern. Type-Check, Lint, Build grün. Bericht: was geprüft, was behoben, was offen."
        ),
    },
    {
        "id": "fehlerbehandlung",
        "titel": "Fehlerbehandlung und Protokollierung: {projekt}",
        "kurz": "Vereinheitlicht Fehlerbehandlung und Protokollierung einschließlich ihrer Fehlerpfade.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 3,
        "text": (
            "Prüfe Fehlerbehandlung und Logging: nackte `except:`, verschluckte Ausnahmen, fehlende Timeouts bei Netz-/Subprozess-Aufrufen, Fehler ohne Kontext (welcher Datensatz, welcher Host), Log-Ausgaben mit Secrets. "
            "Vereinheitliche auf die Konvention des Repos (eigene Fehlerklassen, strukturierte Meldungen, deutsche Nutzertexte mit echten Umlauten). Tests für die Fehlerpfade ergänzen. Commit je Modul."
        ),
    },
    {
        "id": "todo-aufraeumen",
        "titel": "TODO/FIXME abarbeiten: {projekt}",
        "kurz": "Bearbeitet oder präzisiert offene TODO-, FIXME-, XXX- und HACK-Markierungen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Sammle alle TODO/FIXME/XXX/HACK-Markierungen (`rg -n 'TODO|FIXME|XXX|HACK'`). Je Markierung: erledigen, wenn klar und klein (mit Test); sonst in einen Bericht mit Aufwandsschätzung und Vorschlag übernehmen und die Markierung mit Datum und Verweis präzisieren. "
            "Veraltete Markierungen entfernen. Tests grün, Commit."
        ),
    },
    {
        "id": "ci-pruefen",
        "titel": "CI und flackernde Tests: {projekt}",
        "kurz": "Analysiert fehlgeschlagene CI-Läufe und beseitigt Ursachen flackernder Tests.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 3,
        "text": (
            "Prüfe die CI (`gh run list --limit 30`, `gh run view <id> --log-failed`): welche Läufe scheitern, welche Tests flackern (mal rot, mal grün)? Finde die Ursache (Zeit, Reihenfolge, Netz, gemeinsamer Zustand) und behebe sie – keine `retry`- oder `skip`-Pflaster. "
            "Beschleunige die Pipeline, wo es einfach ist (Caching, Parallelisierung). Bericht mit Vorher/Nachher."
        ),
    },
    {
        "id": "release-vorbereiten",
        "titel": "Release vorbereiten: {projekt}",
        "kurz": "Bereitet Änderungsprotokoll, Version und Hinweise für ein neues Release vor.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 2,
        "text": (
            "Bereite ein Release vor: CHANGELOG aus `git log` seit dem letzten Tag (nach Nutzen gruppiert: Neu / Verbessert / Behoben / Sicherheit; Deutsch mit echten Umlauten), Version nach der Konvention des Repos anheben (package.json, pyproject, compose-Tag), Migrationen und Konfigurationsänderungen im Abschnitt »Beim Update beachten« auflisten. "
            "Tests, Lint, Build grün. Ein Commit `chore(release): vX.Y.Z`. KEIN Tag, KEIN Push – das mache ich."
        ),
    },
    {
        "id": "datenschutz",
        "titel": "Datenschutz prüfen (DSGVO): {projekt}",
        "kurz": "Dokumentiert und bewertet die Verarbeitung personenbezogener Daten.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 2,
        "text": (
            "Prüfe die Verarbeitung personenbezogener Daten: Welche Felder sind personenbezogen (Name, E-Mail, IP, Kennzeichen, Standort)? Wo werden sie gespeichert, protokolliert, an Dritte übertragen (APIs, LLM-Gateways, Telemetrie)? Gibt es Löschkonzept, Aufbewahrungsfristen, Zugriffsbeschränkung, Verschlüsselung, Audit-Log? "
            "Liefere ein Verarbeitungsverzeichnis in Tabellenform und Befunde mit Schweregrad und Fix-Vorschlag. Keine Änderungen."
        ),
    },
    {
        "id": "container-haerten",
        "titel": "Container und Deployment härten: {projekt}",
        "kurz": "Härtet Container- und Deployment-Konfigurationen ohne unnötige Verhaltensänderungen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 3,
        "text": (
            "Prüfe Dockerfile, compose und Deploy-Skripte: unprivilegierter Nutzer, feste Basis-Image-Versionen, kleine Images (Multi-Stage), keine Secrets im Image oder in ENV-Defaults, Healthchecks, Ressourcenlimits, read-only wo möglich, gepinnte Abhängigkeiten, `.dockerignore`. "
            "Behebe, was ohne Verhaltensänderung geht; Build muss weiterhin laufen. Bericht mit offenen Punkten, die eine Entscheidung brauchen."
        ),
    },
    {
        "id": "api-doku",
        "titel": "API dokumentieren: {projekt}",
        "kurz": "Aktualisiert OpenAPI-Beschreibungen und praktische Beispiele für die API.",
        "profil": "bearbeiten",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Bringe die API-Dokumentation auf Stand: OpenAPI-Beschreibungen (summary/description/Beispiele) je Endpunkt, Fehlercodes, Auth-Anforderungen; ein kurzes `docs/api.md` mit typischen Aufrufen (curl). "
            "Deutsch, sachlich, echte Umlaute. Nur Dokumentation und Schema-Beschreibungen ändern, kein Verhalten. Commit."
        ),
    },
    {
        "id": "migrationen-pruefen",
        "titel": "Datenbank-Migrationen prüfen: {projekt}",
        "kurz": "Prüft Datenbankschema und Migrationen auf Drift, Risiken und fehlende Regeln.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 3,
        "text": (
            "Prüfe Schema und Migrationen: Modelle gegen Migrationen (Drift?), fehlende Indizes für häufige Abfragen, fehlende Fremdschlüssel/Constraints, nicht rückwärtskompatible Migrationen, lange Sperren bei großen Tabellen, `downgrade` vorhanden und sinnvoll? "
            "Bericht mit Datei:Zeile und konkretem Migrations-Vorschlag. Keine Änderungen an alembic/versions."
        ),
    },
    {
        "id": "icons-vereinheitlichen",
        "titel": "Icons vereinheitlichen: {projekt}",
        "kurz": "Vereinheitlicht Auswahl, Darstellung und Barrierefreiheit der verwendeten Icons.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Vereinheitliche die Icons der Oberfläche: ein Icon-Satz (z. B. lucide) statt Mischung aus Emoji, Unicode-Symbolen und mehreren Bibliotheken; gleiche Größe je Kontext (Schaltfläche, Menü, Tabelle), gleiche Strichstärke, gleiche Farbe wie der Text, `aria-hidden` bei rein dekorativen Icons und beschriftete Schaltflächen ohne Text. "
            "Erstelle zuerst eine Tabelle aller verwendeten Icons (Datei, Icon, Bedeutung) und lege eine Zuordnung Bedeutung → Icon fest (gleiche Bedeutung = gleiches Icon überall). Dann umsetzen, Type-Check/Lint/Build grün, Commit."
        ),
    },
    {
        "id": "uebersetzen",
        "titel": "Übersetzen / Sprache vereinheitlichen: {projekt}",
        "kurz": "Vereinheitlicht nutzersichtbare Texte, Formate und Fachbegriffe in einer Sprache.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Bringe alle nutzersichtbaren Texte in eine Sprache: <Zielsprache, Vorgabe Deutsch> – Oberfläche, Fehlermeldungen, E-Mails/PDF-Texte, Platzhalter, Tooltips, Datums- und Zahlenformate (de-DE: DD.MM.JJJJ, 1.234,56). "
            "Englische Reste, Denglisch und ASCII-Umlaute (ae/oe/ue) beseitigen; Fachbegriffe einheitlich (Glossar anlegen: Begriff → Übersetzung). Gibt es ein i18n-System, dessen Struktur nutzen und fehlende Schlüssel ergänzen; sonst Texte direkt korrigieren. Bezeichner im Code bleiben Englisch. Commit je Bereich."
        ),
    },
    {
        "id": "design-vereinheitlichen",
        "titel": "Farben, Abstände, Typografie vereinheitlichen: {projekt}",
        "kurz": "Vereinheitlicht Farben, Abstände, Typografie und wiederkehrende Oberflächenkomponenten.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Vereinheitliche das Erscheinungsbild: eine Farbpalette (Primär, Akzent, Neutral, Status-Farben) als Design-Tokens/Tailwind-Konfiguration statt verstreuter Hex-Werte; einheitliche Abstände (Skala), Schriftgrößen und Rundungen; gleiche Komponenten für gleiche Zwecke (Schaltflächen, Karten, Chips, Tabellen). "
            "Zuerst Bestandsaufnahme (welche Werte kommen wie oft vor), dann Zuordnung auf Tokens, dann Ersetzung. Kein neues Design – nur Konsistenz. Build grün, Commit je Schritt."
        ),
    },
    {
        "id": "zustaende",
        "titel": "Leer-, Lade- und Fehlerzustände: {projekt}",
        "kurz": "Ergänzt verständliche Leer-, Lade- und Fehlerzustände in Seiten und Listen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 3,
        "text": (
            "Prüfe jede Seite und Liste auf die drei Zustände: leer (verständlicher Hinweis + nächste Aktion), laden (Skeleton/Spinner ohne Layout-Sprung) und Fehler (was ist passiert, was kann ich tun, erneut versuchen). "
            "Ergänze fehlende Zustände mit den vorhandenen Komponenten des Repos, deutsche Texte mit echten Umlauten. Build grün, Commit."
        ),
    },
    {
        "id": "tabellen-export",
        "titel": "Tabellen: Sortierung, Filter, Export: {projekt}",
        "kurz": "Erweitert Tabellen um einheitliche Sortierung, Filterung und Exportfunktionen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 3,
        "text": (
            "Bringe alle Tabellen auf einen Stand: sortierbare Spalten, Filter/Suche wo sinnvoll, Seitenumbruch bei > 50 Zeilen, Zahlen rechtsbündig mit de-DE-Format, Datum DD.MM.JJJJ, und je Tabelle ein Export als XLSX (und CSV) mit denselben Spalten und Filtern wie in der Ansicht. "
            "Vorhandene Export-Hilfen des Repos wiederverwenden, nicht neu erfinden. Kein toFixed(). Tests für den Export, Build grün, Commit."
        ),
    },
    {
        "id": "formulare",
        "titel": "Formulare und Validierung vereinheitlichen: {projekt}",
        "kurz": "Vereinheitlicht Formulare, Validierung und Rückmeldungen beim Speichern.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Vereinheitliche Formulare: Beschriftungen über dem Feld, Pflichtfelder markiert, Validierung beim Verlassen des Feldes und beim Absenden mit Fehlermeldung direkt am Feld (deutsch, konkret: was fehlt, welches Format), Speichern-Schaltfläche mit Ladezustand, keine Doppel-Absendung, Abbrechen ohne Datenverlust-Nachfrage. "
            "Gleiche Komponenten für gleiche Feldtypen (Datum, Betrag, Auswahl). Build grün, Commit."
        ),
    },
    {
        "id": "mobil",
        "titel": "Mobile Ansicht prüfen: {projekt}",
        "kurz": "Prüft und verbessert die Bedienbarkeit auf kleinen und mittleren Bildschirmen.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Prüfe alle Seiten bei 390 px und 768 px Breite: keine horizontale Scrollleiste, Tabellen mit eigenem Scrollbereich oder Kartenansicht, Navigation erreichbar, Schaltflächen ≥ 44 px, Formulare bedienbar, Diagramme skaliert. "
            "Behebe mit den vorhandenen Responsive-Mitteln (Tailwind-Breakpoints, Grid). Build grün, Commit je Seite oder Bereich."
        ),
    },
    {
        "id": "benennung",
        "titel": "Benennung und Begriffe vereinheitlichen: {projekt}",
        "kurz": "Vereinheitlicht Fachbegriffe und Aktionsbezeichnungen in Oberfläche, API und Dokumentation.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
        "prioritaet": 4,
        "text": (
            "Vereinheitliche Begriffe in Oberfläche, API und Doku: dieselbe Sache heißt überall gleich (z. B. »Vorgang« statt mal »Fall«, mal »Akte«), Menüpunkte und Seitentitel stimmen überein, Schaltflächen benennen die Aktion (»Speichern«, nicht »OK«). "
            "Erstelle ein Glossar (Begriff, Bedeutung, Fundstellen), stimme es mit der Fachsprache des Repos (CLAUDE.md, Doku) ab und setze es um. Bezeichner im Code nur umbenennen, wenn Tests es absichern. Commit je Begriff-Gruppe."
        ),
    },
    {
        "id": "datenqualitaet",
        "titel": "Datenqualität prüfen: {projekt}",
        "kurz": "Untersucht gespeicherte Daten auf Lücken, Widersprüche und fehlende Plausibilitätsregeln.",
        "profil": "lesen",
        "modus": "bericht",
        "prioritaet": 3,
        "text": (
            "Prüfe die Datenhaltung auf Qualitätsprobleme: Pflichtfelder ohne Constraint, Duplikate, verwaiste Datensätze, inkonsistente Einheiten/Formate (Netto/Brutto, EUR/kWh vs. ct/kWh, Datumsformate), fehlende Plausibilitätsprüfungen beim Import. "
            "Liefere je Befund: Tabelle/Feld, Beispiel, Auswirkung, Vorschlag (Constraint, Migration, Validierung, Bereinigungsskript). Keine Änderungen."
        ),
    },
    {
        "id": "umlaute-sprache",
        "titel": "Sprache und Umlaute prüfen: {projekt}",
        "kurz": "Korrigiert nutzersichtbare Sprache, Umlaute und Datumsformate.",
        "profil": "bearbeiten_tests",
        "modus": "plan_freigabe",
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
            titel = str(v.get("titel") or v["id"])
            out[str(v["id"])] = {
                "id": str(v["id"]), "titel": titel,
                "kurz": str(v.get("kurz") or f"Führt die benutzerdefinierte Vorlage „{titel}“ aus."),
                "profil": str(v.get("profil") or "bearbeiten"),
                "modus": str(v.get("modus") or ("bericht" if v.get("profil") == "lesen" else "plan_freigabe")),
                "prioritaet": int(v.get("prioritaet") or 3), "text": str(v["text"]),
            }
    return list(out.values())
