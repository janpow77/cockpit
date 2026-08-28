-- Verlauf der Wand: ein Wert je Kennzahl und Lauf (services/verlauf.py)
CREATE TABLE IF NOT EXISTS cockpit_wall_samples (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    key   TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_wall_samples_key_ts ON cockpit_wall_samples (key, ts);
