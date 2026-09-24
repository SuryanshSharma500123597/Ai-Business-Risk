"""Coverage matrix and sanity checks (frozen data.md §3 rules 1, 3, 4)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import PeriodFinancials, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.data_engine.validate.schema_checks import (
    concept_present,
    coverage_report,
    enforce_coverage_gate,
    latest_period,
    validate_company,
)


def period(**overrides: object) -> PeriodFinancials:
    values: dict[str, object] = {
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "frequency": "monthly",
        "source": "synthetic",
    }
    values.update(overrides)
    return PeriodFinancials(**values)  # pyright: ignore[reportCallIssue]


def test_full_generator_output_passes_gate() -> None:
    for seed in (1001, 1002, 1003, 1004, 1005):
        report = validate_company(generate_company(SyntheticCompanyConfig(seed=seed)))
        assert report.required_pct == 100.0
        assert not report.blocked
        assert report.missing_required == []


def test_empty_concept_coverage_and_gate() -> None:
    empty = period()
    report = coverage_report([empty])
    assert report.required_pct == 0.0
    assert report.blocked
    with pytest.raises(AppError) as exc:
        enforce_coverage_gate(report)
    assert exc.value.code == ErrorCode.DATA_COVERAGE_LOW
    assert set(exc.value.details["missing"]) >= {"revenue", "cash", "equity"}


def test_gate_boundary_around_70pct() -> None:
    # 9 required concepts: 8 present = 88.9% (pass), 7 = 77.8% (pass),
    # 6 = 66.7% (blocked)
    full = dict(
        revenue=1.0,
        cogs=1.0,
        cash=1.0,
        current_assets=1.0,
        current_liabilities=1.0,
        total_assets=1.0,
        total_liabilities=1.0,
        equity=1.0,
    )
    p8 = period(**full)  # missing interest_expense -> 8/9
    report = coverage_report([p8])
    assert report.required_pct == pytest.approx(88.9, abs=0.1)
    assert not report.blocked

    p7 = period(**{k: v for k, v in full.items() if k != "equity"})
    report = coverage_report([p7])
    assert report.required_pct == pytest.approx(77.8, abs=0.1)
    assert not report.blocked

    p6 = period(
        revenue=1.0,
        cogs=1.0,
        cash=1.0,
        current_assets=1.0,
        current_liabilities=1.0,
        total_assets=1.0,
    )  # 6/9
    report = coverage_report([p6])
    assert report.blocked

    p5 = period(
        revenue=1.0, cogs=1.0, cash=1.0, current_assets=1.0, current_liabilities=1.0
    )  # 5/9 = 55.6%
    report = coverage_report([p5])
    assert report.blocked


def test_latest_vs_all_mode() -> None:
    old = period(period_end=date(2023, 12, 31), revenue=10.0, ocf=2.0)
    new = period(
        period_end=date(2024, 1, 31),
        revenue=10.0,
        cogs=5.0,
        cash=1.0,
        current_assets=2.0,
        current_liabilities=1.0,
        total_assets=9.0,
        total_liabilities=4.0,
        equity=5.0,
        interest_expense=0.1,
    )
    latest = coverage_report([old, new])
    assert latest.required_pct == 100.0
    # ocf only in the old period: 'latest' counts it missing, 'all' finds it
    assert "ocf" in [i.concept for i in latest.missing_optional]
    all_mode = coverage_report([old, new], mode="all")
    assert "ocf" not in [i.concept for i in all_mode.missing_optional]


def test_period_sanity_warnings() -> None:
    unsorted = [
        period(period_end=date(2024, 2, 29), revenue=1.0),
        period(period_end=date(2024, 1, 31), revenue=1.0),
    ]
    report = coverage_report(unsorted)
    assert "periods not sorted by period_end" in report.warnings

    duplicated = [period(revenue=1.0), period(revenue=1.0)]
    report = coverage_report(duplicated)
    assert "duplicate period_end values present" in report.warnings

    short = [period(revenue=1.0)]
    report = coverage_report(short)
    assert any("fewer than 8 periods" in w for w in report.warnings)


def test_margin_out_of_range_warning() -> None:
    weird = period(
        period_end=date(2024, 1, 31),
        revenue=1.0,
        gross_profit=5.0,
        cogs=-4.0,
        cash=1.0,
        current_assets=2.0,
        current_liabilities=1.0,
        total_assets=9.0,
        total_liabilities=4.0,
        equity=5.0,
        interest_expense=0.1,
    )
    report = coverage_report([weird])
    assert any("outside [-1, 1]" in w for w in report.warnings)


def test_concept_present_semantics() -> None:
    p = period(revenue=1.0, customers=[])
    assert concept_present(p, "revenue") is True
    assert concept_present(p, "cogs") is False
    assert concept_present(p, "customers") is False  # empty list is absent
    assert concept_present(p, "nonexistent") is False


def test_latest_period_and_empty_error() -> None:
    a = period(period_end=date(2024, 1, 31))
    b = period(period_end=date(2024, 2, 29))
    assert latest_period([a, b]).period_end == b.period_end
    with pytest.raises(AppError):
        coverage_report([])
    with pytest.raises(AppError):
        latest_period([])
