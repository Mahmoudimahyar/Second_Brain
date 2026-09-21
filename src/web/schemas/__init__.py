"""V1.5b/V1.5c — central Pydantic schemas for the ``/api/v1/*`` surface.

Populated by W2-5 (gap-audit MED-1). Each route module's request/response
shapes live in a sibling module here (``sources.py``, ``graph.py``, etc.).
The OpenAPI export at ``tools/generate_types.py`` scans this directory
when emitting the typed TS client + Zod schemas (per ADR-013, partially
implemented; W2-6 documents the codegen-drift status).
"""
