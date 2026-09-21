"""V1.5b — FastAPI web layer mounting `/api/v1/*`.

Per ADR-013. Localhost-only binding (V1.5 has no auth — single-user).
Pydantic models live under `src/web/schemas/` and are the source-of-truth
for the Pydantic→Zod codegen consumed by `web/`.
"""
