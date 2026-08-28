-- Kanban-Aufträge: Agentenläufe (Claude/Codex/Gemini) in Worktrees (services/auftraege.py)
CREATE TABLE IF NOT EXISTS cockpit_auftraege (
    id            TEXT PRIMARY KEY,
    titel         TEXT NOT NULL,
    text          TEXT NOT NULL,
    host          TEXT NOT NULL,
    projekt       TEXT NOT NULL,
    projekt_name  TEXT NOT NULL DEFAULT '',
    agent         TEXT NOT NULL DEFAULT 'claude',
    profil        TEXT NOT NULL DEFAULT 'bearbeiten',
    prioritaet    INTEGER NOT NULL DEFAULT 3,
    zeitfenster   TEXT NOT NULL DEFAULT 'sofort',
    status        TEXT NOT NULL DEFAULT 'eingang',
    reihenfolge   INTEGER NOT NULL DEFAULT 0,
    branch        TEXT, worktree TEXT, session_id TEXT,
    gestartet     TEXT, beendet TEXT, dauer_s INTEGER,
    ergebnis      TEXT, fehler TEXT, kosten_usd REAL, tokens_in INTEGER, tokens_out INTEGER, turns INTEGER,
    letzte_zeile  TEXT, diff_url TEXT,
    erstellt      TEXT NOT NULL,
    aktualisiert  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auftraege_status ON cockpit_auftraege (status, prioritaet, reihenfolge);
