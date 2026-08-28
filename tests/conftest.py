"""Testumgebung: eigene SQLite-Datei, damit App-Tests nie die Betriebsdatenbank beruehren."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("ADMIN_DB_PATH", str(Path(tempfile.mkdtemp(prefix="cockpit-test-")) / "cockpit.db"))
os.environ.setdefault("COCKPIT_DATA_DIR", str(Path(os.environ["ADMIN_DB_PATH"]).parent))
