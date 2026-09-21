from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    L1_IMMUTABLE_REJECT = "L1_IMMUTABLE_REJECT"
    GATEWAY_ALL_VENDORS_FAILED = "GATEWAY_ALL_VENDORS_FAILED"
    INGESTION_PAYLOAD_MISSING = "INGESTION_PAYLOAD_MISSING"
    INGESTION_MANIFEST_INVALID = "INGESTION_MANIFEST_INVALID"

    # V1.5a connector errors
    CONNECTOR_NOT_FOUND = "CONNECTOR_NOT_FOUND"
    CONNECTOR_ALREADY_REGISTERED = "CONNECTOR_ALREADY_REGISTERED"
    ENGINE_UNSUPPORTED = "ENGINE_UNSUPPORTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CRED_NOT_FOUND = "CRED_NOT_FOUND"
    SCHEMA_NOT_DISCOVERED = "SCHEMA_NOT_DISCOVERED"
    SCHEMA_TOO_LARGE = "SCHEMA_TOO_LARGE"
    INVALID_MAPPING = "INVALID_MAPPING"
    MAPPING_NOT_COMMITTED = "MAPPING_NOT_COMMITTED"
    PULL_IN_PROGRESS = "PULL_IN_PROGRESS"
    COST_CAP_HIT = "COST_CAP_HIT"

    # V1.6a website-crawl errors (ADR-019 + api.md)
    DOMAIN_BLOCKED = "DOMAIN_BLOCKED"
    UNREACHABLE_DOMAIN = "UNREACHABLE_DOMAIN"
    INVALID_CRON = "INVALID_CRON"
    L1_NOT_CONFIRMED = "L1_NOT_CONFIRMED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CRAWL_RUNNING = "CRAWL_RUNNING"
    SCRAPINGBEE_UNAVAILABLE = "SCRAPINGBEE_UNAVAILABLE"


class StructuredError(Exception):
    """Single error shape across the engine (per `docs/05-features/01-slice-trust-tier-canonicalize/api.md` §API error model)."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        context: dict[str, Any] | None = None,
        retry_safe: bool = False,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.context: dict[str, Any] = context or {}
        self.retry_safe = retry_safe
        super().__init__(f"[{error_code.value}] {message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "context": self.context,
            "retry_safe": self.retry_safe,
        }
