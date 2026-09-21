from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]


@runtime_checkable
class SourceAdapter(Protocol):
    """Pluggable source-type adapter (A-013).

    Adapters normalize raw payloads into canonical records keyed to a
    `DumpReceipt`'s `dump_id`. Auto-discoverable in V1.x; V1 uses direct
    instantiation per `src.ingestion.api.IngestionService`.
    """

    source_tier: SourceTier

    def normalize(self, payload_paths: list[Path]) -> Iterable[object]: ...
