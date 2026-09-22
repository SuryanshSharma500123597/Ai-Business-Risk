"""Stable error codes and the error envelope (frozen in docs/01_architecture/api.md §1)."""

from __future__ import annotations

from typing import Any


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    DATA_COVERAGE_LOW = "DATA_COVERAGE_LOW"
    SCENARIO_OUT_OF_BOUNDS = "SCENARIO_OUT_OF_BOUNDS"
    SCENARIO_PENDING_CONFIRM = "SCENARIO_PENDING_CONFIRM"
    RUN_STATE_INVALID = "RUN_STATE_INVALID"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Domain error carrying a stable code for the API error envelope."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def error_envelope(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the API error body: {"error": {"code", "message", "details"}}."""
    return {"error": {"code": code, "message": message, "details": details or {}}}
