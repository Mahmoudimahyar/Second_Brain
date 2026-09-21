"""V1.5b — `secbrain ui` dev orchestrator (FR-1.5b-1.3).

Boots uvicorn (FastAPI) + pnpm dev (Next.js) together, opens a browser
to the Next.js root, and ensures graceful shutdown on Ctrl-C.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import NoReturn


def project_root() -> Path:
    """Find the repo root from this module's path."""

    return Path(__file__).resolve().parents[2]


def _spawn_backend(host: str, port: int) -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable, "-m", "uvicorn",
        "src.web.app:create_app",
        "--factory",
        "--host", host,
        "--port", str(port),
        "--reload",
    ]
    return subprocess.Popen(
        cmd, cwd=project_root(),
    )


def _spawn_frontend(port: int) -> subprocess.Popen[bytes] | None:
    web_dir = project_root() / "web"
    if not web_dir.is_dir():
        return None
    if (web_dir / "package.json").exists() is False:
        return None
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{port}"
    cmd = ["pnpm", "dev"]
    return subprocess.Popen(
        cmd, cwd=web_dir, env=env, shell=False,
    )


def run(
    *,
    api_host: str = "127.0.0.1",
    api_port: int = 8000,
    ui_port: int = 3000,
    open_browser: bool = True,
) -> NoReturn:
    """Spawn FastAPI + Next.js dev servers and block until interrupted."""

    backend = _spawn_backend(api_host, api_port)
    frontend = _spawn_frontend(api_port)

    print(f"[secbrain ui] backend → http://{api_host}:{api_port}")
    if frontend is not None:
        print(f"[secbrain ui] frontend → http://localhost:{ui_port}")
    else:
        print(
            "[secbrain ui] frontend not started — `web/` not scaffolded "
            "yet. Run `pnpm create next-app@latest web --typescript "
            "--tailwind --app --use-pnpm` first.",
        )

    if open_browser:
        time.sleep(2)
        url = (
            f"http://localhost:{ui_port}"
            if frontend is not None
            else f"http://{api_host}:{api_port}/docs"
        )
        with contextlib.suppress(Exception):
            webbrowser.open(url)

    def _shutdown(signum: int, frame: object) -> None:
        del signum, frame
        print("\n[secbrain ui] shutting down...")
        for proc in (frontend, backend):
            if proc is None:
                continue
            with contextlib.suppress(Exception):
                proc.terminate()
        for proc in (frontend, backend):
            if proc is None:
                continue
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)
        if backend.poll() is not None:
            print("[secbrain ui] backend exited; shutting down")
            _shutdown(0, None)
        if frontend is not None and frontend.poll() is not None:
            print("[secbrain ui] frontend exited; shutting down")
            _shutdown(0, None)


__all__ = ["run"]
