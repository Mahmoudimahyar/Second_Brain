# Contributing to SecBrain

Thanks for your interest. SecBrain is pre-1.0 research software with one maintainer, so the
most useful contributions are **small, evidenced, and reviewable**: a failing test, a
reproducible bug, an eval case the engine gets wrong, or a doc that claims more than the code
does.

## Ground rules

1. **No third-party text, no personal data, no licensed data — ever.** Do not paste real forum
   posts, usernames, thread links, or figures from paid datasets into code, fixtures, gold
   sets, issues, or PRs. Write synthetic examples. See [`evals/README.md`](evals/README.md) for
   how a gold set is built without publishing anyone's words.
2. **"Tests pass" is not "done".** A capability is done when it is *wired* into a real
   entrypoint (`src/cli.py`, a `flows/*.py` flow, a `src/web/routes/*` route, or an MCP tool)
   and you can cite the call site as `file:line`.
3. **The status file is the source of truth.** If your change moves a capability, update its
   row in [`docs/00-bootstrap/implementation-status.md`](docs/00-bootstrap/implementation-status.md)
   *first*, then any ADR or architecture doc. CI runs a doc-lint that fails when docs claim
   more than the code delivers.

The full operating rules — written for coding agents, equally valid for humans — are in
[`AGENTS.md`](AGENTS.md). The reason they exist is in
[`why-drift-happened.md`](docs/00-bootstrap/why-drift-happened.md).

## Development setup

Requires Python ≥ 3.12. The test suite needs **no API keys, no corpus, and no GPU**.

```bash
git clone https://github.com/Mahmoudimahyar/Second_Brain.git
cd Second_Brain
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                               # ~1 minute
```

Web console (Node ≥ 22, pnpm ≥ 11):

```bash
cd web
pnpm install
pnpm typecheck && pnpm test          # unit
pnpm exec playwright install && pnpm test:e2e   # end-to-end + axe-core accessibility
```

Optional extras, installed only when you need them:

| Extra | Pulls in | For |
|---|---|---|
| `web` | FastAPI, uvicorn | the `/api/v1` backend and `secbrain ui` |
| `analysis` | scikit-learn, scipy | Pass-3 clustering, hybrid index, calibration |
| `embeddings` | sentence-transformers, gliner (torch) | local embedders and NER |
| `gateway` | anthropic, openai, google-genai, langfuse | live LLM calls |
| `orchestration` | prefect | scheduled flows under `flows/` |
| `website-crawl` | crawl4ai, pikepdf, pandas, … | the staged website crawler |

`dev` already includes `web` + `analysis` and the light crawl dependencies the tests touch.

## Checks

```bash
pytest                                       # blocking in CI
ruff check src flows tools --select F,E9     # blocking in CI
secbrain-doc-lint                            # blocking in CI
ruff check .                                 # ratchet — not clean yet
mypy src tools                               # ratchet — strict mode, not clean yet
```

**Before a release, run the suite in a *fresh* virtualenv**, not your working one. A long-lived
environment hides version drift: the first public CI run of this repository was red because a
new test had only ever been run against an older Typer (see `CHANGELOG.md`, 0.1.1).

Being straight about the ratchets: the configured ruff rule set and `mypy --strict` both
report outstanding findings today (the largest group is `PLC0415`, flagging the codebase's
deliberate lazy imports). They run on every CI build as informational jobs. PRs should not
add to either count; PRs that reduce them are welcome.

Architectural rules ruff *does* enforce: vendor SDKs (`anthropic`, `openai`, `google.genai`)
may only be imported inside `src/gateway/`; `langchain` and `requests` are banned outright.
See [`dependency-rules.md`](docs/04-architecture/dependency-rules.md).

## Workflow

1. **Open an issue first** for anything beyond a small fix, so scope is agreed before code.
2. **Write the test first**, watch it fail, then implement the smallest change that passes.
3. **One slice per PR.** Keep the diff small enough to actually read. Never squash a large body
   of work into one commit — that is precisely how wiring gaps went unnoticed here once.
4. **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/),
   as the history does: `feat(retrieval): …`, `fix(er): …`, `docs(status): …`.
5. **Fill in the PR template**, including the wiring site and the evidence you ran.
6. Changed a CLI command, an option, or an API route? Run `python -m tools.docs.gen_reference`
   and commit the regenerated reference pages — a test fails otherwise. New environment
   variable? Document it in `.env.example` and `docs/guide/configuration.md` (also tested).
7. Architecture-level changes need an ADR under [`docs/11-decisions/`](docs/11-decisions/)
   (copy `TEMPLATE.md`). An ADR may not be `accepted` while a load-bearing citation is
   unverified.

Adding a dependency needs a reason: the existing stack cannot reasonably do it, the package is
maintained, and the licence is compatible with Apache-2.0.

## Reporting security or privacy problems

Privately, please — see [`SECURITY.md`](SECURITY.md). That includes finding anything in this
repository that looks like personal data or a credential.

## Licence

By contributing you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE), the licence of this repository's code and documentation.
