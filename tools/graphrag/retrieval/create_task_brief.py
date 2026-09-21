"""`create_task_brief(goal)` — compose a Markdown brief from `plan_change` output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.graphrag.retrieval.plan_change import plan_change
from tools.graphrag.store.sqlite_client import SQLiteGraphClient


@dataclass(frozen=True)
class TaskBrief:
    task_id: str
    brief_markdown: str
    saved_to: str | None
    selected_features: list[str]
    estimated_files_touched: list[str]


def _slugify(goal: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s\-]+", "", goal).strip().lower()
    s = re.sub(r"\s+", "-", s)[:60]
    return s or "task"


def create_task_brief(
    store: SQLiteGraphClient,
    goal: str,
    *,
    save_path: Path | None = None,
) -> TaskBrief:
    plan = plan_change(store, goal, k_features=2)
    task_id = _slugify(goal)

    lines: list[str] = []
    lines.append(f"# Task: {goal}\n")
    lines.append("## Goal\n")
    lines.append(goal + "\n")

    lines.append("\n## Relevant features\n")
    files_touched: list[str] = []
    for f in plan.selected_features:
        lines.append(f"### {f.slug} — {f.name}\n")
        lines.append(f"- relevance: {f.relevance_score:.2f}\n")
        if f.summary:
            lines.append(f"- summary: {f.summary[:200]}\n")
        if f.code_files:
            lines.append("- code files: " + ", ".join(f"`{p}`" for p in f.code_files) + "\n")
            files_touched.extend(f.code_files)
        if f.tests_to_run:
            lines.append("- tests to run: " + ", ".join(f.tests_to_run[:10]) + "\n")
        if f.risks:
            lines.append("- risks:\n")
            for r in f.risks[:5]:
                lines.append(f"  - {r}\n")
        lines.append("\n")

    lines.append("## Suggested order\n")
    for i, slug in enumerate(plan.suggested_implementation_order, start=1):
        lines.append(f"{i}. {slug}\n")

    brief = "".join(lines)
    saved_to: str | None = None
    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(brief, encoding="utf-8")
        saved_to = str(save_path)

    return TaskBrief(
        task_id=task_id,
        brief_markdown=brief,
        saved_to=saved_to,
        selected_features=[f.slug for f in plan.selected_features],
        estimated_files_touched=files_touched,
    )
