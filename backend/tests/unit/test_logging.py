"""Logging tests: JSON output with run correlation (docs/01_architecture/architecture.md §9)."""

from __future__ import annotations

import json

import pytest

from backend.app.logging import bind_run_id, clear_run_context, configure_logging, get_logger


def test_json_log_line_includes_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    clear_run_context()
    bind_run_id("run-abc-123")
    try:
        get_logger("test").info("analysis event", stage="validate")
    finally:
        clear_run_context()

    out = capsys.readouterr().out
    lines = [line for line in out.strip().splitlines() if line]
    assert lines, "expected at least one log line on stdout"
    record = json.loads(lines[-1])
    assert record["event"] == "analysis event"
    assert record["run_id"] == "run-abc-123"
    assert record["stage"] == "validate"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_log_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING")
    clear_run_context()
    get_logger("test").info("should not appear")
    get_logger("test").warning("should appear")
    out = capsys.readouterr().out
    assert "should not appear" not in out
    assert "should appear" in out
