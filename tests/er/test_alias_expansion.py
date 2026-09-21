"""Tests for `src.er.alias_expansion.expand_aliases`."""

from __future__ import annotations

import pytest

from src.er.alias_expansion import expand_aliases


def _texts(canonical_id: str, canonical_name: str) -> set[str]:
    return {a.alias_text for a in expand_aliases(canonical_id, canonical_name)}


def test_nyu_pattern_hit() -> None:
    aliases = _texts("school:nyu", "New York University, College of Dentistry")
    assert "NYU" in aliases
    assert "New York University" in aliases


def test_harvard_pattern_hit() -> None:
    aliases = _texts("school:harvard", "Harvard School of Dental Medicine")
    assert "Harvard" in aliases


def test_upenn_pattern_hit() -> None:
    aliases = _texts(
        "school:upenn",
        "University of Pennsylvania School of Dental Medicine",
    )
    assert "Penn" in aliases
    assert "UPenn" in aliases
    assert "U of P" in aliases


def test_ucla_pattern_hit() -> None:
    aliases = _texts("school:ucla", "University of California, Los Angeles")
    assert "UCLA" in aliases


def test_ucsf_pattern_hit() -> None:
    aliases = _texts("school:ucsf", "University of California, San Francisco")
    assert "UCSF" in aliases


def test_acronym_fallback_for_unknown_school() -> None:
    aliases = _texts(
        "school:texasam",
        "Texas A and M College of Dentistry",
    )
    # Acronym strips stopwords like "and" → "TMCD" or similar; just verify
    # something acronym-like is present.
    has_acronym = any(a.isupper() and 3 <= len(a) <= 6 for a in aliases)
    assert has_acronym


def test_no_two_letter_word_initial_acronyms() -> None:
    """2-letter word-initial acronyms collide with English words ("OF"/"OR")
    and are too ambiguous — they must not be generated (precision fix)."""
    for cid, name in (
        ("specialty:orthodontics_fellowship", "Orthodontics Fellowship"),  # -> "OF"
        ("specialty:oral_biology", "Oral Biology"),                        # -> "OB"
        ("specialty:orofacial_pain", "Orofacial Pain"),                    # -> "OP"
    ):
        acronyms = {a.alias_text for a in expand_aliases(cid, name)
                    if a.source == "acronym"}
        assert not any(len(a) == 2 for a in acronyms), f"{name} -> {acronyms}"


def test_all_caps_name_no_embedded_word_acronyms() -> None:
    """ALL-CAPS DB names must not yield common-word "embedded acronyms"
    ("HIGH"/"POINT"/"ORAL") — the heuristic only applies to mixed-case text."""
    aliases = _texts(
        "school:high_point",
        "HIGH POINT UNIVERSITY SCHOOL OF DENTAL MEDICINE AND ORAL HEALTH",
    )
    assert {"HIGH", "POINT", "ORAL"} & aliases == set()


def test_mixed_case_embedded_acronym_still_works() -> None:
    """The genuine case (an acronym embedded in mixed-case text) still fires."""
    aliases = _texts(
        "school:usc", "Herman Ostrow School of Dentistry of USC",
    )
    assert "USC" in aliases


def test_first_phrase_prefix_emitted() -> None:
    aliases = _texts(
        "school:nyu",
        "New York University, College of Dentistry",
    )
    assert "New York University" in aliases


def test_stripped_tail_drops_known_suffix() -> None:
    aliases = _texts(
        "school:tufts",
        "Tufts University School of Dental Medicine",
    )
    assert "Tufts University" in aliases


def test_returns_empty_for_blank_name() -> None:
    assert expand_aliases("school:x", "") == []


def test_dedupes_repeats() -> None:
    """If pattern + acronym both yield "NYU", only one entry is returned."""

    out = expand_aliases("school:nyu", "New York University, College of Dentistry")
    texts = [a.alias_text.lower() for a in out]
    assert len(texts) == len(set(texts))


def test_sources_are_labeled() -> None:
    out = expand_aliases("school:upenn",
                          "University of Pennsylvania School of Dental Medicine")
    sources = {a.source for a in out}
    assert "pattern" in sources
    # At least one of the rule-based sources should be tagged.
    assert sources & {"first_phrase", "stripped_tail", "acronym"}


def test_min_length_filter() -> None:
    """Single-character aliases shouldn't be emitted."""

    out = expand_aliases("school:x", "A")
    for a in out:
        assert len(a.alias_text) >= 2


def test_pattern_takes_priority_over_acronym() -> None:
    """Known patterns produce friendly forms (UPenn, Penn) — not raw acronyms (UoPSoDM)."""

    out = expand_aliases("school:upenn",
                          "University of Pennsylvania School of Dental Medicine")
    pattern_aliases = {a.alias_text for a in out if a.source == "pattern"}
    assert "Penn" in pattern_aliases
    assert "UPenn" in pattern_aliases


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Boston University Henry M. Goldman School of Dental Medicine", "BU"),
        ("University of Southern California, Herman Ostrow School of Dentistry", "USC"),
        ("University of Michigan School of Dentistry", "Michigan"),
        ("Case Western Reserve University School of Dental Medicine", "Case"),
        ("Tufts University School of Dental Medicine", "Tufts"),
    ],
)
def test_well_known_schools(name: str, expected: str) -> None:
    aliases = _texts("school:x", name)
    assert expected in aliases
