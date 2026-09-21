# Project Mode Router

Before discovery, documentation, architecture, or coding, classify the project mode.

## First question

Ask the user:

"What type of project are we building?"

Options:
A. Full product/business
B. Internal tool
C. Developer tool
D. CLI tool
E. API/backend service
F. Library/package
G. Research prototype
H. Automation script
I. Data pipeline
J. AI agent system
K. Landing page only
L. Not sure — help me decide

## Hard rule

Do not create marketing, sales, pricing, competitor, or customer-segmentation docs unless:
- the selected mode requires them
- the user explicitly asks for them
- they are necessary for the project goal

## Mode rules

### product_business
Required: core, product, architecture, features, UI/UX if applicable, testing, operations, security, observability.
Optional: marketing, competitors, pricing, channel strategy, content system.

### internal_tool
Required: core, workflow docs, architecture, features, UI-flow or CLI-flow, testing, operations, security if sensitive.
Skip by default: marketing, pricing, competitors, channel strategy.

### developer_tool
Required: developer use cases, architecture, CLI/API contracts, examples, testing, DevEx, release/versioning.
Skip by default: sales/marketing unless public launch.

### cli_tool
Required: command reference, input/output contracts, config/env docs, error codes, examples, testing, install/run docs.
Skip by default: website map, marketing, visual design system.

### api_service
Required: API contracts, data model, auth/security, integration tests, contract tests, deployment, observability.
Skip by default: UI-flow, design system, marketing.

### library_package
Required: public API, examples, package structure, versioning, compatibility, tests, docs generation, release process.
Skip by default: marketing, UI-flow, website map unless docs site needed.

### research_prototype
Required: research question, hypotheses, methodology, data sources, experiment protocol, evaluation metrics, reproducibility, limitations, results log.
Skip by default: marketing, pricing, sales, production-grade design system.

### automation_script
Required: workflow description, inputs/outputs, config/env, failure modes, logging, tests, runbook.
Skip by default: product docs, marketing, UI-flow unless GUI exists.

### data_pipeline
Required: data sources, schemas, transformations, validation rules, lineage, failure handling, observability, tests.
Skip by default: marketing and UI design.

### ai_agent_system
Required: agent roles, tool permissions, memory/retrieval strategy, evals, safety rules, context budget, trace/logging, failure handling, prompt/versioning.
Marketing optional only if public product.

### landing_page_only
Required: audience, positioning, conversion goal, copy, design system, site map, analytics, testing.
Architecture can be minimal.

## Output

After classification, write:
- selected mode
- why
- required docs
- optional docs
- docs to skip
- first questions to ask
