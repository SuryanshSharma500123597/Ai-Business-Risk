"""Synthetic generator tests: determinism (R6), identities, anomaly injection,
concentration bands, canonical fixtures (frozen data.md §4, testing.md §2)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.data_engine.contracts import (
    AnomalyInjection,
    AnomalyType,
    ShareEntry,
    SyntheticCompanyConfig,
)
from backend.data_engine.ingest.synthetic import (
    canonical_fixture_configs,
    generate_canonical_fixtures,
    generate_company,
)

IDENT_EPS = 1e-6


def val(x: float | None) -> float:
    """Narrow Optional numeric fields the generator always fills."""
    assert x is not None
    return x


def cfg(**kw: object) -> SyntheticCompanyConfig:
    return SyntheticCompanyConfig(**kw)  # pyright: ignore[reportCallIssue]


def hhi(entries: list[ShareEntry]) -> float:
    return sum(e.share**2 for e in entries)


def test_same_seed_same_config_identical_output() -> None:
    a = generate_company(cfg(seed=42)).model_dump_json()
    b = generate_company(SyntheticCompanyConfig(seed=42)).model_dump_json()
    assert a == b


def test_different_seed_different_output() -> None:
    a = generate_company(cfg(seed=1)).model_dump_json()
    b = generate_company(cfg(seed=2)).model_dump_json()
    assert a != b


def test_accounting_identities_hold_every_period() -> None:
    for config in (
        cfg(seed=1001, health="healthy"),
        cfg(seed=1002, health="stressed"),
        cfg(seed=1004, sector="services_saas"),
    ):
        for p in generate_company(config).periods:
            total_assets = val(p.total_assets)
            assert abs(total_assets - val(p.total_liabilities) - val(p.equity)) < IDENT_EPS
            assert abs(val(p.gross_profit) - (val(p.revenue) - val(p.cogs))) < IDENT_EPS
            current_assets = val(p.current_assets)
            assert abs(current_assets - (val(p.cash) + val(p.receivables) + val(p.inventory))) < (
                IDENT_EPS
            )
            assert current_assets >= val(p.cash)
            assert current_assets >= val(p.receivables)
            assert abs(val(p.total_debt) - (val(p.st_debt) + val(p.lt_debt))) < IDENT_EPS


def test_share_buckets_sum_to_one() -> None:
    for p in generate_company(cfg(seed=1005)).periods:
        for bucket in (p.customers, p.suppliers, p.products, p.regions):
            assert bucket is not None
            assert abs(sum(e.share for e in bucket) - 1.0) <= 0.01
            for entry in bucket:
                assert 0.0 <= entry.share <= 1.0


def test_privacy_hashing_customers_suppliers_only() -> None:
    p = generate_company(cfg(seed=1003)).periods[0]
    assert p.customers is not None and p.customers[0].name_hash is not None
    assert p.customers[0].name is None
    assert p.products is not None and p.products[0].name is not None
    assert p.products[0].name_hash is None


@pytest.mark.parametrize(
    ("profile", "lo", "hi"),
    [("dispersed", 0.05, 0.20), ("moderate", 0.10, 0.45), ("concentrated", 0.30, 0.60)],
)
def test_concentration_hhi_within_frozen_band(profile: str, lo: float, hi: float) -> None:
    for seed in (31, 32, 33, 34, 35):
        for p in generate_company(cfg(seed=seed, concentration=profile)).periods:
            value = hhi(p.customers or [])
            assert lo <= value <= hi, f"{profile} seed {seed}: HHI {value}"


def test_margin_collapse_injection_labelled_window() -> None:
    config = cfg(
        seed=2001,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.MARGIN_COLLAPSE, start_month=14, duration_months=4, magnitude=0.5
            )
        ],
    )
    company = generate_company(config)
    margins = [val(p.gross_profit) / val(p.revenue) for p in company.periods]
    inside = margins[13:17]  # months 14..17
    outside = [margins[i] for i in (11, 12, 17, 18)]
    assert max(inside) < min(outside), "injected window must show reduced gross margin"
    assert company.anomaly_labels[0].type is AnomalyType.MARGIN_COLLAPSE


def test_receivable_spike_injection() -> None:
    config = cfg(
        seed=2002,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.RECEIVABLE_SPIKE, start_month=20, duration_months=3, magnitude=0.8
            )
        ],
    )
    dso_series = [val(p.receivables) / val(p.revenue) for p in generate_company(config).periods]
    assert max(dso_series[19:22]) > 1.5 * min(dso_series[:18])


def test_cost_explosion_injection() -> None:
    config = cfg(
        seed=2003,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.COST_EXPLOSION, start_month=10, duration_months=2, magnitude=0.6
            )
        ],
    )
    ratios = [val(p.opex) / val(p.revenue) for p in generate_company(config).periods]
    assert max(ratios[9:11]) > 1.4 * min(ratios[:8])


def test_anomalies_never_break_identities() -> None:
    config = cfg(
        seed=2004,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.MARGIN_COLLAPSE, start_month=5, duration_months=3, magnitude=0.7
            ),
            AnomalyInjection(
                type=AnomalyType.COST_EXPLOSION, start_month=9, duration_months=2, magnitude=0.5
            ),
        ],
    )
    for p in generate_company(config).periods:
        assert abs(val(p.total_assets) - val(p.total_liabilities) - val(p.equity)) < IDENT_EPS
        assert abs(val(p.gross_profit) - (val(p.revenue) - val(p.cogs))) < IDENT_EPS


def test_annual_frequency_aggregation() -> None:
    company = generate_company(cfg(seed=7, frequency="annual", periods=3))
    assert len(company.periods) == 3
    assert all(p.frequency.value == "annual" and p.quarter is None for p in company.periods)
    for p in company.periods:
        assert abs(val(p.total_assets) - val(p.total_liabilities) - val(p.equity)) < IDENT_EPS
        assert abs(val(p.gross_profit) - (val(p.revenue) - val(p.cogs))) < IDENT_EPS
    monthly = generate_company(cfg(seed=7))
    annual_rev = val(company.periods[0].revenue)
    monthly_rev = sum(val(p.revenue) for p in monthly.periods[:12])
    assert annual_rev == pytest.approx(monthly_rev, rel=0.01)


def test_health_orders_runway_and_leverage() -> None:
    """Stressed companies show less cash and more leverage than healthy ones
    (envelope sanity; exact values are template choices)."""
    healthy = generate_company(cfg(seed=3001, health="healthy"))
    stressed = generate_company(cfg(seed=3001, health="stressed"))
    cash_h = np.mean([val(p.cash) / val(p.revenue) for p in healthy.periods])
    cash_s = np.mean([val(p.cash) / val(p.revenue) for p in stressed.periods])
    lev_h = np.mean([val(p.total_debt) / max(val(p.ebitda), 1.0) for p in healthy.periods])
    lev_s = np.mean([val(p.total_debt) / max(val(p.ebitda), 1.0) for p in stressed.periods])
    assert cash_h > cash_s
    assert lev_s > lev_h


def test_canonical_fixtures_frozen() -> None:
    configs = canonical_fixture_configs()
    assert set(configs) == {
        "mfg_healthy",
        "mfg_stressed",
        "saas_stable",
        "retail_seasonal",
        "mfg_concentrated_anomalies",
    }
    assert [c.seed for c in configs.values()] == [1001, 1002, 1003, 1004, 1005]
    fixtures = generate_canonical_fixtures()
    for key, company in fixtures.items():
        assert len(company.periods) == 24, key
        again = generate_company(configs[key])
        assert again.model_dump_json() == company.model_dump_json()
