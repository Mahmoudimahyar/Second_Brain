from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.graph.client import Edge, Node
from src.ingestion.adapters.l1_excel import L1Alias, L1IngestResult
from src.ingestion.adapters.l1_pdf import L1PDFResult
from src.ingestion.adapters.l2_html import L2IngestResult
from src.ingestion.adapters.l5_reddit import L5RedditResult
from src.ingestion.adapters.l5_sdn import L5SDNResult
from src.shared.timestamps import to_iso


@dataclass(frozen=True)
class HITLEnqueueItem:
    """A borderline match (FR-3.2: 0.75 ≤ score < 0.90) for HITL review."""

    item_type: str            # "alias_match" / "conflict" / etc.
    payload: dict[str, Any]


@dataclass(frozen=True)
class StructuralOutput:
    nodes: list[Node]
    edges: list[Edge]
    hitl_items: list[HITLEnqueueItem] = field(default_factory=list)


class Pass1StructuralBuilder:
    """Pass 1 — $0 deterministic graph assembly per `plan.md`.

    Converts canonical records from the L1/L5 adapters into `Node` + `Edge`
    instances ready for `GraphClient.upsert_*`. Emits the canonical structural
    edge set per `data.md`:
        L5: AUTHORED, REPLIED_TO, BELONGS_TO_THREAD, POSTED_IN_FORUM
        L1: SCHOOL_HAS_METRIC, HAS_ALIAS

    No mutation of the graph happens here — that is the caller's responsibility
    (Prefect flow in `flows/pass1_structural.py`). Keeping the builder pure
    makes idempotency, batching, and testing trivial.
    """

    def assemble_reddit(
        self,
        result: L5RedditResult,
        *,
        ingest_time: datetime,
        mention_extractor: Pass1MentionExtractor | None = None,
    ) -> StructuralOutput:
        hitl_items: list[HITLEnqueueItem] = []
        nodes: list[Node] = []
        edges: list[Edge] = []
        ingest_iso = to_iso(ingest_time)

        subreddit_id = f"subreddit:{result.subreddit}"
        nodes.append(Node(
            id=subreddit_id, label="Subreddit", source_tier="L5",
            properties={"name": result.subreddit},
        ))

        for u in result.users:
            nodes.append(Node(
                id=u.user_id, label="User", source_tier="L5",
                properties={
                    "username": u.username, "subreddit": u.subreddit,
                    "first_seen_utc": to_iso(u.first_seen_utc),
                },
            ))

        for p in result.posts:
            nodes.append(Node(
                id=p.post_id, label="Post", source_tier="L5",
                properties={
                    "title": p.title, "selftext": p.selftext,
                    "created_utc": to_iso(p.created_utc),
                    "score": p.score, "ups": p.ups, "downs": p.downs,
                    "num_comments": p.num_comments,
                    "link_flair_text": p.link_flair_text,
                    "subreddit": p.subreddit, "url": p.url,
                    "permalink": p.permalink, "over_18": p.over_18,
                    "ingest_iso": ingest_iso,
                },
            ))
            edges.append(_make_edge(
                edge_id=f"edge:posted_in:{p.post_id}",
                label="POSTED_IN_FORUM",
                from_id=p.post_id, to_id=subreddit_id,
                references=[p.post_id],
                t_valid_from=p.created_utc, t_ingest_from=ingest_time,
            ))
            if p.author_user_id is not None:
                edges.append(_make_edge(
                    edge_id=f"edge:authored:{p.author_user_id}:{p.post_id}",
                    label="AUTHORED",
                    from_id=p.author_user_id, to_id=p.post_id,
                    references=[p.post_id],
                    t_valid_from=p.created_utc, t_ingest_from=ingest_time,
                ))
            if mention_extractor is not None:
                m_edges, m_hitl = _mention_edges_and_hitl(
                    extractor=mention_extractor,
                    text=f"{p.title}\n{p.selftext}",
                    from_id=p.post_id,
                    t_valid_from=p.created_utc,
                    t_ingest_from=ingest_time,
                )
                edges.extend(m_edges)
                hitl_items.extend(m_hitl)

        for c in result.comments:
            nodes.append(Node(
                id=c.comment_id, label="Comment", source_tier="L5",
                properties={
                    "body": c.body, "created_utc": to_iso(c.created_utc),
                    "score": c.score, "ups": c.ups, "downs": c.downs,
                    "controversiality": c.controversiality,
                    "subreddit": c.subreddit,
                    "ingest_iso": ingest_iso,
                },
            ))
            edges.append(_make_edge(
                edge_id=f"edge:replied_to:{c.comment_id}",
                label="REPLIED_TO",
                from_id=c.comment_id, to_id=c.parent_id,
                references=[c.comment_id],
                t_valid_from=c.created_utc, t_ingest_from=ingest_time,
            ))
            edges.append(_make_edge(
                edge_id=f"edge:belongs_to:{c.comment_id}",
                label="BELONGS_TO_THREAD",
                from_id=c.comment_id, to_id=c.post_id,
                references=[c.comment_id],
                t_valid_from=c.created_utc, t_ingest_from=ingest_time,
            ))
            if c.author_user_id is not None:
                edges.append(_make_edge(
                    edge_id=f"edge:authored:{c.author_user_id}:{c.comment_id}",
                    label="AUTHORED",
                    from_id=c.author_user_id, to_id=c.comment_id,
                    references=[c.comment_id],
                    t_valid_from=c.created_utc, t_ingest_from=ingest_time,
                ))
            if mention_extractor is not None and c.body:
                m_edges, m_hitl = _mention_edges_and_hitl(
                    extractor=mention_extractor,
                    text=c.body,
                    from_id=c.comment_id,
                    t_valid_from=c.created_utc,
                    t_ingest_from=ingest_time,
                )
                edges.extend(m_edges)
                hitl_items.extend(m_hitl)

        return StructuralOutput(nodes=nodes, edges=edges, hitl_items=hitl_items)

    def assemble_sdn(
        self,
        result: L5SDNResult,
        *,
        ingest_time: datetime,
        mention_extractor: Pass1MentionExtractor | None = None,
    ) -> StructuralOutput:
        hitl_items: list[HITLEnqueueItem] = []
        nodes: list[Node] = []
        edges: list[Edge] = []
        ingest_iso = to_iso(ingest_time)

        # Categories deduped across threads.
        seen_categories: set[str] = set()
        for t in result.threads:
            category_id = f"sdn_category:{t.category}"
            if t.category and category_id not in seen_categories:
                nodes.append(Node(
                    id=category_id, label="SDNCategory", source_tier="L5",
                    properties={"name": t.category},
                ))
                seen_categories.add(category_id)
            nodes.append(Node(
                id=t.thread_id, label="SDNThread", source_tier="L5",
                properties={
                    "title": t.title, "category": t.category, "url": t.url,
                    "reply_count": t.reply_count, "view_count": t.view_count,
                    "root_post_id": t.root_post_id,
                },
            ))

        for u in result.users:
            nodes.append(Node(
                id=u.user_id, label="User", source_tier="L5",
                properties={
                    "username": u.username,
                    "first_seen_utc": to_iso(u.first_seen_utc),
                },
            ))

        # Build a map for thread lookups.
        thread_by_id = {t.thread_id: t for t in result.threads}

        for p in result.posts:
            thread = thread_by_id.get(p.thread_id)
            nodes.append(Node(
                id=p.post_id, label="Post", source_tier="L5",
                properties={
                    "body": p.body, "created_utc": to_iso(p.created_utc),
                    "category": p.category, "thread_title": p.thread_title,
                    "thread_url": p.thread_url,
                    "page_number": p.page_number,
                    "is_thread_root": p.is_thread_root,
                    "source": "sdn",
                    "ingest_iso": ingest_iso,
                },
            ))
            edges.append(_make_edge(
                edge_id=f"edge:belongs_to:{p.post_id}",
                label="BELONGS_TO_THREAD",
                from_id=p.post_id, to_id=p.thread_id,
                references=[p.post_id],
                t_valid_from=p.created_utc, t_ingest_from=ingest_time,
            ))
            if thread is not None and p.category:
                category_id = f"sdn_category:{p.category}"
                edges.append(_make_edge(
                    edge_id=f"edge:posted_in:{p.post_id}",
                    label="POSTED_IN_FORUM",
                    from_id=p.post_id, to_id=category_id,
                    references=[p.post_id],
                    t_valid_from=p.created_utc, t_ingest_from=ingest_time,
                ))
            # REPLIED_TO from non-root posts to root post.
            if not p.is_thread_root and thread is not None and thread.root_post_id:
                edges.append(_make_edge(
                    edge_id=f"edge:replied_to:{p.post_id}",
                    label="REPLIED_TO",
                    from_id=p.post_id, to_id=thread.root_post_id,
                    references=[p.post_id],
                    t_valid_from=p.created_utc, t_ingest_from=ingest_time,
                ))
            if p.author_user_id is not None:
                edges.append(_make_edge(
                    edge_id=f"edge:authored:{p.author_user_id}:{p.post_id}",
                    label="AUTHORED",
                    from_id=p.author_user_id, to_id=p.post_id,
                    references=[p.post_id],
                    t_valid_from=p.created_utc, t_ingest_from=ingest_time,
                ))
            if mention_extractor is not None and p.body:
                m_edges, m_hitl = _mention_edges_and_hitl(
                    extractor=mention_extractor,
                    text=f"{p.thread_title}\n{p.body}",
                    from_id=p.post_id,
                    t_valid_from=p.created_utc,
                    t_ingest_from=ingest_time,
                )
                edges.extend(m_edges)
                hitl_items.extend(m_hitl)

        return StructuralOutput(nodes=nodes, edges=edges, hitl_items=hitl_items)

    def assemble_l1(
        self, result: L1IngestResult, *, source_dump_id: str, ingest_time: datetime,
    ) -> StructuralOutput:
        nodes: list[Node] = []
        edges: list[Edge] = []

        for s in result.schools:
            nodes.append(Node(
                id=s.canonical_id, label="School", source_tier="L1",
                properties={
                    "canonical_name": s.canonical_name,
                    "city": s.city, "state": s.state, "country": "US",
                    "source_dump_id": source_dump_id,
                },
            ))

        cycle_node_id = f"cycle:{result.cycle_year}"
        nodes.append(Node(
            id=cycle_node_id, label="CycleYear", source_tier="L1",
            properties={"cycle": result.cycle_year},
        ))

        for m in result.metrics:
            nodes.append(Node(
                id=m.metric_id, label="Metric", source_tier="L1",
                properties={
                    "metric_name": m.metric_name,
                    "metric_value": m.metric_value,
                    "cycle_year": m.cycle_year, "unit": m.unit,
                    "source_row": m.source_row,
                    "source_dump_id": source_dump_id,
                },
            ))
            edges.append(_make_edge(
                edge_id=f"edge:school_has_metric:{m.canonical_school_id}:{m.metric_id}",
                label="SCHOOL_HAS_METRIC",
                from_id=m.canonical_school_id, to_id=m.metric_id,
                references=[source_dump_id, m.source_row],
                rank="preferred",
                qualifiers={"cycle": m.cycle_year},
                t_valid_from=m.t_valid_from, t_valid_to=m.t_valid_to,
                t_ingest_from=ingest_time,
                source_tier="L1",
            ))

        for a in result.aliases:
            edges.append(_alias_edge(a, source_dump_id, ingest_time))

        return StructuralOutput(nodes=nodes, edges=edges)

    def assemble_l1_pdf(
        self,
        result: L1PDFResult,
        *,
        source_dump_id: str,
        ingest_time: datetime,
    ) -> StructuralOutput:
        """Emit L1Document nodes (one per page) + PROVENANCE edges.

        SDE4 (Curriculum) is narrative survey data, not numeric metrics. Each
        page becomes one L1Document node tagged source_tier=L1, queryable via
        the hybrid retrieval index. Per-school + per-curriculum structured
        extraction is V2.
        """

        nodes: list[Node] = []
        edges: list[Edge] = []
        dump_node_id = f"dump:{source_dump_id.split(':', 1)[-1]}"
        for p in result.pages:
            nodes.append(Node(
                id=p.document_id, label="L1Document", source_tier="L1",
                properties={
                    "source_name": p.source_name,
                    "title": p.title,
                    "page_number": p.page_number,
                    "cycle_year": p.cycle_year,
                    "body": p.body[:4000],          # property cap
                    "raw_path": p.raw_path,
                    "ingested_iso": to_iso(p.ingested_utc),
                    "source_dump_id": source_dump_id,
                },
            ))
            edges.append(Edge(
                id=f"edge:provenance:{p.document_id}",
                label="PROVENANCE",
                from_id=p.document_id, to_id=dump_node_id,
                source_tier="L1", rank="preferred",
                references=[source_dump_id, p.raw_path],
                qualifiers={"page": p.page_number},
                t_valid_from=p.ingested_utc, t_ingest_from=ingest_time,
                confidence=1.0,
            ))
        return StructuralOutput(nodes=nodes, edges=edges)

    def assemble_l2(
        self,
        result: L2IngestResult,
        *,
        source_dump_id: str,
        ingest_time: datetime,
    ) -> StructuralOutput:
        """Emit L2Document nodes + PROVENANCE edges per ADR-005.

        L2 = unstructured truth (official-source articles). Each document
        becomes one node; rank defaults to `preferred` since the source is
        official. Pass 4 conflict-candidate extraction can later mine claims
        from these documents (FR-2 / V1.x).
        """

        nodes: list[Node] = []
        edges: list[Edge] = []
        for d in result.documents:
            nodes.append(Node(
                id=d.document_id, label="L2Document", source_tier="L2",
                properties={
                    "source_name": d.source_name,
                    "title": d.title,
                    "url": d.url,
                    "body": d.body[:4000],   # property cap; full body lives in raw payload
                    "raw_path": d.raw_path,
                    "published_utc": (
                        to_iso(d.published_utc) if d.published_utc else None
                    ),
                    "ingested_iso": to_iso(d.ingested_utc),
                    "source_dump_id": source_dump_id,
                },
            ))
            # Provenance edge from document → dump (so retrieval can walk
            # citations back to the originating dump).
            edges.append(Edge(
                id=f"edge:provenance:{d.document_id}",
                label="PROVENANCE",
                from_id=d.document_id,
                to_id=f"dump:{source_dump_id.split(':', 1)[-1]}",
                source_tier="L2",
                rank="preferred",
                references=[source_dump_id, d.raw_path],
                qualifiers={"url": d.url} if d.url else {},
                t_valid_from=d.published_utc or ingest_time,
                t_ingest_from=ingest_time,
                confidence=1.0,
            ))
        return StructuralOutput(nodes=nodes, edges=edges)


def _make_edge(
    *,
    edge_id: str,
    label: str,
    from_id: str,
    to_id: str,
    references: list[str],
    t_valid_from: datetime,
    t_ingest_from: datetime,
    t_valid_to: datetime | None = None,
    source_tier: str = "L5",
    rank: str = "normal",
    qualifiers: dict[str, object] | None = None,
    confidence: float = 1.0,
) -> Edge:
    return Edge(
        id=edge_id,
        label=label,
        from_id=from_id,
        to_id=to_id,
        source_tier=source_tier,  # type: ignore[arg-type]
        rank=rank,  # type: ignore[arg-type]
        references=references,
        qualifiers=qualifiers or {},
        t_valid_from=t_valid_from,
        t_valid_to=t_valid_to,
        t_ingest_from=t_ingest_from,
        confidence=confidence,
    )


def _alias_edge(
    alias: L1Alias, source_dump_id: str, ingest_time: datetime,
) -> Edge:
    """`School` --HAS_ALIAS--> embedded alias string identifier."""

    alias_node_id = f"alias_node:{alias.canonical_id}:{_slugged(alias.alias_text)}"
    return Edge(
        id=f"edge:has_alias:{alias.canonical_id}:{_slugged(alias.alias_text)}",
        label="HAS_ALIAS",
        from_id=alias.canonical_id,
        to_id=alias_node_id,
        source_tier="L1",
        rank="preferred",
        references=[source_dump_id],
        qualifiers={"alias_text": alias.alias_text, "alias_source": alias.alias_source},
        confidence=alias.confidence,
        t_valid_from=ingest_time,
        t_ingest_from=ingest_time,
    )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _mention_edges_and_hitl(
    *,
    extractor: Pass1MentionExtractor,
    text: str,
    from_id: str,
    t_valid_from: datetime,
    t_ingest_from: datetime,
) -> tuple[list[Edge], list[HITLEnqueueItem]]:
    """Run fuzzy mention extraction; emit MENTIONS_SCHOOL edges + HITL items.

    FR-3.5: each edge carries confidence + bitemporal tuple.
    FR-3.2: borderline scores (`needs_review=True`) produce a HITLEnqueueItem
            that the caller routes to the HITL queue.
    """

    edges: list[Edge] = []
    hitl: list[HITLEnqueueItem] = []
    for m in extractor.extract(text):
        edges.append(Edge(
            id=f"edge:mentions_school:{from_id}:{m.canonical_id}",
            label="MENTIONS_SCHOOL",
            from_id=from_id,
            to_id=m.canonical_id,
            source_tier="L5",
            rank="normal",
            references=[from_id],
            qualifiers={
                "matched_alias": m.matched_alias,
                "needs_review": m.needs_review,
                "score": m.score,
            },
            t_valid_from=t_valid_from,
            t_ingest_from=t_ingest_from,
            confidence=m.score / 100.0,
        ))
        if m.needs_review:
            hitl.append(HITLEnqueueItem(
                item_type="alias_match",
                payload={
                    "post_id": from_id,
                    "canonical_id": m.canonical_id,
                    "canonical_name": m.canonical_name,
                    "matched_alias": m.matched_alias,
                    "score": m.score,
                    "snippet": text[:280],
                },
            ))
    return edges, hitl


def _slugged(text: str) -> str:
    """Best-effort slug for HAS_ALIAS edge IDs."""

    return _SLUG_RE.sub("_", text.lower()).strip("_") or "_"
