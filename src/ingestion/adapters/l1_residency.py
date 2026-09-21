"""L1 adapter for the DentistJourney residency programs (gold-standard L1).

The `DJ-Backup` PostgreSQL dump carries the authoritative residency universe in
three `programs_*` tables. This parses the `pg_restore --data-only` COPY output
(no live server) into the residency knowledge graph:

  - `Specialty` L1 nodes (31: Endodontics, OMFS, Periodontics ...) + their
    forum aliases ("OMFS"/"OMS"/"Oral Surgery", "Perio", "Endo", "Pedo" ...);
  - `Institution` L1 nodes (~298 residency sponsors) + aliases;
  - `Program` L1 nodes (~817 residency programs) carrying gold facts (positions,
    stipend, length, match participation, application service) as properties;
  - `OFFERED_BY` (Program -> Institution) + `IN_SPECIALTY` (Program -> Specialty)
    edges (100% referential integrity in the source).

The specialty + institution names/aliases feed the same canonical ER backbone
(`CanonicalIndex`) as the dental schools (`l1_db`), so a forum mention of "OMFS
at Penn" can resolve both the specialty and the institution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.graph.client import Edge, Node
from src.ingestion.adapters.l1_db import (
    find_pg_restore,
    is_junk_entity_name,
    parse_copy_dump,
)
from src.ingestion.adapters.l1_excel import L1Alias, L1School
from src.shared.ids import slugify

SPECIALTY_TABLE = "programs_specialty"
INSTITUTION_TABLE = "programs_institution"
PROGRAM_TABLE = "programs_program"

_RESIDENCY_TABLES = (SPECIALTY_TABLE, INSTITUTION_TABLE, PROGRAM_TABLE)

# Curated institution facts (excludes logo/branding URLs).
_INSTITUTION_FACTS = (
    "city", "state", "zip_code", "adea_group_number", "adea_institution_id",
    "institution_type", "website_url",
)
# Curated program facts (excludes the pgvector `embedding` + long prose blobs).
_PROGRAM_STR_FACTS = (
    "city", "state", "application_service", "adea_pass_code", "adea_slug",
    "application_deadline", "stipend_details", "website_url",
)
_PROGRAM_BOOL_FACTS = (
    "match_participating", "rolling_admissions", "stipend_offered",
    "supplemental_app_required", "foreign_trained_dentist_eligible", "is_active",
)
_PROGRAM_INT_FACTS = ("positions_available", "program_length_months")

_TRUE = frozenset({"t", "true", "1", "yes", "y"})
_FALSE = frozenset({"f", "false", "0", "no", "n"})


@dataclass(frozen=True)
class ResidencyResult:
    specialties: list[Node]
    institutions: list[Node]
    programs: list[Node]
    edges: list[Edge]
    aliases: list[L1Alias]
    canonical_registry: list[L1School] = field(default_factory=list)

    @property
    def nodes(self) -> list[Node]:
        return [*self.specialties, *self.institutions, *self.programs]


def extract_residency_from_dump(dump_path: Any, *, pg_restore_bin: str | None = None) -> str:
    """Run `pg_restore --data-only` for the three `programs_*` tables -> SQL."""
    import subprocess  # noqa: PLC0415 — local to keep import cost off the hot path

    pgr = find_pg_restore(pg_restore_bin)
    if pgr is None:
        raise RuntimeError(
            "pg_restore not found - install PostgreSQL client tools or pass --pg-restore.",
        )
    table_args: list[str] = []
    for tbl in _RESIDENCY_TABLES:
        table_args += ["-t", tbl]
    proc = subprocess.run(
        [pgr, "--data-only", "--no-owner", *table_args, "-f", "-", str(dump_path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore failed (exit {proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout


def _parse_alias_json(raw: Any) -> list[str]:
    """Source `aliases` column is a JSON array string, e.g. `["OMFS", "OMS"]`."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    low = str(value).strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _named_entity(
    rows: list[dict[str, Any]], id_col: str, *, prefix: str, label: str,
    table: str, alias_source: str, fact_cols: tuple[str, ...], source_dump_id: str,
) -> tuple[list[Node], list[L1Alias], list[L1School], dict[str, str]]:
    """Shared builder for Specialty/Institution (named L1 entities + aliases)."""
    nodes: list[Node] = []
    aliases: list[L1Alias] = []
    registry: list[L1School] = []
    db_to_canonical: dict[str, str] = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        db_id = row.get(id_col)
        if not name or not db_id or is_junk_entity_name(name):
            continue
        canonical_id = f"{prefix}:{slugify(name)}"
        db_to_canonical[str(db_id)] = canonical_id
        props: dict[str, Any] = {"canonical_name": name, "source_dump_id": source_dump_id}
        for col in fact_cols:
            if row.get(col):
                props[col] = row[col]
        nodes.append(Node(id=canonical_id, label=label, source_tier="L1", properties=props))
        registry.append(L1School(
            canonical_id=canonical_id, canonical_name=name,
            city=row.get("city"), state=row.get("state"),
            source_row=f"{table}:{db_id}",
        ))
        aliases.append(L1Alias(alias_text=name, canonical_id=canonical_id,
                               alias_source=alias_source, confidence=1.0))
        for alias in _parse_alias_json(row.get("aliases")):
            aliases.append(L1Alias(alias_text=alias, canonical_id=canonical_id,
                                   alias_source=f"{alias_source}_alias", confidence=1.0))
    return nodes, aliases, registry, db_to_canonical


def _program_props(row: dict[str, Any], source_dump_id: str) -> dict[str, Any]:
    name = (row.get("program_name") or "").strip()
    props: dict[str, Any] = {"canonical_name": name, "source_dump_id": source_dump_id}
    for col in _PROGRAM_STR_FACTS:
        if row.get(col):
            props[col] = row[col]
    for col in _PROGRAM_BOOL_FACTS:
        b = _as_bool(row.get(col))
        if b is not None:
            props[col] = b
    for col in _PROGRAM_INT_FACTS:
        n = _as_int(row.get(col))
        if n is not None:
            props[col] = n
    return props


def _build_programs(
    rows: list[dict[str, Any]], *, source_dump_id: str,
    spec_map: dict[str, str], inst_map: dict[str, str],
) -> tuple[list[Node], list[Edge]]:
    programs: list[Node] = []
    edges: list[Edge] = []
    for row in rows:
        pid = row.get("program_id")
        name = (row.get("program_name") or "").strip()
        if not pid or not name or is_junk_entity_name(name):
            continue
        canonical_id = f"program:{pid}"
        programs.append(Node(
            id=canonical_id, label="Program", source_tier="L1",
            properties=_program_props(row, source_dump_id),
        ))
        inst_cid = inst_map.get(str(row.get("institution_id")))
        if inst_cid:
            edges.append(Edge(
                id=f"edge:offered_by:{canonical_id}", label="OFFERED_BY",
                from_id=canonical_id, to_id=inst_cid, source_tier="L1", rank="normal",
            ))
        spec_cid = spec_map.get(str(row.get("specialty_id")))
        if spec_cid:
            edges.append(Edge(
                id=f"edge:in_specialty:{canonical_id}", label="IN_SPECIALTY",
                from_id=canonical_id, to_id=spec_cid, source_tier="L1", rank="normal",
            ))
    return programs, edges


def build_residency_from_dump(sql_text: str, *, source_dump_id: str) -> ResidencyResult:
    """Parse the residency COPY dump -> Specialty/Institution/Program nodes + edges."""
    tables = parse_copy_dump(sql_text)
    specialties, spec_aliases, spec_reg, spec_map = _named_entity(
        tables.get(SPECIALTY_TABLE, []), "specialty_id", prefix="specialty",
        label="Specialty", table=SPECIALTY_TABLE, alias_source="db_specialty",
        fact_cols=("description",), source_dump_id=source_dump_id,
    )
    institutions, inst_aliases, inst_reg, inst_map = _named_entity(
        tables.get(INSTITUTION_TABLE, []), "institution_id", prefix="institution",
        label="Institution", table=INSTITUTION_TABLE, alias_source="db_institution",
        fact_cols=_INSTITUTION_FACTS, source_dump_id=source_dump_id,
    )
    programs, edges = _build_programs(
        tables.get(PROGRAM_TABLE, []), source_dump_id=source_dump_id,
        spec_map=spec_map, inst_map=inst_map,
    )
    return ResidencyResult(
        specialties=specialties, institutions=institutions, programs=programs,
        edges=edges, aliases=[*spec_aliases, *inst_aliases],
        canonical_registry=[*spec_reg, *inst_reg],
    )
