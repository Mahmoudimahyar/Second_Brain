from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from src.extraction.pass1_structural import StructuralOutput
from src.graph.client import Edge, Node
from src.ingestion.adapters.l5_reddit import L5RedditResult
from src.ingestion.adapters.l5_sdn import L5SDNResult
from src.shared.timestamps import to_iso

_TOPIC_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class TopicAssignment:
    """One (post, topic) link emitted by Pass 2."""

    post_id: str
    topic_id: str
    topic_label: str
    source: str  # "reddit_flair" / "sdn_category"


class Pass2LabelsBuilder:
    """Pass 2 — $0 cheap labels per `plan.md` (A-065).

    Promotes Reddit `link_flair_text` and SDN `category` to `Topic` nodes
    and emits `REFERENCES_TOPIC` edges from posts that carry them. Null-safe
    for older Reddit dumps lacking flair (GAP-037).

    Pure: returns a `StructuralOutput` (nodes + edges) for the caller to write.
    """

    def build_reddit(
        self, result: L5RedditResult, *, ingest_time: datetime,
    ) -> StructuralOutput:
        topics: dict[str, Node] = {}
        edges: list[Edge] = []
        ingest_iso = to_iso(ingest_time)

        for post in result.posts:
            flair = (post.link_flair_text or "").strip()
            if not flair:
                continue
            topic_id, topic_node = _topic_node(
                flair, source="reddit_flair", ingest_iso=ingest_iso,
            )
            topics.setdefault(topic_id, topic_node)
            edges.append(_topic_edge(
                post_id=post.post_id, topic_id=topic_id,
                t_valid_from=post.created_utc, t_ingest_from=ingest_time,
                references=[post.post_id, f"flair:{flair}"],
            ))

        return StructuralOutput(nodes=list(topics.values()), edges=edges)

    def build_sdn(
        self, result: L5SDNResult, *, ingest_time: datetime,
    ) -> StructuralOutput:
        topics: dict[str, Node] = {}
        edges: list[Edge] = []
        ingest_iso = to_iso(ingest_time)

        for post in result.posts:
            category = (post.category or "").strip()
            if not category:
                continue
            topic_id, topic_node = _topic_node(
                category, source="sdn_category", ingest_iso=ingest_iso,
            )
            topics.setdefault(topic_id, topic_node)
            edges.append(_topic_edge(
                post_id=post.post_id, topic_id=topic_id,
                t_valid_from=post.created_utc, t_ingest_from=ingest_time,
                references=[post.post_id, f"category:{category}"],
            ))

        return StructuralOutput(nodes=list(topics.values()), edges=edges)


def _topic_node(label: str, *, source: str, ingest_iso: str) -> tuple[str, Node]:
    slug = _TOPIC_SLUG_RE.sub("_", label.lower()).strip("_") or "_"
    topic_id = f"topic:{slug}"
    return topic_id, Node(
        id=topic_id, label="Topic", source_tier="L5",
        properties={"label": label, "source": source, "ingest_iso": ingest_iso},
    )


def _topic_edge(
    *, post_id: str, topic_id: str,
    t_valid_from: datetime, t_ingest_from: datetime,
    references: list[str],
) -> Edge:
    return Edge(
        id=f"edge:references_topic:{post_id}:{topic_id}",
        label="REFERENCES_TOPIC",
        from_id=post_id, to_id=topic_id,
        source_tier="L5", rank="normal",
        references=references,
        t_valid_from=t_valid_from, t_ingest_from=t_ingest_from,
    )
