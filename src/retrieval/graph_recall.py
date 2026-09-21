"""Graph-anchored recall — use entity structure to recover evidence that flat
text/embedding search misses, and to surface high-signal focus nodes.

Decision (`project_evidence_dossier`): the graph is the candidate-set **definer +
prioritizer**; text/embeddings **rank within**. The graph also yields **exact**
per-entity census counts (not keyword guesses).

This reader is backed by the bundle's **Parquet** export via DuckDB — lock-free and
crash-safe, so it runs on the EC2 VM (or against the shipped bundle) with **no Kùzu
buffer-pool risk**. The production API can swap in bounded Kùzu point-lookups
(ADR-025: <3 ms multi-hop) behind the same `GraphCandidates` contract.

NEVER point this at a live local Kùzu DB on the workstation — heavy graph I/O there
has crashed the PC. Parquet/DuckDB only, or run on the VM.

What the graph covers (verified 2026-06-18, canonical graph 4.56M/13.1M):
  - `MENTIONS_SCHOOL` (712,471) is **SDN-only** (all `sdn_post`; reddit has none).
    So graph-anchored recall is the strong path for **SDN** evidence; **reddit**
    evidence is recovered by the text sources (FTS5 + comment/post embeddings) and by
    `Claim.resolved_school_id`, NOT by this module. The dossier unions both.
  - Thread model: reddit `Comment -BELONGS_TO_THREAD-> Post(root)`; SDN
    `Post -BELONGS_TO_THREAD-> SDNThread`. SDN recovery walks posts→thread→members.
  - Entities dedupe via `SAME_AS` (e.g. NYU = 2 `school:` nodes + 1 `institution:`);
    recall unions the closure.

Validated (NYU, on VM, parquet/duckdb): 38,989 SDN posts mention NYU; they sit in
10,014 SDN threads totalling **154,013 posts** — ~4× recovery from structure alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_MENTIONS_SCHOOL = "MENTIONS_SCHOOL"
_BELONGS_TO_THREAD = "BELONGS_TO_THREAD"
_CONSENSUS_FOR = "CONSENSUS_FOR"
_ASKED_AT = "ASKED_AT"
_SAME_AS = "SAME_AS"


@dataclass
class GraphCandidates:
    """Entity-anchored candidate evidence + exact counts for one school."""

    school_id: str
    same_as_ids: list[str] = field(default_factory=list)
    mentioning_post_ids: list[str] = field(default_factory=list)   # SDN posts naming the school
    thread_member_ids: list[str] = field(default_factory=list)     # all posts in those SDN threads
    consensus_ids: list[str] = field(default_factory=list)
    l1_claim_ids: list[str] = field(default_factory=list)
    interview_q_ids: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)           # exact population counts
    truncated: dict[str, bool] = field(default_factory=dict)

    def candidate_doc_ids(self) -> list[str]:
        """Deduped SDN evidence doc ids (mentioning posts ∪ thread members)."""
        seen: set[str] = set()
        out: list[str] = []
        for did in (*self.mentioning_post_ids, *self.thread_member_ids):
            if did not in seen:
                seen.add(did)
                out.append(did)
        return out

    def to_dict(self) -> dict:
        return {
            "school_id": self.school_id,
            "same_as_ids": self.same_as_ids,
            "counts": self.counts,
            "truncated": self.truncated,
            "n_mentioning_posts": len(self.mentioning_post_ids),
            "n_thread_members": len(self.thread_member_ids),
            "n_consensus": len(self.consensus_ids),
            "n_l1_claims": len(self.l1_claim_ids),
            "n_interview_qs": len(self.interview_q_ids),
        }


class ParquetGraphReader:
    """Lock-free graph reader over the bundle's nodes/edges Parquet via DuckDB."""

    def __init__(self, nodes_parquet: str, edges_parquet: str) -> None:
        import duckdb  # noqa: PLC0415 — optional dep, bundle/VM only

        self.con = duckdb.connect()
        self.con.execute(
            f"CREATE VIEW nodes AS SELECT * FROM read_parquet('{nodes_parquet}')"
        )
        self.con.execute(
            f"CREATE VIEW edges AS SELECT * FROM read_parquet('{edges_parquet}')"
        )

    # -- primitives ---------------------------------------------------------

    def _load_ids(self, table: str, ids: list[str]) -> None:
        self.con.execute(f"CREATE OR REPLACE TEMP TABLE {table}(id VARCHAR)")
        if ids:
            self.con.executemany(f"INSERT INTO {table} VALUES (?)", [(i,) for i in ids])

    def from_ids_for_target(self, edge_label: str, to_id: str) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT from_id FROM edges WHERE label=? AND to_id=?",
            [edge_label, to_id],
        ).fetchall()]

    def from_ids_for_targets(self, edge_label: str, to_ids: list[str]) -> list[str]:
        if not to_ids:
            return []
        self._load_ids("_tgt", to_ids)
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT e.from_id FROM edges e JOIN _tgt t ON e.to_id=t.id WHERE e.label=?",
            [edge_label],
        ).fetchall()]

    def to_ids_for_sources(self, edge_label: str, from_ids: list[str]) -> list[str]:
        if not from_ids:
            return []
        self._load_ids("_src", from_ids)
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT e.to_id FROM edges e JOIN _src s ON e.from_id=s.id WHERE e.label=?",
            [edge_label],
        ).fetchall()]

    def same_as_closure(self, school_id: str, *, max_iter: int = 4, max_ids: int = 25) -> list[str]:
        """Bidirectional SAME_AS closure (bounded) so dup school/institution nodes unite."""
        closure: set[str] = {school_id}
        frontier: set[str] = {school_id}
        for _ in range(max_iter):
            if not frontier or len(closure) >= max_ids:
                break
            fl = list(frontier)
            self._load_ids("_f", fl)
            rows = self.con.execute(
                "SELECT e.to_id FROM edges e JOIN _f f ON e.from_id=f.id WHERE e.label=? "
                "UNION SELECT e.from_id FROM edges e JOIN _f f ON e.to_id=f.id WHERE e.label=?",
                [_SAME_AS, _SAME_AS],
            ).fetchall()
            nxt = {r[0] for r in rows} - closure
            closure |= nxt
            frontier = nxt
        return sorted(closure)[:max_ids]

    def l1_claims_for(self, ids: list[str], *, cap: int = 50) -> list[str]:
        """L1 Claim nodes whose properties reference any of the school ids."""
        if not ids:
            return []
        likes = " OR ".join(["properties_json LIKE ?"] * len(ids))
        params = [f"%{i}%" for i in ids]
        return [r[0] for r in self.con.execute(
            f"SELECT id FROM nodes WHERE label='Claim' AND source_tier='L1' AND ({likes}) LIMIT {int(cap)}",
            params,
        ).fetchall()]

    def node_props(self, node_id: str) -> dict:
        """Parsed properties_json for a node id ({} if missing/unparseable)."""
        import json  # noqa: PLC0415

        r = self.con.execute(
            "SELECT properties_json FROM nodes WHERE id=? LIMIT 1", [node_id]
        ).fetchone()
        if not r or not r[0]:
            return {}
        try:
            return json.loads(r[0])
        except Exception:  # noqa: BLE001
            return {}

    def claim_resolved_post_ids(self, school_ids: list[str], *, cap: int = 100_000) -> list[str]:
        """Reddit/SDN posts behind Claims resolved to any of `school_ids` (C-path).

        Claim -EXTRACTED_FROM-> Post; the Claim's properties carry resolved_school_id.
        This recovers posts the Pass-4 LLM judged on-topic even without a literal alias.
        """
        if not school_ids:
            return []
        likes = " OR ".join(["properties_json LIKE ?"] * len(school_ids))
        params = [f"%{i}%" for i in school_ids]
        claim_ids = [r[0] for r in self.con.execute(
            f"SELECT id FROM nodes WHERE label='Claim' AND ({likes}) LIMIT {int(cap)}",
            params,
        ).fetchall()]
        if not claim_ids:
            return []
        self._load_ids("_cl", claim_ids)
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT e.to_id FROM edges e JOIN _cl c ON e.from_id=c.id "
            "WHERE e.label='EXTRACTED_FROM'",
        ).fetchall()]

    def sentiment_for(self, doc_ids: list[str]) -> dict[str, list[str]]:
        """{verdict -> [doc_id]} for the given docs, via ANNOTATES → SentimentAnnotation.

        SentimentAnnotation(from) -ANNOTATES-> Post/Comment(to); the annotation node's
        properties carry `verdict` (positive/negative/neutral). Returns the EXACT doc-id
        set per verdict so the sentiment percentages are auditable (PV-1).
        """
        if not doc_ids:
            return {}
        self._load_ids("_sd", doc_ids)
        rows = self.con.execute(
            "SELECT e.to_id, json_extract_string(n.properties_json,'verdict') v "
            "FROM edges e JOIN _sd s ON e.to_id=s.id JOIN nodes n ON e.from_id=n.id "
            "WHERE e.label='ANNOTATES'",
        ).fetchall()
        out: dict[str, list[str]] = {}
        seen: set[str] = set()
        for to_id, v in rows:
            if not v or to_id in seen:
                continue
            seen.add(to_id)
            out.setdefault(v, []).append(to_id)
        return out

    def resolve_school_ids(self, text: str, *, limit: int = 5) -> list[str]:
        """Best-effort school resolution by id/name substring (production uses the
        canonical alias index; this is the VM-validation fallback)."""
        toks = [t for t in text.lower().split() if len(t) > 3]
        if not toks:
            return []
        clauses = " OR ".join(["lower(id) LIKE ? OR lower(properties_json) LIKE ?"] * len(toks))
        params: list = []
        for t in toks:
            params += [f"%{t}%", f"%{t}%"]
        return [r[0] for r in self.con.execute(
            f"SELECT id FROM nodes WHERE label='School' AND ({clauses}) LIMIT {int(limit)}",
            params,
        ).fetchall()]


def graph_anchored_recall(
    reader: ParquetGraphReader,
    school_id: str,
    *,
    post_cap: int = 3000,
    member_cap: int = 8000,
) -> GraphCandidates:
    """Recover SDN evidence + focus nodes structurally linked to `school_id`.

    Counts are exact (honest census); id lists are capped for downstream filtering,
    with truncation flagged (no silent caps). Reddit evidence is NOT here — it comes
    from the text recall sources (see module docstring).
    """
    res = GraphCandidates(school_id=school_id)
    ids = reader.same_as_closure(school_id)
    res.same_as_ids = ids

    # SDN posts that name the school (across the SAME_AS closure).
    mentioning = reader.from_ids_for_targets(_MENTIONS_SCHOOL, ids)
    res.counts["mentioning_posts"] = len(mentioning)
    res.truncated["mentioning_posts"] = len(mentioning) > post_cap
    res.mentioning_post_ids = mentioning[:post_cap]

    # SDN thread recovery: mentioning posts → their SDNThreads → all member posts.
    threads = reader.to_ids_for_sources(_BELONGS_TO_THREAD, mentioning)
    members = reader.from_ids_for_targets(_BELONGS_TO_THREAD, threads) if threads else []
    res.counts["sdn_threads"] = len(threads)
    res.counts["thread_members"] = len(members)
    res.truncated["thread_members"] = len(members) > member_cap
    res.thread_member_ids = members[:member_cap]

    # Focus / authoritative nodes.
    res.consensus_ids = reader.from_ids_for_targets(_CONSENSUS_FOR, ids)
    res.interview_q_ids = reader.from_ids_for_targets(_ASKED_AT, ids)
    res.l1_claim_ids = reader.l1_claims_for(ids)
    res.counts["forum_consensus"] = len(res.consensus_ids)
    res.counts["interview_questions"] = len(res.interview_q_ids)
    res.counts["l1_claims"] = len(res.l1_claim_ids)

    return res
