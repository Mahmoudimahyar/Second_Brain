# SecBrain guide

User-facing documentation. If you want to *use* or *extend* SecBrain, start here. (The numbered
folders next to this one are the project's design record — feature packets, ADRs, research —
indexed in [`../README.md`](../README.md).)

| | |
|---|---|
| **[Quickstart](../../examples/quickstart/README.md)** | The whole idea in two minutes, on fictional data. No keys, no GPU, no downloads. |
| **[Concepts](concepts.md)** | Trust tiers, bitemporal edges, the five passes, entity resolution, the conflict cascade, evidence-grade answers. |
| **[Architecture tour](architecture.md)** | Which package does what, how a record flows through it, and where the tests for each part live. |
| **[Bring your own platform](adapters.md)** | What a source adapter is, what exists today, and what it honestly takes to add Slack, Discord, or your own API. |
| **[Use it from an AI agent (MCP)](mcp.md)** | The two MCP servers, their tools, and the config snippet. |
| **[Configuration](configuration.md)** | Every environment variable the code reads — and nothing else. |
| **[CLI reference](reference/cli.md)** | All commands and options. *Generated from the code.* |
| **[REST API reference](reference/rest-api.md)** | All `/api/v1` operations. *Generated from the code.* |
| **[FAQ](faq.md)** | Is it production-ready? Does it ship data? Why Kùzu? Why no LangChain? What does it cost? |

The two reference pages are produced by `python -m tools.docs.gen_reference`, and a test fails
if they fall out of date — the same "docs must not drift from code" rule the rest of the
project lives by.
