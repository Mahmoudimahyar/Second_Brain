# Documentation Activation Matrix

Not every project needs every doc. Use this to avoid documentation bloat.

| Doc group | Product/business | Internal tool | Dev tool | CLI | API service | Library | Research | Automation | Data pipeline | AI agent system | Landing page |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 00-bootstrap | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required |
| 01-core | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required |
| 02-product | Required | Light | Light | Skip | Skip | Light | Skip | Skip | Skip | Light | Required |
| 03-research | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required |
| 04-architecture | Required | Required | Required | Light | Required | Required | Light | Light | Required | Required | Light |
| 05-features | Required | Required | Required | Light | Required | Light | Optional | Light | Required | Required | Optional |
| 06-api | If relevant | If relevant | If relevant | Skip | Required | Public API docs | Optional | Optional | Required | If relevant | Skip |
| 07-data | If relevant | If relevant | If relevant | Optional | Required | Optional | Required if data | Optional | Required | Required if memory/RAG | Analytics only |
| 08-ui | Required if UI | Required if UI | Optional | Skip | Skip | Optional docs site | Optional | Skip | Optional dashboard | Required if UI | Required |
| 09-testing | Required | Required | Required | Required | Required | Required | Required | Required | Required | Required | Light |
| 10-operations | Required | Required | Required | Light | Required | Release docs | Reproducibility | Light | Required | Required | Light |
| 11-decisions | Required | Required | Required | Optional | Required | Required | Required | Optional | Required | Required | Optional |
| 12-security | Required | Required if sensitive | Required | Optional | Required | If sensitive | If sensitive | Optional | Required | Required | Light |
| 13-observability | Required | Required | Required | Light | Required | Optional | Experiment logging | Light | Required | Required | Analytics |
| 14-context-packs | Required | Required | Required | Optional | Required | Optional | Optional | Optional | Required | Required | Optional |
| 15-marketing | Optional/user choice | Skip | Optional | Skip | Skip | Optional | Skip | Skip | Skip | Optional | Required |
