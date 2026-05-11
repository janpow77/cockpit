-- Initiales Cockpit-Schema. Idempotent, SQLite.

-- Hosts: physische/virtuelle Maschinen die im Tailscale-Netz sind.
CREATE TABLE IF NOT EXISTS cockpit_hosts (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    tailscale_ip    TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    ssh_user        TEXT,
    ssh_key_path    TEXT,
    is_self         INTEGER NOT NULL DEFAULT 0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_check_at   TEXT,
    last_status     TEXT NOT NULL DEFAULT 'unknown',  -- online | offline | unreachable | unknown
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cockpit_hosts_name ON cockpit_hosts(name);

-- Apps: Docker-Stacks oder Einzel-Container die ueberwacht werden.
CREATE TABLE IF NOT EXISTS cockpit_apps (
    id                  TEXT PRIMARY KEY,
    host_id             TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    -- container_filter ist eine docker-ps-Filter-Expression (z.B. "name=auditworkshop-")
    container_filter    TEXT NOT NULL DEFAULT '',
    compose_path        TEXT,             -- z.B. /opt/auditworkshop/compose.yaml
    healthcheck_url     TEXT,             -- optional, wird per HTTP gepingt
    tags                TEXT NOT NULL DEFAULT '[]',
    enabled             INTEGER NOT NULL DEFAULT 1,
    last_check_at       TEXT,
    last_status         TEXT NOT NULL DEFAULT 'unknown',  -- healthy | degraded | down | unknown
    last_summary        TEXT,             -- JSON-Snapshot vom letzten Check
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(host_id, name),
    FOREIGN KEY (host_id) REFERENCES cockpit_hosts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cockpit_apps_host ON cockpit_apps(host_id);

-- GitHub-Repos: Bookmark-Liste, alle Daten kommen von api.github.com
CREATE TABLE IF NOT EXISTS cockpit_repos (
    id              TEXT PRIMARY KEY,
    owner           TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    default_branch  TEXT NOT NULL DEFAULT 'main',
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_sync_at    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(owner, name)
);

-- Backups: registrierte Backup-Jobs (Postgres-dump, Files-rsync, Docker-volume).
CREATE TABLE IF NOT EXISTS cockpit_backups (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    host_id             TEXT NOT NULL,
    backup_type         TEXT NOT NULL DEFAULT 'shell',  -- postgres | rsync | docker_volume | shell
    -- command: Shell-Befehl oder Template (z.B. "pg_dump $DB | gzip > $TARGET")
    command             TEXT NOT NULL,
    target_path         TEXT NOT NULL,
    schedule_cron       TEXT,             -- nur informativ — Cron laeuft auf dem Host
    enabled             INTEGER NOT NULL DEFAULT 1,
    last_run_at         TEXT,
    last_run_status     TEXT NOT NULL DEFAULT 'never',  -- ok | failed | running | never
    last_size_bytes     INTEGER,
    last_run_log        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (host_id) REFERENCES cockpit_hosts(id) ON DELETE CASCADE
);

-- Secrets / Vault: Werte sind verschluesselt at-rest (Fernet).
CREATE TABLE IF NOT EXISTS cockpit_secrets (
    id              TEXT PRIMARY KEY,
    key             TEXT NOT NULL UNIQUE,
    -- value_encrypted ist Fernet-Token (urlsafe_base64).
    value_encrypted TEXT NOT NULL,
    app_tag         TEXT,
    host_tag        TEXT,
    comment         TEXT NOT NULL DEFAULT '',
    last_used_at    TEXT,
    last_used_purpose TEXT,
    reveal_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cockpit_secrets_key ON cockpit_secrets(key);
CREATE INDEX IF NOT EXISTS idx_cockpit_secrets_app ON cockpit_secrets(app_tag);

-- Audit: jede mutierende Aktion wird hier protokolliert.
CREATE TABLE IF NOT EXISTS cockpit_audit (
    id              TEXT PRIMARY KEY,
    ts              TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'admin',
    action          TEXT NOT NULL,
    target          TEXT,
    before          TEXT,
    after           TEXT,
    ip              TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_cockpit_audit_ts ON cockpit_audit(ts DESC);
CREATE INDEX IF NOT EXISTS idx_cockpit_audit_action ON cockpit_audit(action);

-- Settings: einfacher key/value-Store fuer globale Optionen.
CREATE TABLE IF NOT EXISTS cockpit_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

-- Sessions: Bearer-Token Login.
CREATE TABLE IF NOT EXISTS cockpit_sessions (
    token           TEXT PRIMARY KEY,
    actor           TEXT NOT NULL DEFAULT 'admin',
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    ip              TEXT
);
CREATE INDEX IF NOT EXISTS idx_cockpit_sessions_expires ON cockpit_sessions(expires_at);
