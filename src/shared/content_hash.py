from __future__ import annotations

from hashlib import sha256
from pathlib import Path

_CHUNK = 1 << 16


def content_hash_file(path: Path) -> str:
    h = sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def content_hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def content_hash_str(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
