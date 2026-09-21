"""L1 adapter for the DentistJourney production DB dump (gold-standard L1).

The `DJ-Backup` PostgreSQL dump carries the authoritative dental-school universe
(`dental_schools_dentalschool` = 78 schools) + the official-name/alias backbone
(`market_intel_schoolalias` = 322 aliases) used to anchor forum entity
resolution. This module parses the `pg_restore --data-only` COPY output (no live
server needed) into:
  - `L1School` + `L1Alias` records → the canonical index (reusing the L1 Excel
    adapter's SQLite schema + `persist`), the backbone for `Pass1MentionExtractor`;
  - rich `School` graph nodes (L1, immutable) carrying the gold facts as properties.

Cleaner than the ADEA Excel path (no aggregate-row artifacts — GAP-056).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.graph.client import Node
from src.ingestion.adapters.l1_excel import L1Alias, L1School
from src.shared.ids import slugify

_COPY_RE = re.compile(r"^COPY (?:public\.)?(\S+) \((.*)\) FROM stdin;")
_ESC = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\", "b": "\b", "f": "\f", "v": "\v"}

SCHOOL_TABLE = "dental_schools_dentalschool"
ALIAS_TABLE = "market_intel_schoolalias"

# Gold facts carried onto the School node (besides canonical_name/city/state).
_BOOL_COLS = frozenset({"is_canadian", "interview_required", "is_ivy_league", "secondary_application"})
_INT_COLS = frozenset({"clinic_count", "faculty_count", "program_length_months", "research_centers"})
_FLOAT_COLS = frozenset({"avg_board_pass_rate", "job_placement_rate"})
_STR_FACT_COLS = (
    "short_name", "institution_type", "degree_offered", "website",
    "accepts_international", "application_deadline", "patient_visits", "district",
)
_FACT_COLS = (*_STR_FACT_COLS, *_BOOL_COLS, *_INT_COLS, *_FLOAT_COLS)

# Test/placeholder/aggregate rows that must never enter the canonical index
# (e.g. "Test University" in programs_institution; ADEA aggregate rows — GAP-056).
_JUNK_NAME_RE = re.compile(
    r"\b(test|sample|example|demo|placeholder|dummy|tbd|unknown|"
    r"mean|median|average|totals?|non-?zero|excluding)\b",
    re.IGNORECASE,
)


def is_junk_entity_name(name: str | None) -> bool:
    """True for test / placeholder / aggregate names (skip at ingest)."""
    n = (name or "").strip()
    if not n:
        return True
    return bool(_JUNK_NAME_RE.search(n)) or n.lower().startswith("number of")


def find_pg_restore(explicit: str | None = None) -> str | None:
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("pg_restore")
    if found:
        return found
    for version in ("17", "18", "16", "15"):
        cand = Path(f"C:/Program Files/PostgreSQL/{version}/bin/pg_restore.exe")
        if cand.is_file():
            return str(cand)
    return None


def extract_from_dump(dump_path: Path, *, pg_restore_bin: str | None = None) -> str:
    """Run `pg_restore --data-only` for the backbone tables (no live server) → SQL."""
    pgr = find_pg_restore(pg_restore_bin)
    if pgr is None:
        raise RuntimeError(
            "pg_restore not found — install PostgreSQL client tools or pass --pg-restore.",
        )
    proc = subprocess.run(
        [pgr, "--data-only", "--no-owner", "-t", SCHOOL_TABLE, "-t", ALIAS_TABLE,
         "-f", "-", str(dump_path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore failed: {proc.stderr[-500:]}")
    return proc.stdout


def _unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(1)), value)


def parse_copy_dump(sql_text: str) -> dict[str, list[dict[str, str | None]]]:
    """Parse `pg_restore --data-only` output (COPY blocks) → {table: [row dict]}."""
    tables: dict[str, list[dict[str, str | None]]] = {}
    lines = sql_text.split("\n")
    i = 0
    while i < len(lines):
        m = _COPY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        table = m.group(1)
        cols = [c.strip().strip('"') for c in m.group(2).split(",")]
        rows: list[dict[str, str | None]] = []
        i += 1
        while i < len(lines) and lines[i] != r"\.":
            fields = lines[i].split("\t")
            rows.append({c: _unescape(f) for c, f in zip(cols, fields, strict=False)})
            i += 1
        tables[table] = rows
        i += 1
    return tables


def _coerce(col: str, value: str) -> Any:
    if col in _BOOL_COLS:
        return value == "t"
    if col in _INT_COLS:
        try:
            return int(value)
        except ValueError:
            return None
    if col in _FLOAT_COLS:
        try:
            return float(value)
        except ValueError:
            return None
    return value


@dataclass(frozen=True)
class DBL1Result:
    schools: list[L1School]
    aliases: list[L1Alias]
    nodes: list[Node]                 # rich L1 School nodes (gold facts as properties)
    db_id_to_canonical: dict[str, str]


def build_l1_from_dump(sql_text: str, *, source_dump_id: str) -> DBL1Result:
    """Parse the DB COPY dump → canonical (`L1School`/`L1Alias`) + rich School nodes."""
    tables = parse_copy_dump(sql_text)
    schools: list[L1School] = []
    aliases: list[L1Alias] = []
    nodes: list[Node] = []
    db_id_to_canonical: dict[str, str] = {}

    for row in tables.get(SCHOOL_TABLE, []):
        name = (row.get("name") or "").strip()
        if not name or is_junk_entity_name(name):
            continue
        canonical_id = f"school:{slugify(name)}"
        db_id = row.get("id")
        if db_id:
            db_id_to_canonical[str(db_id)] = canonical_id
        schools.append(L1School(
            canonical_id=canonical_id, canonical_name=name,
            city=row.get("city"), state=row.get("state"),
            source_row=f"{SCHOOL_TABLE}:{db_id}",
        ))
        props: dict[str, Any] = {"canonical_name": name, "source_dump_id": source_dump_id}
        if row.get("city"):
            props["city"] = row["city"]
        if row.get("state"):
            props["state"] = row["state"]
        for col in _FACT_COLS:
            raw = row.get(col)
            if raw is not None and raw != "":
                coerced = _coerce(col, raw)
                if coerced is not None:
                    props[col] = coerced
        nodes.append(Node(id=canonical_id, label="School", source_tier="L1", properties=props))

        aliases.append(L1Alias(alias_text=name, canonical_id=canonical_id,
                               alias_source="db_name", confidence=1.0))
        short = (row.get("short_name") or "").strip()
        if short and short.lower() != name.lower():
            aliases.append(L1Alias(alias_text=short, canonical_id=canonical_id,
                                   alias_source="db_short_name", confidence=1.0))

    for row in tables.get(ALIAS_TABLE, []):
        alias = (row.get("alias") or "").strip()
        sid = row.get("school_id")
        cid = db_id_to_canonical.get(str(sid)) if sid else None
        if alias and cid:
            try:
                conf = float(row.get("confidence") or 1.0)
            except ValueError:
                conf = 1.0
            aliases.append(L1Alias(alias_text=alias, canonical_id=cid,
                                   alias_source="market_intel", confidence=conf))

    return DBL1Result(
        schools=schools, aliases=aliases, nodes=nodes,
        db_id_to_canonical=db_id_to_canonical,
    )
