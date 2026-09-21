"""Process-wide shared Kùzu Database handle for the web app.

Kùzu takes an exclusive file lock per `Database` handle, so the ask agent and
the `/api/v1/graph/*` routes must share ONE handle (each consumer opens its own
`Connection` — Connections are cheap; the Database is the lockholder).
"""

from __future__ import annotations

import threading
from typing import Any

from src.web.paths import data_dir

_lock = threading.Lock()
_db: Any | None = None
_db_path: str | None = None


def shared_database() -> Any:
    """Lazy singleton `kuzu.Database` for `<data_dir>/graph/kuzu.db`."""
    global _db, _db_path  # noqa: PLW0603 — module-level cache by design
    path = str(data_dir() / "graph" / "kuzu.db")
    if _db is None or _db_path != path:
        with _lock:
            if _db is None or _db_path != path:
                import os  # noqa: PLC0415

                import kuzu  # noqa: PLC0415

                bp = int(os.environ.get("SECBRAIN_KUZU_BUFFER_POOL_BYTES", "0") or "0")
                _db = (kuzu.Database(path, buffer_pool_size=bp) if bp > 0
                       else kuzu.Database(path))
                _db_path = path
    return _db
