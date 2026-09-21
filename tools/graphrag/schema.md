# GraphRAG Schema — Repo MCP Server

> Node + edge types with **full property definitions**. Reference for both `tools/graphrag/parsers/` (emit) and `tools/graphrag/retrieval/` (consume). The V1 product engine schema is separate; see `docs/07-data/data-dictionary.md`.

## Property conventions (apply to every node + edge)

| Property | Type | Required | Description |
|---|---|---|---|
| `id` | str | yes | Canonical ID; format per "Canonical IDs" below |
| `node_type` / `edge_type` | str | yes | Enum string, e.g., `DocSection`, `FUNCTION_CALLS_FUNCTION` |
| `snapshot_id` | str | yes | Hash of the indexing run that produced this node/edge; for time-travel + incremental diffing |
| `created_at` | datetime UTC | yes | First time this id was seen in any snapshot |
| `last_seen_at` | datetime UTC | yes | Most recent snapshot to include this id |
| `last_modified_at` | datetime UTC | yes | Most recent snapshot where content-hash changed |
| `content_hash` | str | yes (on file-backed nodes) | Hash of the file content; drives incremental reindex |
| `source_path` | str | yes (on file-backed nodes) | Repo-relative path |

## Node types

### `DocPage`

A whole `.md` file.

| Property | Type | Notes |
|---|---|---|
| `title` | str | From the first H1 in the file (fallback: file name) |
| `frontmatter` | dict | YAML frontmatter parsed if present |
| `source_path` | str | e.g., `docs/01-core/product-vision.md` |
| `byte_size` | int | |
| `section_count` | int | Number of `DocSection` children |

### `DocSection`

A heading-bounded section within a DocPage. One per H1/H2/H3.

| Property | Type | Notes |
|---|---|---|
| `level` | int | 1 / 2 / 3 |
| `heading` | str | Heading text |
| `source_path` | str | `docs/<...>.md#anchor` |
| `text` | str | Section body (preserved; used for chunking + embedding) |
| `chunk_ids` | list[str] | Embedding-chunk IDs within this section |

### `Feature`

A slice / feature packet under `docs/05-features/<slice>/`.

| Property | Type | Notes |
|---|---|---|
| `slug` | str | E.g., `01-slice-trust-tier-canonicalize` |
| `name` | str | From README's title |
| `status` | enum | `proposed` / `in-progress` / `complete` / `deferred` (parsed from README front matter or `bootstrap-status.md` mapping) |
| `priority` | enum | If declared |

### `Requirement`

A functional (FR-*) or non-functional (NFR-*) requirement.

| Property | Type | Notes |
|---|---|---|
| `req_id` | str | E.g., `FR-2.3`, `NFR-1` |
| `feature_slug` | str | Which slice owns this requirement |
| `title` | str | Short title |
| `description` | str | Full text |
| `kind` | enum | `functional` / `non-functional` |

### `AcceptanceCriterion`

| Property | Type | Notes |
|---|---|---|
| `ac_id` | str | E.g., `AC-3` |
| `feature_slug` | str | |
| `description` | str | |
| `linked_requirement_ids` | list[str] | From the test-plan.md mapping table |

### `CodeFile`

| Property | Type | Notes |
|---|---|---|
| `language` | str | `python` for now |
| `source_path` | str | `src/...` or `tools/...` or `tests/...` |
| `loc` | int | Lines of code |
| `function_count` | int | |
| `class_count` | int | |

### `Function`

| Property | Type | Notes |
|---|---|---|
| `qualified_name` | str | `src.gateway.api.LLMClient.complete` |
| `parent_file` | str | source_path of CodeFile |
| `signature` | str | `(self, task: TaskID, ...) -> GatewayResponse` |
| `docstring` | str | Module docstring or function docstring |
| `is_public` | bool | Inferred from naming convention |
| `start_line`, `end_line` | int | |
| `body_hash` | str | hash of the function body (drives "did this function change?") |

### `Class`

Similar to `Function`; with `bases`, `methods` list.

### `Endpoint` (V2 — placeholder)

Reserved for when V2 introduces HTTP endpoints. Properties TBD.

### `DatabaseTable` (V1 product engine side store)

| Property | Type | Notes |
|---|---|---|
| `name` | str | E.g., `l1_school` |
| `source_path` | str | `src/sqlite/schema.sql` or `data/sqlite/...` |
| `columns` | list[dict] | name + type |

### `ConfigKey`

| Property | Type | Notes |
|---|---|---|
| `key` | str | E.g., `ANTHROPIC_API_KEY` |
| `source_path` | str | `.env.example` or `pyproject.toml` |
| `description` | str | Annotation from .env.example |
| `required` | bool | |

### `TestFile`

| Property | Type | Notes |
|---|---|---|
| `source_path` | str | `tests/...` |
| `test_case_count` | int | |

### `TestCase`

| Property | Type | Notes |
|---|---|---|
| `qualified_name` | str | `tests.gateway.test_gateway.test_ttl_pinning_runtime` |
| `parent_file` | str | |
| `markers` | list[str] | `pytest` markers (`unit`, `integration`, etc.) |
| `linked_req_ids` | list[str] | From docstring tags |
| `linked_ac_ids` | list[str] | From docstring tags |

### `UIFlow` (V2 — placeholder)

Reserved. V1 has no UI.

### `ADR`

| Property | Type | Notes |
|---|---|---|
| `adr_id` | str | `ADR-001` |
| `title` | str | From the H1 |
| `status` | enum | `proposed` / `accepted` / `deprecated` / `pending` |
| `date` | date | |
| `decision_summary` | str | First paragraph of `## Decision` |
| `affects_modules` | list[str] | From the "Related code" section |

### `KnownIssue`

| Property | Type | Notes |
|---|---|---|
| `ki_id` | str | `KI-001` |
| `feature_slug` | str | Which feature packet owns this |
| `severity` | enum | `low` / `med` / `high` / `critical` |
| `category` | str | `Cost` / `Vendor` / `Data` / etc. |
| `description` | str | |
| `workaround` | str | If any |

### `Prompt`

| Property | Type | Notes |
|---|---|---|
| `prompt_id` | str | E.g., `stage3_sentiment` |
| `prompt_version` | int | |
| `source_path` | str | `src/prompts/stage3_sentiment.baml` |
| `schema_hash` | str | Hash of the output schema |

### `ContextPack`

| Property | Type | Notes |
|---|---|---|
| `pack_name` | str | E.g., `v1-slice-implementation` |
| `source_path` | str | `docs/14-context-packs/<pack>/` |
| `purpose` | str | One-line from README |

## Edge types

All edges carry the property convention (top of file). Below: per-type semantic.

### Hierarchy + structural edges

| Edge | From → To | Semantic |
|---|---|---|
| `DOC_PAGE_HAS_SECTION` | `DocPage` → `DocSection` | Tree structure |
| `FILE_HAS_FUNCTION` | `CodeFile` → `Function` | Tree |
| `FILE_HAS_CLASS` | `CodeFile` → `Class` | Tree |
| `CLASS_HAS_METHOD` | `Class` → `Function` | Methods of a class |
| `TEST_FILE_HAS_CASE` | `TestFile` → `TestCase` | Tree |

### Feature → docs → code → tests

| Edge | From → To | Derivation |
|---|---|---|
| `FEATURE_HAS_REQUIREMENT` | `Feature` → `Requirement` | parsed from `requirements.md` |
| `REQUIREMENT_HAS_ACCEPTANCE_CRITERION` | `Requirement` → `AcceptanceCriterion` | parsed from `test-plan.md` |
| `FEATURE_DOCUMENTED_BY` | `Feature` → `DocPage` | every `.md` under the slice's directory |
| `FEATURE_IMPLEMENTED_BY` | `Feature` → `CodeFile` | from `plan.md` references + naming convention match |
| `DOC_SECTION_REFERENCES_CODE` | `DocSection` → `CodeFile` / `Function` / `Class` | backtick-wrapped identifier match |
| `ENDPOINT_HANDLED_BY` | `Endpoint` → `Function` | V2 — reserved |
| `FUNCTION_CALLS_FUNCTION` | `Function` → `Function` | AST-derived |
| `TEST_COVERS_REQUIREMENT` | `TestCase` → `Requirement` | docstring tag (`# AC-3` or `# FR-2.3`) |
| `TEST_COVERS_ACCEPTANCE_CRITERION` | `TestCase` → `AcceptanceCriterion` | docstring tag |
| `TEST_COVERS_FUNCTION` | `TestCase` → `Function` | import / call analysis |
| `TEST_COVERS_CODE` | `TestCase` → `CodeFile` | broader version of above |
| `UI_FLOW_TESTED_BY` | `UIFlow` → `TestCase` | V2 reserved |

### Cross-cutting

| Edge | From → To | Derivation |
|---|---|---|
| `ADR_DECIDES` | `ADR` → `Feature` / `CodeFile` / `Function` / `Requirement` | "Related code" / "Related docs" sections in the ADR |
| `KNOWN_ISSUE_AFFECTS` | `KnownIssue` → `Function` / `Class` / `Feature` | issue text references |
| `PROMPT_USED_BY` | `Prompt` → `Function` | gateway-call analysis |
| `CONTEXT_PACK_REFERENCES` | `ContextPack` → `DocPage` / `Feature` / `CodeFile` | required-reading.md, related-code.md, etc. |

## Canonical IDs

| Type | Pattern | Example |
|---|---|---|
| DocPage | `doc:<path-with-slashes-replaced-by-colons>` | `doc:docs:01-core:product-vision.md` |
| DocSection | `<DocPageID>#<heading-slug>` | `doc:docs:04-architecture:tech-stack.md#model-gateway` |
| Feature | `feature:<slug>` | `feature:01-slice-trust-tier-canonicalize` |
| Requirement | `req:<feature-slug>:<req-id>` | `req:01-slice:FR-2.3` |
| AcceptanceCriterion | `ac:<feature-slug>:<ac-id>` | `ac:01-slice:AC-3` |
| CodeFile | `code:<path>` | `code:src/gateway/api.py` |
| Function | `fn:<qualified-name>` | `fn:src.gateway.api.LLMClient.complete` |
| Class | `cls:<qualified-name>` | `cls:src.gateway.api.LLMClient` |
| ConfigKey | `cfg:<key>` | `cfg:ANTHROPIC_API_KEY` |
| TestFile | `testfile:<path>` | `testfile:tests/gateway/test_gateway.py` |
| TestCase | `test:<qualified-name>` | `test:tests.gateway.test_gateway.test_ttl_pinning_runtime` |
| ADR | `adr:<id>` | `adr:ADR-001` |
| KnownIssue | `ki:<feature-slug>:<id>` | `ki:01-slice:KI-001` |
| Prompt | `prompt:<id>:<version>` | `prompt:stage3_sentiment:3` |
| ContextPack | `pack:<name>` | `pack:v1-slice-implementation` |

## Schema validation

A `tools/graphrag/schema_validate.py` script (built during Phase 2) walks the indexed graph and asserts:
- Every node has the required property convention fields.
- Every edge type's from/to types match the schema above.
- Every Requirement / AcceptanceCriterion has a `feature_slug` that maps to an actual `Feature`.
- No orphan `DocSection` without a `DocPage`.
- No orphan `Function` without a `CodeFile`.

Run as part of `tools/graphrag/index.py` (post-build sanity).

## Evolution

- New node types: ADR-required.
- New edge types: documented here + parser/derivation update + tests.
- Renaming: deprecation cycle with dual-write.
