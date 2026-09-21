"""V1.5b — Pydantic → TypeScript/Zod codegen (FR-1.5b-1.2 + NFR-1.5b-3).

Renders an OpenAPI spec from the FastAPI app, then derives TS types into
`web/src/lib/api/generated/`. CI gate breaks on schema drift.

This is a minimal stub — V1.5b ships with hand-authored types in
`web/src/lib/api/client.ts`. When the corpus grows beyond a single
hand-maintained module, swap this in via `datamodel-code-generator` or
`pydantic-to-zod`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    from src.web.app import create_app  # noqa: PLC0415
    app = create_app()
    spec = app.openapi()
    out_dir = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "api" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_file = out_dir / "openapi.json"
    spec_file.write_text(
        json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8",
    )
    print(f"wrote {spec_file}")

    # Minimal TS type emission — derive endpoint names + response shapes.
    # V1.5b stays on hand-maintained types in `client.ts`; this emission
    # is the source of truth for the CI drift gate.
    ts_path = out_dir / "openapi-paths.d.ts"
    paths = sorted(spec["paths"].keys())
    ts_lines = [
        "// Auto-generated from FastAPI OpenAPI. Do not edit by hand.",
        "// Run `python tools/generate_types.py` to regenerate.",
        "",
        "export type ApiPath =",
        *[f"  | {json.dumps(p)}" for p in paths],
        "  ;",
    ]
    ts_path.write_text("\n".join(ts_lines) + "\n", encoding="utf-8")
    print(f"wrote {ts_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
