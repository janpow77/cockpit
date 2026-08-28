"""Verlauf der Wand: Kennzahlen je Lauf als Zeitreihe in SQLite.

Der Hintergrundlauf (wall_loop) schreibt nach jedem Stand eine Handvoll Werte
(Host-Last, Speicher, Platte, GPU, Hero-Kennzahlen, Alarmzahlen, Antwortzeiten der
Dienste, Kira-Bestand). Die Wand zeigt daraus Verlaufslinien; Aufbewahrung 30 Tage.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import WallSampleRow

log = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def slug(text: str) -> str:
    """Kennzahl-Label → Schluesselteil (rein, testbar): 'Meldungen 24 h' → 'meldungen_24_h'."""
    t = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def werte_aus_stand(stand: dict) -> dict[str, float]:
    """Welche Zahlen eines Wand-Standes aufgehoben werden (rein, testbar)."""
    out: dict[str, float] = {}
    for h in stand.get("hosts") or []:
        st = h.get("stats") or {}
        name = h.get("name")
        for feld in ("load1", "mem_pct", "disk_pct"):
            if st.get(feld) is not None:
                out[f"host.{name}.{feld}"] = float(st[feld])
        gpus = st.get("gpus") or []
        if gpus:
            out[f"host.{name}.gpu_pct"] = sum(float(g.get("util_pct") or 0) for g in gpus) / len(gpus)
        if st.get("containers") is not None:
            out[f"host.{name}.containers"] = float(st["containers"])
    for k in (stand.get("hero") or {}).get("kpis") or []:
        if isinstance(k.get("value"), (int, float)):
            out[f"hero.{slug(str(k.get('label')))}"] = float(k["value"])
    alerts = stand.get("alerts") or []
    out["alerts.krit"] = float(sum(1 for a in alerts if a.get("level") == "krit"))
    out["alerts.warn"] = float(sum(1 for a in alerts if a.get("level") == "warn"))
    for d in stand.get("dienste") or []:
        if d.get("ms") is not None:
            out[f"dienst.{d.get('host')}.ms"] = float(d["ms"])
        out[f"dienst.{d.get('host')}.ok"] = 1.0 if d.get("ok") else 0.0
    kira = stand.get("kira") or {}
    if isinstance(kira.get("total"), (int, float)):
        out["kira.total"] = float(kira["total"])
    return out


def record(session: Session, stand: dict, ts: datetime | None = None) -> int:
    ts_iso = _iso(ts or datetime.now(UTC))
    werte = werte_aus_stand(stand)
    for key, value in werte.items():
        session.add(WallSampleRow(ts=ts_iso, key=key, value=value))
    session.commit()
    return len(werte)


def series(session: Session, keys: list[str], hours: int = 24, max_points: int = 400) -> dict[str, list[list]]:
    """{key: [[ts, value], …]} fuer die letzten `hours` Stunden, auf max_points ausgeduennt."""
    seit = _iso(datetime.now(UTC) - timedelta(hours=hours))
    out: dict[str, list[list]] = {k: [] for k in keys}
    if not keys:
        return out
    rows = session.execute(
        select(WallSampleRow.key, WallSampleRow.ts, WallSampleRow.value)
        .where(WallSampleRow.key.in_(keys), WallSampleRow.ts >= seit)
        .order_by(WallSampleRow.ts.asc())
    ).all()
    for key, ts, value in rows:
        out[key].append([ts, value])
    for key, punkte in out.items():
        if len(punkte) > max_points:
            schritt = len(punkte) / max_points
            out[key] = [punkte[int(i * schritt)] for i in range(max_points)]
    return out


def keys(session: Session, prefix: str | None = None) -> list[str]:
    q = select(WallSampleRow.key).distinct()
    if prefix:
        q = q.where(WallSampleRow.key.like(prefix + "%"))
    return [r[0] for r in session.execute(q).all()]


def purge(session: Session, days: int = 30) -> int:
    cutoff = _iso(datetime.now(UTC) - timedelta(days=days))
    res = session.execute(delete(WallSampleRow).where(WallSampleRow.ts < cutoff))
    session.commit()
    return int(res.rowcount or 0)
