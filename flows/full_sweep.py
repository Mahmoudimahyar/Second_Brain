"""One-shot composed flow: all 5 passes against the configured data.

Use the per-pass flow files individually for scheduled daily / weekly runs.
This file is the operator-invoked "do everything now" entry-point.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow

from flows.pass1_structural import pass1_structural_incremental
from flows.pass2_labels import pass2_labels_incremental
from flows.pass3_clustering import pass3_clustering_weekly
from flows.pass4_llm import pass4_llm_daily
from flows.pass5_indexing import pass5_indexing_refresh


@flow(name="full-sweep")
def full_sweep(
    *,
    data_dir: Path,
    l1_excel_paths: list[Path],
    reddit_posts: Path,
    reddit_comments: Path | None = None,
) -> dict[str, dict[str, float | int]]:
    pass1 = pass1_structural_incremental(
        l1_excel_paths=l1_excel_paths,
        reddit_posts=reddit_posts, reddit_comments=reddit_comments,
        data_dir=data_dir,
    )
    pass2 = pass2_labels_incremental(
        reddit_posts=reddit_posts, reddit_comments=reddit_comments,
        data_dir=data_dir,
    )
    pass3 = pass3_clustering_weekly(data_dir=data_dir)
    pass4 = pass4_llm_daily(data_dir=data_dir)
    pass5 = pass5_indexing_refresh(data_dir=data_dir)
    return {
        "pass1": dict(pass1),  # type: ignore[arg-type]
        "pass2": dict(pass2),  # type: ignore[arg-type]
        "pass3": dict(pass3),  # type: ignore[arg-type]
        "pass4": dict(pass4),  # type: ignore[arg-type]
        "pass5": dict(pass5),  # type: ignore[arg-type]
    }
