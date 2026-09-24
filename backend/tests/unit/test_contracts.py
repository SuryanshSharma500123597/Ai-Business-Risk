"""Contract/schema tests for the canonical data model (frozen data.md §1)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.data_engine.contracts import (
    COVERAGE_GATE_PCT,
    IDENTITY_TOLERANCE,
    MIN_PERIODS_FOR_ML,
    OPTIONAL_CONCEPTS,
    REQUIRED_CONCEPTS,
    SyntheticCompanyConfig,
    hash_name,
)
from backend.data_engine.contracts import (
    ShareEntry as SE,
)


def make_period_kwargs() -> dict[str, object]:
    return {
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "frequency": "monthly",
        "source": "synthetic",
    }


def test_required_and_optional_sets_frozen() -> None:
    assert len(REQUIRED_CONCEPTS) == 9
    assert "revenue" in REQUIRED_CONCEPTS and "equity" in REQUIRED_CONCEPTS
    assert "ebitda" in OPTIONAL_CONCEPTS and "customers" in OPTIONAL_CONCEPTS
    assert not set(REQUIRED_CONCEPTS) & set(OPTIONAL_CONCEPTS)
    assert COVERAGE_GATE_PCT == 70.0
    assert IDENTITY_TOLERANCE == 0.005
    assert MIN_PERIODS_FOR_ML == 8


def test_share_entry_rules() -> None:
    assert SE(name="alpha", share=0.5).share == 0.5
    assert SE(name_hash="abc123", share=0.5).name_hash == "abc123"
    with pytest.raises(ValidationError):
        SE(name="alpha", name_hash="abc", share=0.5)  # both labels
    with pytest.raises(ValidationError):
        SE(share=0.5)  # no label
    with pytest.raises(ValidationError):
        SE(name="alpha", share=1.5)  # out of range


def test_hash_name_stable_and_short() -> None:
    h1, h2 = hash_name("Acme Corp"), hash_name("Acme Corp")
    assert h1 == h2 and len(h1) == 16 and h1 != hash_name("Acme Corp ")


def test_period_financials_extra_forbidden() -> None:
    from backend.data_engine.contracts import PeriodFinancials

    kwargs = make_period_kwargs()
    PeriodFinancials(**kwargs)  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValidationError):
        PeriodFinancials(**kwargs, surprise_field=1.0)  # type: ignore[call-arg]


def test_synthetic_config_frequency_ranges() -> None:
    SyntheticCompanyConfig(seed=1)  # default monthly 24
    SyntheticCompanyConfig(seed=1, frequency="annual", periods=3)
    with pytest.raises(ValidationError):
        SyntheticCompanyConfig(seed=1, frequency="annual", periods=11)
    with pytest.raises(ValidationError):
        SyntheticCompanyConfig(seed=1, periods=11)  # monthly below 12
    with pytest.raises(ValidationError):
        SyntheticCompanyConfig(seed=1, periods=37)


def test_seasonality_default_by_sector() -> None:
    retail = SyntheticCompanyConfig(seed=1, sector="retail")
    mfg = SyntheticCompanyConfig(seed=1, sector="manufacturing")
    assert retail.effective_seasonality is True
    assert mfg.effective_seasonality is False
    override = SyntheticCompanyConfig(seed=1, sector="retail", seasonality=False)
    assert override.effective_seasonality is False
