-- Phase 2: Traffic-Statistiken + Deployment-Historie. Idempotent, SQLite.

-- Traffic-Samples: 1-Minuten-Aggregate aus Caddy-Access-Log pro App.
-- Wird per Background-Task aufgefuellt (services/traffic_collector.py).
CREATE TABLE IF NOT EXISTS cockpit_traffic_samples (
    id              TEXT PRIMARY KEY,
    -- ISO8601, auf volle Minute gerundet (UTC).
    bucket_ts       TEXT NOT NULL,
    -- Bucket-Granularitaet: 1m / 5m / 1h. 1m wird gesammelt, andere per Rollup.
    bucket_size     TEXT NOT NULL DEFAULT '1m',
    -- Optional verknuepfte App; NULL = host-weit (Catch-All-Bucket).
    app_id          TEXT,
    host_id         TEXT NOT NULL,
    -- Hostname aus Caddy-Log (z.B. workshop.flowaudit.de). NULL = mehrere.
    server_name     TEXT,
    requests        INTEGER NOT NULL DEFAULT 0,
    status_2xx      INTEGER NOT NULL DEFAULT 0,
    status_3xx      INTEGER NOT NULL DEFAULT 0,
    status_4xx      INTEGER NOT NULL DEFAULT 0,
    status_5xx      INTEGER NOT NULL DEFAULT 0,
    bytes_out       INTEGER NOT NULL DEFAULT 0,
    -- Latenzen in Millisekunden (Caddy duration * 1000).
    latency_p50_ms  INTEGER,
    latency_p95_ms  INTEGER,
    latency_max_ms  INTEGER,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (host_id) REFERENCES cockpit_hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (app_id) REFERENCES cockpit_apps(id) ON DELETE SET NULL,
    UNIQUE(bucket_ts, bucket_size, host_id, server_name, app_id)
);
CREATE INDEX IF NOT EXISTS idx_traffic_app_ts ON cockpit_traffic_samples(app_id, bucket_ts DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_host_ts ON cockpit_traffic_samples(host_id, bucket_ts DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_size_ts ON cockpit_traffic_samples(bucket_size, bucket_ts DESC);

-- Traffic-Source-Config pro Host: wo liegt das Caddy-JSON-Log?
CREATE TABLE IF NOT EXISTS cockpit_traffic_sources (
    id              TEXT PRIMARY KEY,
    host_id         TEXT NOT NULL,
    log_path        TEXT NOT NULL,             -- z.B. /var/log/caddy/access.log
    log_format      TEXT NOT NULL DEFAULT 'caddy_json',
    -- Map server_name -> app_name. JSON-Array: [{"server_name":"workshop.flowaudit.de","app_name":"auditworkshop"}].
    -- App-Auflosung passiert beim Aggregator zum Zeitpunkt der Verarbeitung.
    server_app_map  TEXT NOT NULL DEFAULT '[]',
    -- Letzte verarbeitete Position (byte-offset) im Logfile, fuer inkrementelles Tailen.
    last_offset     INTEGER NOT NULL DEFAULT 0,
    -- Inode-Stempel um Logrotation zu erkennen (SSH-`stat -c %i`).
    last_inode      TEXT,
    last_collect_at TEXT,
    last_status     TEXT NOT NULL DEFAULT 'never',  -- ok | failed | running | never
    last_error      TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(host_id, log_path),
    FOREIGN KEY (host_id) REFERENCES cockpit_hosts(id) ON DELETE CASCADE
);

-- Deployments: jede Image-Aktivierung pro App. Geschrieben von
-- lifecycle/start.sh (Workshop, audit_designer) oder manuell via API.
CREATE TABLE IF NOT EXISTS cockpit_deployments (
    id              TEXT PRIMARY KEY,
    app_id          TEXT NOT NULL,
    ts              TEXT NOT NULL,
    -- Image-Referenz z.B. ghcr.io/janpow77/auditworkshop-backend:sha-abc1234
    image           TEXT NOT NULL,
    -- SHA256-Digest, falls bekannt (docker inspect --format '{{.Image}}').
    image_digest    TEXT,
    -- Git-SHA aus dem CI-Build oder lokal ermittelt.
    git_sha         TEXT,
    -- Source: lifecycle (Skript), gh-action (Workflow), manual (API), unknown.
    source          TEXT NOT NULL DEFAULT 'unknown',
    actor           TEXT NOT NULL DEFAULT 'system',
    -- ok | failed | started | rolled_back
    status          TEXT NOT NULL DEFAULT 'ok',
    notes           TEXT,
    -- Optionale Dauer in Sekunden (Build → Start abgeschlossen).
    duration_s      INTEGER,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (app_id) REFERENCES cockpit_apps(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_deployments_app_ts ON cockpit_deployments(app_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_deployments_ts ON cockpit_deployments(ts DESC);
