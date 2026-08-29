-- Telegram-Dialog: gesendete Nachrichten je Auftrag (Reply → Auftrag)
CREATE TABLE IF NOT EXISTS cockpit_telegram (
    message_id INTEGER NOT NULL,
    chat_id    TEXT NOT NULL,
    auftrag_id TEXT NOT NULL,
    art        TEXT NOT NULL,
    erstellt   TEXT NOT NULL,
    PRIMARY KEY (message_id, chat_id)
);
CREATE INDEX IF NOT EXISTS ix_telegram_auftrag ON cockpit_telegram (auftrag_id);
