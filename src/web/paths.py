"""Workspace path helpers — shared between FastAPI app + routers without
circular imports.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("SECBRAIN_DATA_DIR", "data"))


def sqlite_path() -> Path:
    return data_dir() / "sqlite" / "store.db"


__all__ = ["data_dir", "sqlite_path"]
