"""Backup-Runner. Fuehrt das Command auf dem konfigurierten Host aus,
loggt das Ergebnis und aktualisiert die DB.
"""
from __future__ import annotations

import logging
import shlex

from sqlalchemy.orm import Session

from ..crud import backups as crud_backups
from ..models import BackupRow, HostRow
from .ssh_runner import run_on_host

log = logging.getLogger(__name__)


def run_backup(session: Session, backup: BackupRow, host: HostRow) -> dict:
    """Fuehrt ein Backup aus. Liefert {ok, duration_ms, bytes, log, error}."""
    cmd = backup.command
    crud_backups.record_run(session, backup.id, status="running")
    result = run_on_host(host, cmd, timeout=600)

    bytes_total: int | None = None
    if result.ok:
        # Versuche, Groesse der Target-Datei abzufragen
        try:
            tgt = backup.target_path
            stat_cmd = f"stat -c %s {shlex.quote(tgt)} 2>/dev/null || true"
            stat_res = run_on_host(host, stat_cmd, timeout=10)
            if stat_res.ok and stat_res.stdout.strip().isdigit():
                bytes_total = int(stat_res.stdout.strip())
        except Exception as exc:
            log.debug("Backup-Size-Probe fehlgeschlagen: %s", exc)

    log_text = (result.stdout + ("\n--- stderr ---\n" + result.stderr if result.stderr else ""))[-4000:]
    status = "ok" if result.ok else "failed"
    crud_backups.record_run(session, backup.id, status=status, log_excerpt=log_text, bytes_total=bytes_total)
    return {
        "ok": result.ok,
        "duration_ms": result.duration_ms,
        "bytes": bytes_total,
        "log": log_text,
        "error": None if result.ok else (result.stderr or f"rc={result.exit_code}")[:300],
    }
