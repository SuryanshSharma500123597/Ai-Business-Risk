"""Phase 3 data-quality regression tests."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.data_engine.contracts import (
    CompanyDataset,
    CompanyProfile,
    PeriodFinancials,
    SyntheticCompanyConfig,
)
from backend.data_engine.ingest.synthetic import generate_company
from backend.data_engine.normalize.currency import convert_period
from backend.data_engine.normalize.periods import to_frequency
from backend.data_engine.validate.identities import check_period
from backend.data_engine.validate.schema_checks import validate_dataset


def period(**updates: object) -> PeriodFinancials:
    values: dict[str, object] = {
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "frequency": "monthly",
        "source": "synthetic",
        "revenue": 100.0,
        "cogs": 60.0,
        "gross_profit": 40.0,
        "cash": 10.0,
        "receivables": 20.0,
        "inventory": 10.0,
        "current_assets": 40.0,
        "current_liabilities": 20.0,
        "total_assets": 100.0,
        "total_liabilities": 60.0,
        "equity": 40.0,
        "interest_expense": 1.0,
    }
    values.update(updates)
    return PeriodFinancials(**values)


def dataset(periods: list[PeriodFinancials]) -> CompanyDataset:
    return CompanyDataset(
        profile=CompanyProfile(name="Example", sector="manufacturing"), periods=periods
    )


def test_validate_dataset_checks_all_periods_and_blocks_identity_errors() -> None:
    report = validate_dataset(dataset([period(), period(period_end=date(2024, 2, 29), equity=1.0)]))
    assert report.blocked
    assert any(issue.severity == "error" for issue in report.issues)


def test_real_current_assets_may_include_unmodeled_components() -> None:
    p = period(source="edgar", current_assets=50.0)
    assert check_period(p) == []


def test_missing_identity_inputs_are_coverage_not_identity_errors() -> None:
    assert "assets != liabilities + equity" not in check_period(period(equity=None))


def test_warning_does_not_block_but_duplicate_order_does() -> None:
    p = period(opex=500.0)
    warning_report = validate_dataset(dataset([p]))
    assert not warning_report.blocked
    assert any(issue.severity == "warning" for issue in warning_report.issues)
    ordered_report = validate_dataset(
        dataset([p, p.model_copy(update={"period_end": date(2024, 1, 31)})])
    )
    assert ordered_report.blocked


def test_nonfinite_financial_value_rejected() -> None:
    with pytest.raises(ValidationError):
        period(revenue=float("nan"))


def test_synthetic_rejects_negative_seed_and_out_of_bounds_anomaly() -> None:
    with pytest.raises(ValidationError):
        SyntheticCompanyConfig(seed=-1)
    with pytest.raises(ValidationError):
        SyntheticCompanyConfig(
            seed=1,
            inject_anomalies=[
                {
                    "type": "margin_collapse",
                    "start_month": 24,
                    "duration_months": 2,
                    "magnitude": 0.5,
                }
            ],
        )


def test_annual_normalization_preserves_missing_flow() -> None:
    first = period()
    second = period(period_end=date(2024, 2, 29), dividends=10.0)
    annual, _ = to_frequency([first, second], "annual")
    assert annual == []  # incomplete calendar year is not invented


def test_fx_conversion_includes_debt_schedule_and_rejects_nonfinite_rate() -> None:
    p = period(debt_schedule=[{"bucket": "0-3m", "amount": 10.0}])
    converted = convert_period(p, 2.0)
    assert converted.debt_schedule is not None
    assert converted.debt_schedule[0].amount == 20.0
    with pytest.raises(ValueError, match="finite"):
        convert_period(p, float("inf"))


def test_generated_company_is_source_neutral_dataset() -> None:
    company = generate_company(SyntheticCompanyConfig(seed=17))
    assert isinstance(company, CompanyDataset)
    assert company.generator_config is not None
