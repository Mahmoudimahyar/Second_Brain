"""Tests for the DJ-Backup L1 DB adapter — COPY parsing + School/alias build."""

from __future__ import annotations

from src.ingestion.adapters.l1_db import build_l1_from_dump, parse_copy_dump

_SQL = (
    "COPY public.dental_schools_dentalschool (id, name, short_name, state, city, "
    "institution_type, avg_board_pass_rate, interview_required, is_canadian, "
    "degree_offered) FROM stdin;\n"
    "77\tARIZONA SCHOOL OF DENTISTRY & ORAL HEALTH\tASDOH\tAZ\tMesa\tPRIVATE\t92.5\tt\tf\tDMD\n"
    "80\tCALIFORNIA NORTHSTATE UNIVERSITY, COLLEGE OF DENTAL MEDICINE\t\\N\tCA\t"
    "Elk Grove\tPUBLIC\t\\N\tf\tf\tDDS\n"
    "\\.\n"
    "COPY public.market_intel_schoolalias (id, alias, source, confidence, created_at, "
    "school_id) FROM stdin;\n"
    "1\tASDOH\tsdn\t0.9\t2026-01-01\t77\n"
    "2\tA.T. Still\tforum\t0.8\t2026-01-01\t77\n"
    "3\tCNU Dental\tforum\t0.7\t2026-01-01\t80\n"
    "\\.\n"
)


def test_parse_copy_dump_tables_and_nulls() -> None:
    tables = parse_copy_dump(_SQL)
    assert set(tables) == {"dental_schools_dentalschool", "market_intel_schoolalias"}
    schools = tables["dental_schools_dentalschool"]
    assert len(schools) == 2
    assert schools[0]["name"] == "ARIZONA SCHOOL OF DENTISTRY & ORAL HEALTH"
    assert schools[1]["short_name"] is None              # \N -> None
    assert schools[1]["avg_board_pass_rate"] is None


def test_build_l1_schools_nodes_and_coercion() -> None:
    r = build_l1_from_dump(_SQL, source_dump_id="db:test")
    assert len(r.schools) == 2
    assert len(r.nodes) == 2
    asdoh = next(n for n in r.nodes if "arizona" in n.id)
    assert asdoh.label == "School" and asdoh.source_tier == "L1"
    assert asdoh.properties["state"] == "AZ"
    assert asdoh.properties["avg_board_pass_rate"] == 92.5   # float coercion
    assert asdoh.properties["interview_required"] is True     # bool coercion
    assert asdoh.properties["degree_offered"] == "DMD"
    assert r.db_id_to_canonical["77"] == asdoh.id


def test_aliases_link_to_correct_school() -> None:
    r = build_l1_from_dump(_SQL, source_dump_id="db:test")
    asdoh = next(n for n in r.nodes if "arizona" in n.id)
    asdoh_aliases = {a.alias_text for a in r.aliases if a.canonical_id == asdoh.id}
    # self-aliases (name + short_name) + market_intel aliases for school 77.
    assert "ARIZONA SCHOOL OF DENTISTRY & ORAL HEALTH" in asdoh_aliases
    assert "ASDOH" in asdoh_aliases
    assert "A.T. Still" in asdoh_aliases

    cnu = next(n for n in r.nodes if "california_northstate" in n.id)
    cnu_aliases = {a.alias_text for a in r.aliases if a.canonical_id == cnu.id}
    assert "CNU Dental" in cnu_aliases                    # alias for school 80
    assert "A.T. Still" not in cnu_aliases                # not cross-linked
    assert cnu.properties.get("avg_board_pass_rate") is None  # \N not added


def test_empty_input_is_safe() -> None:
    r = build_l1_from_dump("-- no copy blocks here\n", source_dump_id="db:x")
    assert r.schools == [] and r.nodes == [] and r.aliases == []
