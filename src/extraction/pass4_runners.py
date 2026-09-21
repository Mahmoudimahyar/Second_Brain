"""V1 Pass 4 task runners per FR-2.3.

Each runner: utility-filter pre-check → cache lookup → gateway call →
cache write → audit log. Gateway dispatch follows ADR-011 per-task routing.

These are pure functions over a `ModelGateway` + `ExtractionCache` (+ optional
`AuditLog`). Callers wire them into Prefect flows or one-shot CLI invocations.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ValidationError

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_schemas import (
    CONFLICT_CANDIDATE_PROMPT,
    CONFLICT_CANDIDATE_PROMPT_VERSION,
    INTERVIEW_Q_PROMPT,
    INTERVIEW_Q_PROMPT_VERSION,
    SENTIMENT_PROMPT,
    SENTIMENT_PROMPT_VERSION,
    ConflictCandidate,
    InterviewQuestionHarvest,
    Sentiment,
    schema_hash,
)
from src.gateway import strip_json_fences
from src.gateway.api import ModelGateway, TaskID
from src.observability import AuditLog


@dataclass(frozen=True)
class TaskOutcome:
    """Return shape for every Pass 4 runner."""

    parsed: BaseModel | None
    cache_hit: bool
    cost_usd: float
    latency_ms: float
    vendor: str | None
    model: str | None
    error: str | None = None


def _run_task[S: BaseModel](
    *,
    schema: type[S],
    prompt_template: str,
    prompt_version: str,
    task_id: TaskID,
    post_text: str,
    gateway: ModelGateway,
    cache: ExtractionCache,
    audit: AuditLog | None,
) -> TaskOutcome:
    """Shared cache-aware runner. Returns a TaskOutcome with the parsed schema."""

    if not post_text.strip():
        return TaskOutcome(
            parsed=None, cache_hit=False, cost_usd=0.0,
            latency_ms=0.0, vendor=None, model=None,
            error="empty input",
        )

    s_hash = schema_hash(schema)
    cache_key = ExtractionCache.make_key(
        thread_content=post_text,
        prompt_id=task_id.value,
        prompt_version=prompt_version,
        schema_hash=s_hash,
        model_id=task_id.value,        # routing decides actual model; ID is task-scoped
        model_version="auto",
    )

    cached = cache.get(cache_key)
    if cached is not None:
        try:
            parsed = schema.model_validate(
                json.loads(strip_json_fences(cached.output_json)),
            )
        except (json.JSONDecodeError, ValidationError):
            parsed = None
        if audit is not None:
            audit.log_extraction(
                thread_content_hash=cache_key, prompt_template_id=task_id.value,
                prompt_version=prompt_version, schema_hash=s_hash,
                model=cached.model, model_version=cached.model_version,
                cache_hit=True, cache_key=cache_key,
                ttl_pinned=3600,
                input_tokens=0, output_tokens=0,
                cached_input_tokens=cached.cached_input_tokens,
                cost_usd=0.0, latency_ms=0.0,
            )
        return TaskOutcome(
            parsed=parsed, cache_hit=True, cost_usd=0.0,
            latency_ms=0.0, vendor=cached.vendor, model=cached.model,
        )

    start = time.perf_counter()
    prompt = prompt_template % post_text
    try:
        resp = gateway.complete(task_id, prompt, schema=schema, cache_key=cache_key)
    except (RuntimeError, ValidationError) as e:
        return TaskOutcome(
            parsed=None, cache_hit=False, cost_usd=0.0,
            latency_ms=(time.perf_counter() - start) * 1000,
            vendor=None, model=None, error=str(e),
        )

    parsed = cast("S | None", resp.output) if isinstance(resp.output, schema) else None
    raw_for_cache = (
        parsed.model_dump_json() if parsed is not None
        else strip_json_fences(resp.raw_text)
    )
    cache.put_output(
        cache_key, raw_for_cache,
        vendor=resp.vendor, model=resp.model, model_version=resp.model,
        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
        cost_usd=resp.cost_usd,
    )
    if audit is not None:
        audit.log_extraction(
            thread_content_hash=cache_key, prompt_template_id=task_id.value,
            prompt_version=prompt_version, schema_hash=s_hash,
            model=resp.model, model_version=resp.model,
            cache_hit=False, cache_key=cache_key,
            ttl_pinned=resp.ttl_pinned,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            cached_input_tokens=resp.cached_input_tokens,
            cost_usd=resp.cost_usd, latency_ms=resp.latency_ms,
        )
    return TaskOutcome(
        parsed=parsed,
        cache_hit=False,
        cost_usd=resp.cost_usd,
        latency_ms=resp.latency_ms,
        vendor=resp.vendor,
        model=resp.model,
    )


def extract_sentiment(
    post_text: str,
    *,
    gateway: ModelGateway,
    cache: ExtractionCache,
    audit: AuditLog | None = None,
) -> TaskOutcome:
    return _run_task(
        schema=Sentiment,
        prompt_template=SENTIMENT_PROMPT,
        prompt_version=SENTIMENT_PROMPT_VERSION,
        task_id=TaskID.PASS4_SENTIMENT,
        post_text=post_text,
        gateway=gateway, cache=cache, audit=audit,
    )


def extract_interview_questions(
    post_text: str,
    *,
    gateway: ModelGateway,
    cache: ExtractionCache,
    audit: AuditLog | None = None,
) -> TaskOutcome:
    return _run_task(
        schema=InterviewQuestionHarvest,
        prompt_template=INTERVIEW_Q_PROMPT,
        prompt_version=INTERVIEW_Q_PROMPT_VERSION,
        task_id=TaskID.PASS4_INTERVIEW_Q,
        post_text=post_text,
        gateway=gateway, cache=cache, audit=audit,
    )


def extract_conflict_candidate(
    post_text: str,
    *,
    gateway: ModelGateway,
    cache: ExtractionCache,
    audit: AuditLog | None = None,
) -> TaskOutcome:
    return _run_task(
        schema=ConflictCandidate,
        prompt_template=CONFLICT_CANDIDATE_PROMPT,
        prompt_version=CONFLICT_CANDIDATE_PROMPT_VERSION,
        task_id=TaskID.PASS4_CONFLICT_CANDIDATE,
        post_text=post_text,
        gateway=gateway, cache=cache, audit=audit,
    )


