from __future__ import annotations

import re
from hashlib import sha256

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("_", text.lower()).strip("_")
    return slug or "_"


def make_dump_id(source_tier: str, content_hashes: list[str]) -> str:
    h = sha256()
    h.update(source_tier.encode("ascii"))
    h.update(b"|")
    for ch in sorted(content_hashes):
        h.update(ch.encode("ascii"))
    return f"dump:{h.hexdigest()[:16]}"
