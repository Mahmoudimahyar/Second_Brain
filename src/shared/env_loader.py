from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> int:
    """Load `KEY=VALUE` pairs from `path` into `os.environ`.

    Treats existing empty env vars as missing (Windows shadow-var workaround).
    Returns count of vars loaded.
    """

    if not path.is_file():
        return 0
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        key = k.strip()
        if os.environ.get(key):
            continue
        os.environ[key] = v.strip().split("#")[0].strip()
        loaded += 1
    return loaded
