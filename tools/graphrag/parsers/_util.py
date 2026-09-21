"""Shared parser utilities. Single source of truth for cross-parser helpers."""

from __future__ import annotations

import hashlib


def hash_text(s: str) -> str:
    """SHA-256 hex of UTF-8-encoded `s`."""

    return hashlib.sha256(s.encode("utf-8")).hexdigest()
