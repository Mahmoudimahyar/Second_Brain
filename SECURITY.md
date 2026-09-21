# Security Policy

## Supported versions

SecBrain is pre-1.0 research software. Security fixes land on the default branch only;
there are no maintained release branches yet.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting instead:
**Security → Advisories → Report a vulnerability** on this repository.

Please include:

- what you found and where (`path:line` if you have it),
- how to reproduce it,
- the impact you expect (data exposure, code execution, cost abuse, …).

You should get an acknowledgement within 7 days. Once a fix is available the advisory is
published with credit, unless you prefer to stay anonymous.

## Scope

In scope:

- the Python engine (`src/`, `flows/`, `tools/`),
- the FastAPI backend (`src/web/`) and the Next.js console (`web/`),
- the MCP servers (`src/retrieval/mcp_server.py`, `tools/graphrag/mcp_server.py`),
- the website crawler's safety controls (robots handling, domain blocklist, budget caps).

Out of scope:

- vulnerabilities in third-party dependencies with no SecBrain-specific exploit path
  (report those upstream),
- findings that require a pre-compromised workstation — V1 is designed as a
  single-tenant, local-first tool and is **not** hardened for multi-tenant or
  internet-facing deployment (see `docs/12-security/`).

## Handling secrets

- Secrets live only in a local `.env` (git-ignored). `.env.example` documents every
  variable with placeholder values — never real ones.
- No API key is required to run the test suite; LLM vendors are stubbed in tests.
- If you ever find a credential in this repository or its history, report it through the
  private channel above so it can be rotated before disclosure.

## Data and privacy

This repository contains **code only** — no corpus, reference data, graph or run output
(see *Data and privacy* in the README). If you believe personal data has been committed by mistake, treat
it as a security report.
