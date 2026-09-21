"""Tests for the DJ-Backup residency L1 adapter (programs_* COPY -> graph)."""

from __future__ import annotations

from src.ingestion.adapters.l1_residency import (
    _parse_alias_json,
    build_residency_from_dump,
)

_SQL = (
    "COPY public.programs_specialty (specialty_id, name, description, aliases) "
    "FROM stdin;\n"
    '40\tOral and Maxillofacial Surgery\tSurgery of face/jaw\t["OMFS", "OMS", "Oral Surgery"]\n'
    "52\tPeriodontics\t\\N\t[\"Perio\"]\n"
    "\\.\n"
    "COPY public.programs_institution (institution_id, name, city, state, "
    "adea_institution_id, institution_type, aliases) FROM stdin;\n"
    '10\tUniversity of Pennsylvania\tPhiladelphia\tPA\t99\tDENTAL_SCHOOL\t["Penn", "UPenn"]\n'
    "\\.\n"
    "COPY public.programs_program (program_id, program_name, institution_id, "
    "specialty_id, positions_available, program_length_months, match_participating, "
    "is_active, application_service) FROM stdin;\n"
    "500\tPenn OMFS Residency\t10\t40\t4\t72\tt\tt\tPASS\n"
    "501\tPenn Perio\t10\t52\t3\t36\tf\tt\tPASS\n"
    "502\tOrphan Program\t999\t999\t1\t12\tt\tt\tPASS\n"
    "\\.\n"
)


def test_parse_alias_json() -> None:
    assert _parse_alias_json('["OMFS", "OMS"]') == ["OMFS", "OMS"]
    assert _parse_alias_json("[]") == []
    assert _parse_alias_json(None) == []
    assert _parse_alias_json("not json") == []


def test_build_counts_and_tiers() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    assert len(r.specialties) == 2
    assert len(r.institutions) == 1
    assert len(r.programs) == 3
    assert all(n.source_tier == "L1" for n in r.nodes)
    assert {n.label for n in r.nodes} == {"Specialty", "Institution", "Program"}


def test_specialty_aliases_indexed() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    omfs = next(n for n in r.specialties if "maxillofacial" in n.id)
    omfs_aliases = {a.alias_text for a in r.aliases if a.canonical_id == omfs.id}
    assert {"Oral and Maxillofacial Surgery", "OMFS", "OMS", "Oral Surgery"} <= omfs_aliases


def test_program_facts_coerced() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    omfs_prog = next(n for n in r.programs if n.id == "program:500")
    assert omfs_prog.properties["positions_available"] == 4          # int
    assert omfs_prog.properties["program_length_months"] == 72       # int
    assert omfs_prog.properties["match_participating"] is True        # bool
    assert omfs_prog.properties["is_active"] is True
    assert omfs_prog.properties["application_service"] == "PASS"
    perio_prog = next(n for n in r.programs if n.id == "program:501")
    assert perio_prog.properties["match_participating"] is False


def test_edges_link_program_to_institution_and_specialty() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    by_pair = {(e.label, e.from_id, e.to_id) for e in r.edges}
    assert ("OFFERED_BY", "program:500", "institution:university_of_pennsylvania") in by_pair
    assert ("IN_SPECIALTY", "program:500", "specialty:oral_and_maxillofacial_surgery") in by_pair
    assert all(e.source_tier == "L1" for e in r.edges)


def test_orphan_program_gets_no_edges() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    orphan_edges = [e for e in r.edges if e.from_id == "program:502"]
    assert orphan_edges == []                      # inst/specialty 999 absent -> no edge


def test_canonical_registry_has_specialties_and_institutions() -> None:
    r = build_residency_from_dump(_SQL, source_dump_id="db:test")
    ids = {s.canonical_id for s in r.canonical_registry}
    assert "specialty:periodontics" in ids
    assert "institution:university_of_pennsylvania" in ids


def test_empty_input_is_safe() -> None:
    r = build_residency_from_dump("-- nothing\n", source_dump_id="db:x")
    assert r.nodes == [] and r.edges == [] and r.aliases == []
