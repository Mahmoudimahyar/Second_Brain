from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from src.er.alias_expansion import expand_aliases
from src.shared.ids import slugify
from src.shared.timestamps import to_iso, utc_now

SCHOOL_ALIASES: frozenset[str] = frozenset({
    "school", "dental school", "institution", "name", "school name",
})
# Substrings (case-insensitive) that identify a school column when no exact
# SCHOOL_ALIASES match exists. SDE1 (Report 1) uses headers like "United
# States, CODA-accredited Dental Schools" which doesn't exact-match but
# contains "dental schools". Keep this list tight so it doesn't false-positive
# on metric headers that happen to mention schools.
SCHOOL_HEADER_SUBSTRINGS: tuple[str, ...] = (
    "dental schools", "dental-schools", "coda-accredited dental",
    "dental school 1", "dental school 2", "dental school 3",
    "dental school (",                       # "Dental School (Random Code)" — anonymized
)
STATE_ALIASES: frozenset[str] = frozenset({"state", "st", "state / province", "state/province"})
STATE_HEADER_SUBSTRINGS: tuple[str, ...] = (
    "state /", "state/", "state / country", "country / province",
)
CITY_ALIASES: frozenset[str] = frozenset({"city"})
NON_METRIC_HEADERS: frozenset[str] = (
    SCHOOL_ALIASES
    | STATE_ALIASES
    | CITY_ALIASES
    | frozenset({"type", "type of institutional support", "country", "region"})
)
SKIP_SHEET_NAMES: frozenset[str] = frozenset({"TOC", "Notes", "Glossary"})

_CYCLE_RE = re.compile(r"(20\d{2})[\-_](\d{2})")
_SUMMARY_LABELS = frozenset({"total", "average", "mean", "sum", "all schools"})
# Footnote markers ADEA Excel files append to school names — trailing digit,
# asterisk, or footnote glyph. Strip before slugify to dedupe canonical_ids
# across sheets / files (GAP-045 cont'd).
_FOOTNOTE_SUFFIX_RE = re.compile(r"[\s\d*†‡]+$")


@dataclass(frozen=True)
class L1School:
    canonical_id: str
    canonical_name: str
    city: str | None
    state: str | None
    source_row: str


@dataclass(frozen=True)
class L1SchoolYearMetric:
    metric_id: str
    canonical_school_id: str
    cycle_year: str
    metric_name: str
    metric_value: float | None
    unit: str | None
    source_row: str
    t_valid_from: datetime
    t_valid_to: datetime


@dataclass(frozen=True)
class L1Alias:
    alias_text: str
    canonical_id: str
    alias_source: str
    confidence: float


@dataclass(frozen=True)
class L1IngestResult:
    cycle_year: str
    schools: list[L1School]
    metrics: list[L1SchoolYearMetric]
    aliases: list[L1Alias]


class L1ExcelAdapter:
    """Adapter for ADEA Report 2 (SDE2) Excel files. Implements FR-1.2.

    Each file covers one cycle year and contains many sheets (TOC, Notes,
    Glossary, Tab1..TabN, Fig*). The adapter iterates data sheets, finds the
    header row that contains a school-identifier column, and extracts
    `L1School` + `L1SchoolYearMetric` + `L1Alias` records. Each sheet's row-1
    title (e.g., "Table 1: United States Dental Schools - Tuition...") is
    captured as the metric-name prefix so metrics from different sheets remain
    distinguishable.

    `persist` writes to SQLite tables defined in `data.md`. Re-running on the
    same data is a no-op for schools/aliases (INSERT OR IGNORE) and replaces
    metric values keyed by `metric_id` (INSERT OR REPLACE).
    """

    source_tier = "L1"

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def parse(self, payload_path: Path) -> L1IngestResult:
        cycle = self._cycle_from_filename(payload_path.name)
        if cycle is None:
            raise ValueError(f"Cannot infer cycle year from filename: {payload_path.name}")

        wb = load_workbook(payload_path, read_only=True, data_only=True)
        schools_by_id: dict[str, L1School] = {}
        metrics_by_id: dict[str, L1SchoolYearMetric] = {}
        aliases_by_id: dict[str, L1Alias] = {}
        try:
            for sheet_name in wb.sheetnames:
                if not _is_data_sheet(sheet_name):
                    continue
                ws = wb[sheet_name]
                self._parse_sheet(
                    ws, cycle,
                    schools_out=schools_by_id,
                    metrics_out=metrics_by_id,
                    aliases_out=aliases_by_id,
                )
        finally:
            wb.close()
        return L1IngestResult(
            cycle_year=cycle,
            schools=list(schools_by_id.values()),
            metrics=list(metrics_by_id.values()),
            aliases=list(aliases_by_id.values()),
        )

    def _parse_sheet(  # noqa: PLR0912 — header detection + multi-output emission
        self,
        ws: Worksheet,
        cycle: str,
        *,
        schools_out: dict[str, L1School],
        metrics_out: dict[str, L1SchoolYearMetric],
        aliases_out: dict[str, L1Alias],
    ) -> None:
        # Materialize the first 20 rows once — read-only iteration can't replay.
        head_rows: list[tuple[Cell, ...]] = []
        for row in ws.iter_rows(max_row=20):
            head_rows.append(tuple(row))

        header_idx, headers = self._find_header(head_rows)
        if header_idx is None or headers is None:
            return
        school_col = self._find_col_in_headers(headers, SCHOOL_ALIASES)
        if school_col is None:
            return

        sheet_title = self._sheet_title(head_rows)
        state_col = self._find_col_in_headers(headers, STATE_ALIASES)
        city_col = self._find_col_in_headers(headers, CITY_ALIASES)
        metric_cols = self._find_metric_cols(headers)
        if not metric_cols:
            return

        t_valid_from = self._cycle_to_datetime(cycle, start=True)
        t_valid_to = self._cycle_to_datetime(cycle, start=False)
        sheet_label = ws.title

        for row in ws.iter_rows(min_row=header_idx + 2):
            if school_col >= len(row):
                continue
            name = self._cell_text(row[school_col])
            if not name or self._is_summary_row(name):
                continue
            # GAP-045 cont'd: SDE3 Tab5+ uses random numeric codes for the
            # school column (e.g., "4476"). Those rows can't be canonicalized
            # and must be skipped.
            if self._is_anonymized_code(name):
                continue
            normalized_name = self._strip_footnote(name)
            canonical_id = f"school:{slugify(normalized_name)}"
            row_num = int(getattr(row[school_col], "row", 0) or 0)
            if canonical_id not in schools_out:
                schools_out[canonical_id] = L1School(
                    canonical_id=canonical_id,
                    canonical_name=normalized_name,
                    city=self._optional_text(row, city_col),
                    state=self._optional_text(row, state_col),
                    source_row=f"{sheet_label}!A{row_num}",
                )
                alias_id = f"alias:{slugify(canonical_id + ':' + normalized_name)}"
                if alias_id not in aliases_out:
                    aliases_out[alias_id] = L1Alias(
                        alias_text=normalized_name,
                        canonical_id=canonical_id,
                        alias_source="manual",
                        confidence=1.0,
                    )
            for col_idx, metric_label in metric_cols:
                if col_idx >= len(row):
                    continue
                raw_value = row[col_idx].value
                if raw_value is None or raw_value == "":
                    continue
                metric_value = self._coerce_float(raw_value)
                qualified_name = (
                    f"{sheet_title} - {metric_label}" if sheet_title else metric_label
                )
                metric_id = (
                    f"metric:{slugify(canonical_id)}:"
                    f"{slugify(qualified_name)}:{cycle}"
                )
                if metric_id in metrics_out:
                    continue
                metrics_out[metric_id] = L1SchoolYearMetric(
                    metric_id=metric_id,
                    canonical_school_id=canonical_id,
                    cycle_year=cycle,
                    metric_name=qualified_name,
                    metric_value=metric_value,
                    unit=None,
                    source_row=f"{sheet_label}!{_col_letter(col_idx)}{row_num}",
                    t_valid_from=t_valid_from,
                    t_valid_to=t_valid_to,
                )

    def persist(self, result: L1IngestResult, source_dump_id: str) -> None:
        now_iso = to_iso(utc_now())
        with self._connect() as conn:
            for s in result.schools:
                conn.execute(
                    "INSERT OR IGNORE INTO l1_school "
                    "(canonical_id, canonical_name, city, state, country, "
                    " source_dump_id, created_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        s.canonical_id, s.canonical_name, s.city, s.state, "US",
                        source_dump_id, now_iso,
                    ),
                )
            for m in result.metrics:
                conn.execute(
                    "INSERT OR REPLACE INTO l1_school_year_metric "
                    "(metric_id, canonical_school_id, cycle_year, metric_name, "
                    " metric_value, unit, source_dump_id, source_row, "
                    " t_valid_from, t_valid_to) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        m.metric_id, m.canonical_school_id, m.cycle_year, m.metric_name,
                        m.metric_value, m.unit, source_dump_id, m.source_row,
                        to_iso(m.t_valid_from), to_iso(m.t_valid_to),
                    ),
                )
            for a in result.aliases:
                alias_id = f"alias:{slugify(a.canonical_id + ':' + a.alias_text)}"
                conn.execute(
                    "INSERT OR IGNORE INTO alias "
                    "(alias_id, canonical_id, alias_text, alias_source, "
                    " confidence, created_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        alias_id, a.canonical_id, a.alias_text, a.alias_source,
                        a.confidence, now_iso,
                    ),
                )
                # Emit rule-based short-form expansions ("NYU", "Penn", ...).
                for expanded in expand_aliases(a.canonical_id, a.alias_text):
                    expanded_id = (
                        f"alias:{slugify(a.canonical_id + ':' + expanded.alias_text)}"
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO alias "
                        "(alias_id, canonical_id, alias_text, alias_source, "
                        " confidence, created_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            expanded_id, expanded.canonical_id,
                            expanded.alias_text, f"discovered_{expanded.source}",
                            0.9, now_iso,
                        ),
                    )
            conn.commit()

    @staticmethod
    def _cycle_from_filename(name: str) -> str | None:
        m = _CYCLE_RE.search(name)
        if not m:
            return None
        return f"{m.group(1)}-{m.group(2)}"

    @staticmethod
    def _cycle_to_datetime(cycle: str, *, start: bool) -> datetime:
        year = int(cycle.split("-", 1)[0])
        if start:
            return datetime(year, 9, 1, tzinfo=UTC)
        return datetime(year + 1, 8, 31, tzinfo=UTC)

    @classmethod
    def _find_header(
        cls, head_rows: list[tuple[Cell, ...]],
    ) -> tuple[int | None, list[str] | None]:
        """Pick the row whose cells include a school-identifier — that's the real header."""

        for idx, row in enumerate(head_rows):
            headers = [cls._cell_text(c) for c in row]
            if any(cls._is_school_header(h) for h in headers):
                return idx, headers
        return None, None

    @staticmethod
    def _is_school_header(text: str) -> bool:
        s = text.strip().lower()
        if not s:
            return False
        if s in SCHOOL_ALIASES:
            return True
        return any(sub in s for sub in SCHOOL_HEADER_SUBSTRINGS)

    @staticmethod
    def _is_state_header(text: str) -> bool:
        s = text.strip().lower()
        if not s:
            return False
        if s in STATE_ALIASES:
            return True
        return any(sub in s for sub in STATE_HEADER_SUBSTRINGS)

    @classmethod
    def _find_col_in_headers(
        cls, headers: list[str], aliases: frozenset[str],
    ) -> int | None:
        # SDE1 path: school column via substring match.
        if aliases is SCHOOL_ALIASES:
            for i, h in enumerate(headers):
                if cls._is_school_header(h):
                    return i
            return None
        # SDE1 state column variant ("State / Country / Province").
        if aliases is STATE_ALIASES:
            for i, h in enumerate(headers):
                if cls._is_state_header(h):
                    return i
            return None
        for i, h in enumerate(headers):
            if h.strip().lower() in aliases:
                return i
        return None

    @classmethod
    def _find_metric_cols(cls, headers: list[str]) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for i, h in enumerate(headers):
            label = h.strip()
            if not label:
                continue
            low = label.lower()
            if low in NON_METRIC_HEADERS:
                continue
            # Skip the SDE1 substring-matched school + state columns too.
            if any(sub in low for sub in SCHOOL_HEADER_SUBSTRINGS):
                continue
            if any(sub in low for sub in STATE_HEADER_SUBSTRINGS):
                continue
            out.append((i, label))
        return out

    @classmethod
    def _sheet_title(cls, head_rows: list[tuple[Cell, ...]]) -> str:
        """Row 1's first non-empty text (e.g., 'Table 1: ... - Tuition ...')."""

        for row in head_rows[:3]:
            for c in row:
                text = cls._cell_text(c)
                if text:
                    return text
            # First non-empty cell in any row in first three; loop continues to next row
        return ""

    @staticmethod
    def _cell_text(cell: Cell) -> str:
        value = cell.value
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @classmethod
    def _optional_text(cls, row: tuple[Cell, ...], col: int | None) -> str | None:
        if col is None or col >= len(row):
            return None
        text = cls._cell_text(row[col])
        return text or None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            return float(value)
        try:
            cleaned = str(value).replace(",", "").replace("$", "").strip()
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_summary_row(text: str) -> bool:
        lower = text.strip().lower()
        return lower in _SUMMARY_LABELS or lower.startswith("total ")

    @staticmethod
    def _strip_footnote(name: str) -> str:
        """Normalize a school name by stripping trailing footnote markers
        (digits, asterisks, daggers) that the ADEA spreadsheets sometimes
        append to indicate a notes-to-the-reader anchor."""

        return _FOOTNOTE_SUFFIX_RE.sub("", name).strip()

    @staticmethod
    def _is_anonymized_code(text: str) -> bool:
        """SDE3 Tab5+ uses 4-digit random codes for the school column rather
        than names. Detect by the absence of any alphabetic characters."""

        s = text.strip()
        if not s:
            return False
        return not any(c.isalpha() for c in s)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS l1_school (
                    canonical_id     TEXT PRIMARY KEY,
                    canonical_name   TEXT NOT NULL,
                    city             TEXT,
                    state            TEXT,
                    country          TEXT DEFAULT 'US',
                    ada_code         TEXT,
                    website          TEXT,
                    source_dump_id   TEXT NOT NULL,
                    created_utc      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_l1_school_state ON l1_school(state);

                CREATE TABLE IF NOT EXISTS l1_school_year_metric (
                    metric_id            TEXT PRIMARY KEY,
                    canonical_school_id  TEXT NOT NULL
                        REFERENCES l1_school(canonical_id),
                    cycle_year           TEXT NOT NULL,
                    metric_name          TEXT NOT NULL,
                    metric_value         REAL,
                    unit                 TEXT,
                    source_dump_id       TEXT NOT NULL,
                    source_row           TEXT,
                    t_valid_from         TEXT NOT NULL,
                    t_valid_to           TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_l1_metric_school
                    ON l1_school_year_metric(canonical_school_id);
                CREATE INDEX IF NOT EXISTS idx_l1_metric_cycle
                    ON l1_school_year_metric(cycle_year);

                CREATE TABLE IF NOT EXISTS alias (
                    alias_id        TEXT PRIMARY KEY,
                    canonical_id    TEXT NOT NULL,
                    alias_text      TEXT NOT NULL,
                    alias_source    TEXT NOT NULL,
                    confidence      REAL,
                    created_utc     TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alias_canonical
                    ON alias(canonical_id);
                """,
            )


def _is_data_sheet(sheet_name: str) -> bool:
    if sheet_name in SKIP_SHEET_NAMES:
        return False
    return not sheet_name.lower().startswith("fig")


def _col_letter(idx: int) -> str:
    letters = ""
    n = idx
    while True:
        letters = chr(ord("A") + (n % 26)) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return letters
