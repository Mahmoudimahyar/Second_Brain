"""Gold-set F1 gate test for MappingSuggester (AC-3, FR-1.5a-3.4).

Uses the deterministic `HashEmbeddingService`. The lexical (rapidfuzz) match
signal dominates for these canonical column shapes — sufficient to gate.
A BGE-based gold-set run is exercised separately when BGE weights are
warm-cached locally (slow first run).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.mapping_suggester import MappingSuggester
from src.ingestion.sources.base import (
    ColumnSpec,
    ForeignKeySpec,
    SchemaSnapshot,
    TableSpec,
)

GOLD_PATH = Path("evals/gold/v1.5a-mapping-suggestions.jsonl")


def _load_gold() -> list[dict]:
    rows: list[dict] = []
    for raw_line in GOLD_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _gold_to_snapshot(item: dict) -> SchemaSnapshot:
    table = TableSpec(
        name=item["table"],
        column_specs=[
            ColumnSpec(name=name, type=ctype, nullable=True, sample_values=[])
            for name, ctype in item["columns"]
        ],
        primary_key=item.get("pk") or None,
        foreign_keys=[
            ForeignKeySpec(
                columns=fk["columns"],
                references_table=fk["references_table"],
                references_columns=fk["references_columns"],
            )
            for fk in item.get("fks", [])
        ],
    )
    return SchemaSnapshot(
        source_id=f"ds:gold:{item['id']}",
        discovered_at=datetime.now(UTC),
        tables=[table],
        labels=[],
        rel_types=[],
    )


def _f1_per_class(
    truth: list[tuple[str, str | None]],
    pred: list[tuple[str, str | None]],
) -> tuple[float, dict[str, float]]:
    """Compute micro + per-class F1.

    A prediction is correct if both the mapping_type AND (when applicable)
    target_type match the gold. For 'skip' / 'edge' (target=null), only
    mapping_type must match.
    """

    assert len(truth) == len(pred)
    tp_per: dict[str, int] = {}
    fp_per: dict[str, int] = {}
    fn_per: dict[str, int] = {}
    classes: set[str] = set()

    def _label(item: tuple[str, str | None]) -> str:
        mt, tt = item
        if mt in {"skip", "edge"}:
            return mt
        return f"{mt}:{tt}"

    for t, p in zip(truth, pred, strict=True):
        t_label = _label(t)
        p_label = _label(p)
        classes.add(t_label)
        classes.add(p_label)
        if t_label == p_label:
            tp_per[t_label] = tp_per.get(t_label, 0) + 1
        else:
            fp_per[p_label] = fp_per.get(p_label, 0) + 1
            fn_per[t_label] = fn_per.get(t_label, 0) + 1

    per_class_f1: dict[str, float] = {}
    for cls in classes:
        tp = tp_per.get(cls, 0)
        fp = fp_per.get(cls, 0)
        fn = fn_per.get(cls, 0)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_class_f1[cls] = f1
    # Micro-F1 across all 50 items
    micro_tp = sum(tp_per.values())
    micro_fp = sum(fp_per.values())
    micro_fn = sum(fn_per.values())
    p = micro_tp / (micro_tp + micro_fp) if (micro_tp + micro_fp) > 0 else 0.0
    r = micro_tp / (micro_tp + micro_fn) if (micro_tp + micro_fn) > 0 else 0.0
    micro_f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return micro_f1, per_class_f1


def test_mapping_suggester_f1_meets_gate() -> None:
    """AC-3: F1 ≥ 0.85 on the 50-pair gold set."""
    gold = _load_gold()
    assert len(gold) == 50, f"gold set must have 50 rows, got {len(gold)}"

    suggester = MappingSuggester(embedding_service=HashEmbeddingService())

    truth: list[tuple[str, str | None]] = []
    pred: list[tuple[str, str | None]] = []
    for item in gold:
        snap = _gold_to_snapshot(item)
        proposal = suggester.suggest(snap)
        per_table = proposal.per_table[0]
        truth.append((item["expected_mapping"], item.get("expected_target")))
        pred.append((per_table.mapping_type, per_table.target_type))

    micro_f1, per_class = _f1_per_class(truth, pred)
    assert micro_f1 >= 0.85, (
        f"MappingSuggester gold-set F1 {micro_f1:.3f} < 0.85 gate.\n"
        f"per-class: {per_class}"
    )


def test_gold_set_size_is_50() -> None:
    """Guards against accidental gold-set shrinkage."""
    gold = _load_gold()
    assert len(gold) == 50
