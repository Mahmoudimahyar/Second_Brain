"""Per-statistic provenance (PV-1) — every number the dossier emits is traceable to
the exact set of source posts/comments it was computed from.

Principle: for a counted statistic ("30% of NYU reddit comments are positive"), the
value is a deterministic function over an explicit ID set, and that ID set *is* the
citation. The LLM never produces the number — so it is 100% faithful by construction
and fully auditable. Large ID sets are kept in a bounded in-process `ProvenanceStore`
keyed by a deterministic `stat_id`; the answer carries counts + a sample + the stat_id,
and a drill-down endpoint paginates the full set (hydrated to url+snippet).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field


def make_stat_id(*parts: object) -> str:
    """Deterministic short id for a statistic (stable across identical queries)."""
    return "stat:" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


@dataclass
class ProvenancedStat:
    """One statistic with its receipts. `value` is a fraction or a raw count; the full
    source-id set lives in the ProvenanceStore under `stat_id` (sample_ids inline)."""

    stat_id: str
    label: str
    value: float
    kind: str               # "fraction" | "count"
    numerator: int
    denominator: int
    source_kind: str        # "reddit_comment" | "reddit_post" | "sdn_post" | "mixed"
    method: str             # human-readable computation description
    sample_ids: list[str] = field(default_factory=list)  # first K for inline display

    def to_dict(self) -> dict:
        return {
            "stat_id": self.stat_id, "label": self.label, "value": self.value,
            "kind": self.kind, "numerator": self.numerator, "denominator": self.denominator,
            "source_kind": self.source_kind, "method": self.method,
            "sample_ids": self.sample_ids,
            "drill_down": f"/api/v1/dossier/sources?stat_id={self.stat_id}",
        }


class ProvenanceStore:
    """Bounded in-process cache: stat_id -> full source-id list (+meta). Backs the
    /sources drill-down. stat_ids are deterministic, so a re-query re-populates it."""

    def __init__(self, cap: int = 1024) -> None:
        self._d: OrderedDict[str, dict] = OrderedDict()
        self._cap = cap

    def record(self, stat_id: str, ids: list[str], *, source_kind: str,
               method: str, label: str) -> None:
        self._d[stat_id] = {"ids": list(ids), "source_kind": source_kind,
                            "method": method, "label": label}
        self._d.move_to_end(stat_id)
        while len(self._d) > self._cap:
            self._d.popitem(last=False)

    def get(self, stat_id: str) -> dict | None:
        rec = self._d.get(stat_id)
        if rec is not None:
            self._d.move_to_end(stat_id)
        return rec


def build_distribution(
    store: ProvenanceStore, *, prefix: str, buckets: dict[str, list[str]],
    source_kind: str, method: str, sample_k: int = 10,
) -> list[ProvenancedStat]:
    """Turn {bucket_label -> [doc_ids]} into provenanced fractions, recording each
    bucket's full id set in `store`. The fractions are exact counts over the union."""
    total = sum(len(v) for v in buckets.values())
    out: list[ProvenancedStat] = []
    for label, ids in buckets.items():
        sid = make_stat_id(prefix, label)
        store.record(sid, ids, source_kind=source_kind, method=method, label=label)
        out.append(ProvenancedStat(
            stat_id=sid, label=label,
            value=round(len(ids) / total, 4) if total else 0.0,
            kind="fraction", numerator=len(ids), denominator=total,
            source_kind=source_kind, method=method, sample_ids=ids[:sample_k],
        ))
    out.sort(key=lambda s: -s.numerator)
    return out
