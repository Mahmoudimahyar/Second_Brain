"""V1.5a Phase 6 — Prefect 3 flow for per-source delta pulls.

Schedules a daily pull per registered data source. Mode defaults to `delta`
(uses persisted cursor); `--full-resync` (via CLI override) closes the prior
`t_ingest_to` and re-ingests everything.

The flow is thin orchestration over `pull_source` in `src/ingestion/sources/
state.py`. It exists as a separate module so Prefect's flow discovery can
register it and so the per-source schedule (CronSchedule / IntervalSchedule)
is colocated with the flow definition.

Prefect is an optional dep in V1; importing this module without Prefect
installed degrades gracefully (the flow decorator becomes a no-op so the
function still works as a plain Python entry point for the CLI).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Runtime (not TYPE_CHECKING) imports: Prefect introspects the @flow/@task
# signatures via get_type_hints(), so PullMode/DataSource/PullReceipt must be
# resolvable at runtime or flow-param validation fails with a model_rebuild
# error. No import cycle exists (base/state do not import flows).
from src.ingestion.sources.base import DataSource, SourceManifest
from src.ingestion.sources.state import PullMode, PullReceipt

# ----------------------------------------------------------------------
# Optional Prefect import — degrades to a no-op decorator when missing.
# ----------------------------------------------------------------------


try:
    from prefect import flow, task
except ImportError:  # pragma: no cover — Prefect is optional in V1.5
    def flow(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def _wrap(fn: Any) -> Any:
            return fn
        if args and callable(args[0]):
            return _wrap(args[0])
        return _wrap

    def task(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def _wrap(fn: Any) -> Any:
            return fn
        if args and callable(args[0]):
            return _wrap(args[0])
        return _wrap


# ----------------------------------------------------------------------
# Tasks + flow
# ----------------------------------------------------------------------


@task(name="data-source-pull-one")
def pull_one_source_task(
    *,
    data_source: DataSource,
    state_db_path: Path,
    mode: PullMode = "delta",
) -> PullReceipt:
    """Task wrapper around the synchronous `pull_source` function.

    Lazy imports so the Prefect-less degraded-mode path still works.
    """

    from src.ingestion.sources.state import (  # noqa: PLC0415
        DataSourceStateStore,
        pull_source,
    )
    state = DataSourceStateStore(sqlite_path=state_db_path)
    receipt, _records = pull_source(
        data_source=data_source,
        state_store=state,
        mode=mode,
    )
    return receipt


@flow(name="data-source-pull-all")
def data_source_pull_all(
    *,
    sqlite_path: Path,
    mode: PullMode = "delta",
) -> list[PullReceipt]:
    """Pull deltas from every active data source.

    Iterates the `DataSourceRegistry.list_active()` rows, materializes a
    `DataSource` per row via `IngestionService.register_data_source`, then
    runs `pull_one_source_task` against it.

    Disconnected / paused / errored sources are skipped. Errors per source
    are recorded in the `pulls` audit table but do not abort the flow.
    """

    # Lazy imports to keep this module Prefect-optional.
    from src.ingestion.api import IngestionService  # noqa: PLC0415
    from src.ingestion.sources.registry import (  # noqa: PLC0415
        DataSourceRegistry,
    )

    registry = DataSourceRegistry(sqlite_path=sqlite_path)
    service = IngestionService(
        dumps_root=sqlite_path.parent / "dumps",
        sqlite_path=sqlite_path,
    )
    receipts: list[PullReceipt] = []
    for row in registry.list_active():
        manifest = _row_to_manifest(row)
        if manifest is None:
            continue
        ds = service.register_data_source(
            manifest,
            actor="prefect",
        )
        receipts.append(
            pull_one_source_task(
                data_source=ds,
                state_db_path=sqlite_path,
                mode=mode,
            ),
        )
    return receipts


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _row_to_manifest(row: Any) -> SourceManifest | None:
    """Rebuild a `SourceManifest` from a `DataSourceRow`."""

    import json  # noqa: PLC0415

    from src.ingestion.sources.base import (  # noqa: PLC0415
        LocalFileConfig,
        MySQLConfig,
        Neo4jConfig,
        PostgresConfig,
        SourceManifest,
        SQLiteConfig,
    )
    try:
        config_data = json.loads(row.config_json)
    except (json.JSONDecodeError, TypeError):
        return None
    engine = row.engine
    if engine == "local_file":
        config: Any = LocalFileConfig.model_validate(config_data)
    elif engine == "postgres":
        config = PostgresConfig.model_validate(config_data)
    elif engine == "mysql":
        config = MySQLConfig.model_validate(config_data)
    elif engine == "sqlite":
        config = SQLiteConfig.model_validate(config_data)
    elif engine == "neo4j":
        config = Neo4jConfig.model_validate(config_data)
    else:
        return None
    return SourceManifest(
        source_id=row.source_id,
        engine=engine,
        display_name=row.display_name,
        config=config,
        tier=row.tier,
        credential_ref=row.credential_ref,
        notes=row.notes,
    )


__all__ = ["data_source_pull_all", "pull_one_source_task"]
