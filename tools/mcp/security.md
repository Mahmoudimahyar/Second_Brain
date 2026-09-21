# MCP Security

## Principles

- Least privilege.
- Command allowlists.
- Path validation.
- No arbitrary shell execution from user-controlled input.
- No secrets returned to model context.
- Dangerous operations require explicit approval.
- Tool calls should be logged.
- Writes should be scoped to the repository.
- `.env` must never be printed into chat, logs, or reports.

## Dangerous operations

Require explicit approval for:
- deleting files
- destructive database migrations
- production deploys
- changing auth/payment/security config
- reading secret files
- modifying CI/CD secrets
