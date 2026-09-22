"""Error envelope contract tests (frozen: docs/01_architecture/api.md §1)."""

from __future__ import annotations

from backend.core.errors import AppError, ErrorCode, error_envelope


def test_error_envelope_shape() -> None:
    envelope = error_envelope(ErrorCode.NOT_FOUND, "company not found", {"id": "x"})
    assert envelope == {
        "error": {"code": "NOT_FOUND", "message": "company not found", "details": {"id": "x"}}
    }


def test_error_envelope_details_default_empty() -> None:
    envelope = error_envelope(ErrorCode.INTERNAL_ERROR, "boom")
    assert envelope["error"]["details"] == {}


def test_app_error_attributes() -> None:
    err = AppError(ErrorCode.RUN_STATE_INVALID, "bad state", {"status": "pending"})
    assert err.code == "RUN_STATE_INVALID"
    assert err.message == "bad state"
    assert err.details == {"status": "pending"}
    assert str(err) == "bad state"
