"""Settings contract tests (frozen env names: docs/01_architecture/architecture.md §6)."""

from __future__ import annotations

import pytest

from backend.core.config import Settings

_OVERRIDABLE = (
    "DATABASE_URL",
    "LLM_PROVIDER",
    "GLM_API_KEY",
    "GLM_MODEL",
    "GLM_BASE_URL",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_BASE_URL",
    "FRED_API_KEY",
    "DATA_CACHE_DIR",
    "RUN_BUDGET_TOKENS",
    "RUN_TIMEOUT_SECONDS",
    "LOG_LEVEL",
    "RUN_LIVE_SMOKE",
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _OVERRIDABLE:
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "glm"
    assert settings.glm_model == "glm-5.3-flash"
    assert settings.glm_base_url == "https://api.z.ai/api/paas/v4"
    assert settings.run_budget_tokens == 200_000
    assert settings.run_timeout_seconds == 600
    assert settings.data_cache_dir == "data/raw"
    assert settings.log_level == "INFO"
    assert settings.run_live_smoke is False
    assert settings.llm_configured is False


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RUN_BUDGET_TOKENS", "1234")
    monkeypatch.setenv("RUN_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("RUN_LIVE_SMOKE", "1")
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "openai"
    assert settings.run_budget_tokens == 1234
    assert settings.run_timeout_seconds == 90
    assert settings.run_live_smoke is True
    assert settings.llm_configured is True


def test_ollama_needs_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _OVERRIDABLE:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert Settings(_env_file=None).llm_configured is False
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    assert Settings(_env_file=None).llm_configured is True


def test_invalid_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
