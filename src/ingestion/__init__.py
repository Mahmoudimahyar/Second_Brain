"""V1 ingestion plane. Public API per `docs/04-architecture/module-boundaries.md`."""

from src.ingestion.api import DumpManifest, DumpReceipt, IngestionService

__all__ = ["DumpManifest", "DumpReceipt", "IngestionService"]
