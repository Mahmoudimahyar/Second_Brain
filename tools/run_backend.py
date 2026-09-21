"""Boot script for the V1.5 FastAPI backend on :8000.

Loads `.env` into os.environ (so the gateway picks up all 4 API keys),
explicitly UNSETS `SECBRAIN_OFFLINE` so production gateway paths run,
then hands off to uvicorn pointing at `src.web.app:create_app`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if __name__ == "__main__":
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and v:
                    os.environ[k] = v

    os.environ.pop("SECBRAIN_OFFLINE", None)

    import uvicorn

    print(f"keys loaded: ANTHROPIC={'yes' if os.environ.get('ANTHROPIC_API_KEY') else 'no'} "
          f"GEMINI/GOOGLE={'yes' if os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY') else 'no'} "
          f"OPENAI={'yes' if os.environ.get('OPENAI_API_KEY') else 'no'} "
          f"TAVILY={'yes' if os.environ.get('TAVILY_API_KEY') else 'no'}",
          flush=True)

    uvicorn.run(
        "src.web.app:create_app",
        host="127.0.0.1",
        port=8000,
        factory=True,
        reload=False,
        log_level="info",
    )
    sys.exit(0)
