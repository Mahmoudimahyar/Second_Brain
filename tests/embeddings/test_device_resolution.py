"""WP2.1 / GAP-054 — `resolve_device` honors CUDA_VISIBLE_DEVICES.

The V1 host's Pascal GTX 1080 crashed the round-1 ingest (Q-028). Pass 1-2 need
no GPU and never build the embedder; Pass 3 does, and must be forceable to CPU.
"""

from __future__ import annotations

import pytest

from src.embeddings.bge_embedder import resolve_device


def test_cpu_requested_stays_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    assert resolve_device("cpu") == "cpu"


def test_empty_cuda_visible_devices_forces_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    assert resolve_device("cuda") == "cpu"
    assert resolve_device("auto") == "cpu"
    assert resolve_device("cpu") == "cpu"


def test_explicit_cuda_with_visible_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    assert resolve_device("cuda") == "cuda"


def test_auto_returns_a_valid_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    assert resolve_device("auto") in {"cpu", "cuda"}
