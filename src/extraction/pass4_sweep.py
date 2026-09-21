"""Pass 4 sweep orchestrator per FR-2.

Composes the utility filter → cache → gateway → audit chain over a stream of
(post_id, post_text) inputs and assembles graph-ready Node + Edge outputs:

  - `Sentiment`           → attached as properties on the source Post (no new
                            node — sentiment is a per-post annotation).
  - `InterviewQuestion`   → one node per harvested question, plus a
                            REPORTED_AT edge to the source Post.
  - `ConflictCandidate`   → one Claim node + MENTIONS_METRIC edge. The
                            ConflictResolver (Phase 6) then runs over these
                            candidate Claims vs L1 Metric values.

The sweep is intentionally caller-driven (no global iteration over the graph):
the Prefect flow or CLI command decides which posts to sample.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_runners import (
    TaskOutcome,
    extract_conflict_candidate,
    extract_interview_questions,
    extract_sentiment,
)
from src.extraction.pass4_schemas import (
    ConflictCandidate,
    InterviewQuestionHarvest,
    Sentiment,
)
from src.extraction.utility_filter import FilterContext, FilterDecision, filter_post
from src.gateway.api import ModelGateway
from src.graph.client import Edge, Node
from src.observability import AuditLog
from src.shared.timestamps import to_iso

Pass4TaskName = Literal["sentiment", "interview_q", "conflict_candidate"]


@dataclass(frozen=True)
class Pass4Input:
    """One post fed into the sweep."""

    post_id: str
    text: str
    author: str | None = None
    is_reply: bool = False
    created_utc: datetime | None = None
    mentions_entity: bool = False    # populated by Pass 1 mention_extractor


@dataclass(frozen=True)
class Pass4Result:
    post_id: str
    filter_decision: FilterDecision
    sentiment: TaskOutcome | None = None
    interview_q: TaskOutcome | None = None
    conflict_candidate: TaskOutcome | None = None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return sum(
            (o.cost_usd or 0.0)
            for o in (self.sentiment, self.interview_q, self.conflict_candidate)
            if o is not None
        )

    @property
    def any_cache_hit(self) -> bool:
        return any(
            o.cache_hit for o in
            (self.sentiment, self.interview_q, self.conflict_candidate)
            if o is not None
        )


@dataclass(frozen=True)
class Pass4Summary:
    """Aggregate stats over a sweep — useful for CLI / Prefect reports."""

    total_inputs: int
    filtered_out: int
    processed: int
    cache_hits: int
    total_cost_usd: float
    sentiment_count: int = 0
    interview_q_count: int = 0
    conflict_candidate_count: int = 0


def run_pass4_sweep(
    inputs: Iterable[Pass4Input],
    *,
    tasks: tuple[Pass4TaskName, ...],
    gateway: ModelGateway,
    cache: ExtractionCache,
    audit: AuditLog | None = None,
    ingest_time: datetime | None = None,
) -> Iterator[Pass4Result]:
    """Lazily yield one `Pass4Result` per input.

    Caller is responsible for writing the emitted nodes + edges to the graph.
    """

    ingest_iso = to_iso(ingest_time) if ingest_time else None
    for inp in inputs:
        ctx = FilterContext(
            text=inp.text, author=inp.author, is_reply=inp.is_reply,
            mentions_entity=inp.mentions_entity,
        )
        decision = filter_post(ctx)
        if not decision.keep:
            yield Pass4Result(post_id=inp.post_id, filter_decision=decision)
            continue

        sentiment_out: TaskOutcome | None = None
        interview_q_out: TaskOutcome | None = None
        conflict_out: TaskOutcome | None = None

        if "sentiment" in tasks:
            sentiment_out = extract_sentiment(
                inp.text, gateway=gateway, cache=cache, audit=audit,
            )
        if "interview_q" in tasks:
            interview_q_out = extract_interview_questions(
                inp.text, gateway=gateway, cache=cache, audit=audit,
            )
        if "conflict_candidate" in tasks:
            conflict_out = extract_conflict_candidate(
                inp.text, gateway=gateway, cache=cache, audit=audit,
            )

        nodes, edges = _emit_graph_artifacts(
            inp=inp,
            sentiment_out=sentiment_out,
            interview_q_out=interview_q_out,
            conflict_out=conflict_out,
            ingest_iso=ingest_iso,
        )
        yield Pass4Result(
            post_id=inp.post_id,
            filter_decision=decision,
            sentiment=sentiment_out,
            interview_q=interview_q_out,
            conflict_candidate=conflict_out,
            nodes=nodes,
            edges=edges,
        )


def summarize(results: Iterable[Pass4Result]) -> Pass4Summary:
    total = filtered = processed = hits = 0
    cost = 0.0
    sentiment = interview_q = conflict = 0
    for r in results:
        total += 1
        if not r.filter_decision.keep:
            filtered += 1
            continue
        processed += 1
        if r.any_cache_hit:
            hits += 1
        cost += r.total_cost_usd
        if r.sentiment and r.sentiment.parsed is not None:
            sentiment += 1
        if r.interview_q and r.interview_q.parsed is not None:
            interview_q += 1
        if r.conflict_candidate and r.conflict_candidate.parsed is not None:
            conflict += 1
    return Pass4Summary(
        total_inputs=total, filtered_out=filtered, processed=processed,
        cache_hits=hits, total_cost_usd=cost,
        sentiment_count=sentiment, interview_q_count=interview_q,
        conflict_candidate_count=conflict,
    )


def _emit_graph_artifacts(
    *,
    inp: Pass4Input,
    sentiment_out: TaskOutcome | None,
    interview_q_out: TaskOutcome | None,
    conflict_out: TaskOutcome | None,
    ingest_iso: str | None,
) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    t_valid = inp.created_utc or datetime.now(tz=datetime.now().astimezone().tzinfo)
    t_ingest = t_valid

    if sentiment_out is not None and isinstance(sentiment_out.parsed, Sentiment):
        s = sentiment_out.parsed
        nodes.append(Node(
            id=f"sentiment:{inp.post_id}",
            label="SentimentAnnotation",
            source_tier="L5",
            properties={
                "post_id": inp.post_id, "verdict": s.verdict,
                "confidence": s.confidence,
                "target_entities": list(s.target_entities),
                "reasoning": s.reasoning,
                "vendor": sentiment_out.vendor,
                "model": sentiment_out.model,
                "ingest_iso": ingest_iso,
            },
        ))
        edges.append(Edge(
            id=f"edge:annotates:{inp.post_id}",
            label="ANNOTATES",
            from_id=f"sentiment:{inp.post_id}", to_id=inp.post_id,
            source_tier="L5", rank="normal",
            references=[inp.post_id],
            t_valid_from=t_valid, t_ingest_from=t_ingest,
            confidence=s.confidence,
        ))

    if interview_q_out is not None and isinstance(
        interview_q_out.parsed, InterviewQuestionHarvest,
    ):
        for i, q in enumerate(interview_q_out.parsed.questions):
            q_id = f"iq:{_qid(inp.post_id, i, q.text)}"
            nodes.append(Node(
                id=q_id, label="InterviewQuestion", source_tier="L5",
                properties={
                    "text": q.text, "school_mention": q.school_mention,
                    "year": q.year, "advice_given": q.advice_given,
                    "source_post_id": inp.post_id,
                    "vendor": interview_q_out.vendor,
                    "model": interview_q_out.model,
                    "ingest_iso": ingest_iso,
                },
            ))
            edges.append(Edge(
                id=f"edge:reported_at:{q_id}",
                label="REPORTED_AT",
                from_id=q_id, to_id=inp.post_id,
                source_tier="L5", rank="normal",
                references=[inp.post_id],
                t_valid_from=t_valid, t_ingest_from=t_ingest,
                confidence=interview_q_out.parsed.confidence,
            ))

    if conflict_out is not None and isinstance(
        conflict_out.parsed, ConflictCandidate,
    ) and conflict_out.parsed.contains_candidate:
        c = conflict_out.parsed
        c_id = f"claim:{_qid(inp.post_id, 0, str(c.claim_predicate))}"
        nodes.append(Node(
            id=c_id, label="Claim", source_tier="L5",
            properties={
                "subject": c.claim_subject, "predicate": c.claim_predicate,
                "value": c.claim_value, "cycle_year": c.cycle_year,
                "confidence": c.confidence,
                "source_post_id": inp.post_id,
                "vendor": conflict_out.vendor, "model": conflict_out.model,
                "ingest_iso": ingest_iso,
            },
        ))
        edges.append(Edge(
            id=f"edge:extracted_from:{c_id}",
            label="EXTRACTED_FROM",
            from_id=c_id, to_id=inp.post_id,
            source_tier="L5", rank="normal",
            references=[inp.post_id],
            t_valid_from=t_valid, t_ingest_from=t_ingest,
            confidence=c.confidence,
        ))

    return nodes, edges


def _qid(post_id: str, idx: int, suffix: str) -> str:
    h = sha256()
    h.update(post_id.encode("utf-8"))
    h.update(f"|{idx}|".encode())
    h.update((suffix or "").encode("utf-8"))
    return h.hexdigest()[:16]
