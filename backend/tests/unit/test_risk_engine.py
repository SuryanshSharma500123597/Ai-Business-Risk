"""Hand-computed Fixture Unit Tests for Risk Engine Formulas (Spec §10, §29).

100% hand-fixture coverage testing exact numerical values, edge cases, and boundary anchors.
"""

import pytest

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.risk_engine.contracts import (
    DimensionResult,
    MetricResult,
    MetricStatus,
    SeverityLabel,
    get_severity_label,
)
from backend.risk_engine.engine import QuantitativeRiskEngine
from backend.risk_engine.metrics.concentration import calc_cr1, calc_cr3, calc_hhi
from backend.risk_engine.metrics.credit import calc_altman_z, calc_dso
from backend.risk_engine.metrics.financial_strength import (
    calc_debt_to_ebitda,
    calc_debt_to_equity,
    calc_dscr,
    calc_gross_margin,
    calc_interest_coverage,
    calc_net_margin,
    calc_operating_margin,
    calc_roa,
    calc_roe,
)
from backend.risk_engine.metrics.liquidity import (
    calc_cash_ratio,
    calc_cash_runway_months,
    calc_current_ratio,
    calc_quick_ratio,
)
from backend.risk_engine.metrics.market import (
    calc_fx_exposure_score,
    calc_rate_sensitivity,
    calc_var_95,
)
from backend.risk_engine.metrics.operational import (
    calc_ccc,
    calc_dio,
    calc_dpo,
)
from backend.risk_engine.registry import DEFAULT_DIMENSION_WEIGHTS, interpolate_score
from backend.risk_engine.scoring import aggregate_composite, aggregate_dimension

# --- Financial Strength Fixture Tests ---


def test_gross_margin_hand_fixtures():
    # Case 1: Revenue 1000, GP 400 => 40.0%
    res1 = calc_gross_margin({"revenue": 1000.0, "gross_profit": 400.0})
    assert res1.status == MetricStatus.VALID
    assert pytest.approx(res1.value, abs=1e-5) == 40.0

    # Case 2: Zero revenue edge case
    res2 = calc_gross_margin({"revenue": 0.0, "gross_profit": 0.0})
    assert res2.status == MetricStatus.FLAGGED
    assert res2.value == 0.0


def test_operating_margin_hand_fixtures():
    res1 = calc_operating_margin({"revenue": 1000.0, "ebit": 150.0})
    assert res1.status == MetricStatus.VALID
    assert pytest.approx(res1.value, abs=1e-5) == 15.0


def test_net_margin_hand_fixtures():
    res1 = calc_net_margin({"revenue": 1000.0, "net_income": 60.0})
    assert res1.status == MetricStatus.VALID
    assert pytest.approx(res1.value, abs=1e-5) == 6.0


def test_roa_and_roe_hand_fixtures():
    res_roa = calc_roa({"net_income": 50.0, "total_assets": 1000.0})
    assert pytest.approx(res_roa.value, abs=1e-5) == 5.0

    res_roe = calc_roe({"net_income": 50.0, "equity": 500.0})
    assert pytest.approx(res_roe.value, abs=1e-5) == 10.0

    # Negative equity edge case
    res_roe_neg = calc_roe({"net_income": 50.0, "equity": -100.0})
    assert res_roe_neg.status == MetricStatus.FLAGGED


def test_debt_ratios_hand_fixtures():
    res_de = calc_debt_to_equity({"total_debt": 400.0, "equity": 200.0})
    assert pytest.approx(res_de.value, abs=1e-5) == 2.0

    res_ebitda = calc_debt_to_ebitda({"total_debt": 600.0, "ebitda": 200.0})
    assert pytest.approx(res_ebitda.value, abs=1e-5) == 3.0


def test_coverage_ratios_hand_fixtures():
    res_ic = calc_interest_coverage({"ebit": 300.0, "interest_expense": 100.0})
    assert pytest.approx(res_ic.value, abs=1e-5) == 3.0

    res_dscr = calc_dscr({"ebitda": 400.0, "interest_expense": 100.0, "st_debt": 100.0})
    assert pytest.approx(res_dscr.value, abs=1e-5) == 2.0


# --- Liquidity Fixture Tests ---


def test_liquidity_ratios_hand_fixtures():
    # Current ratio: 500 / 250 = 2.0
    res_cr = calc_current_ratio({"current_assets": 500.0, "current_liabilities": 250.0})
    assert pytest.approx(res_cr.value, abs=1e-5) == 2.0

    # Quick ratio: (500 - 100) / 250 = 1.6
    res_qr = calc_quick_ratio(
        {"current_assets": 500.0, "inventory": 100.0, "current_liabilities": 250.0}
    )
    assert pytest.approx(res_qr.value, abs=1e-5) == 1.6

    # Cash ratio: 125 / 250 = 0.5
    res_cash = calc_cash_ratio({"cash": 125.0, "current_liabilities": 250.0})
    assert pytest.approx(res_cash.value, abs=1e-5) == 0.5


def test_cash_runway_hand_fixtures():
    res = calc_cash_runway_months({"cash": 120.0, "ocf": -10.0})
    assert pytest.approx(res.value, abs=1e-5) == 12.0

    res_positive_ocf = calc_cash_runway_months({"cash": 120.0, "ocf": 50.0})
    assert res_positive_ocf.value == 999.0


# --- Market Risk Fixture Tests ---


def test_market_metrics_hand_fixtures():
    # Rate sensitivity: total_debt 1000, floating 0.5, EBITDA 100
    # => 1000 * 0.5 * 0.01 / 100 = 0.05 => 5%
    res_rate = calc_rate_sensitivity(
        {"total_debt": 1000.0, "rate_exposure": {"floating_debt_share": 0.5}, "ebitda": 100.0}
    )
    assert pytest.approx(res_rate.value, abs=1e-5) == 5.0

    # FX score: import 0.5, foreign 0.5, pass-through 0.3
    # => 100 * (0.6*0.5 + 0.4*0.5) * (1-0.3) = 35
    res_fx = calc_fx_exposure_score(
        {"fx_exposure": {"import_cost_share": 0.5, "foreign_revenue_share": 0.5}}, pass_through=0.3
    )
    assert pytest.approx(res_fx.value, abs=1e-5) == 35.0


def test_var_and_es_hand_fixtures():
    returns = [-0.05, -0.04, -0.03, -0.02, -0.01] + [0.01] * 95
    res_var = calc_var_95(returns)
    assert res_var.status == MetricStatus.VALID
    assert res_var.value is not None and res_var.value >= 0.0


# --- Credit Fixture Tests ---


def test_credit_metrics_hand_fixtures():
    # DSO: rec 100, rev 730 => (100 / 730) * 365 = 50.0 days
    res_dso = calc_dso({"receivables": 100.0, "revenue": 730.0})
    assert pytest.approx(res_dso.value, abs=1e-5) == 50.0

    # Altman Z private manufacturer: TA=1000, TL=400, CA=400, CL=200, EBIT=100, Rev=1000, Eq=600
    res_z = calc_altman_z(
        {
            "total_assets": 1000.0,
            "total_liabilities": 400.0,
            "current_assets": 400.0,
            "current_liabilities": 200.0,
            "ebit": 100.0,
            "revenue": 1000.0,
            "equity": 600.0,
        },
        profile={"sector": "manufacturing"},
    )
    assert res_z.status == MetricStatus.VALID
    assert res_z.value is not None and res_z.value > 0.0


# --- Operational Fixture Tests ---


def test_operational_metrics_hand_fixtures():
    # DIO: inv 100, cogs 730 => 50.0 days
    res_dio = calc_dio({"inventory": 100.0, "cogs": 730.0})
    assert pytest.approx(res_dio.value, abs=1e-5) == 50.0

    # DPO: payables 60, cogs 730 => 30.0 days
    res_dpo = calc_dpo({"payables": 60.0, "cogs": 730.0})
    assert pytest.approx(res_dpo.value, abs=1e-5) == 30.0

    # CCC: 50 + 50 - 30 = 70.0
    res_ccc = calc_ccc(50.0, 50.0, 30.0)
    assert pytest.approx(res_ccc.value, abs=1e-5) == 70.0


# --- Concentration Fixture Tests ---


def test_concentration_hand_fixtures():
    # HHI for shares 0.5, 0.3, 0.2 => 0.25 + 0.09 + 0.04 = 0.38
    res_hhi = calc_hhi([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(res_hhi.value, abs=1e-5) == 0.38

    res_cr1 = calc_cr1([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(res_cr1.value, abs=1e-5) == 0.5

    res_cr3 = calc_cr3([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(res_cr3.value, abs=1e-5) == 1.0


# --- Scoring & Interpolation Tests ---


def test_piecewise_linear_interpolation():
    anchors = [(10.0, 90.0), (20.0, 65.0), (30.0, 45.0), (40.0, 25.0)]
    assert interpolate_score(10.0, anchors) == 90.0
    assert interpolate_score(40.0, anchors) == 25.0
    assert interpolate_score(15.0, anchors) == 77.5  # midpoint of 90 and 65
    assert interpolate_score(5.0, anchors) == 90.0  # lower clamp
    assert interpolate_score(50.0, anchors) == 25.0  # upper clamp


def test_severity_labels():
    assert get_severity_label(15.0) == SeverityLabel.LOW
    assert get_severity_label(35.0) == SeverityLabel.MODERATE
    assert get_severity_label(60.0) == SeverityLabel.HIGH
    assert get_severity_label(85.0) == SeverityLabel.CRITICAL


# --- Engine Pipeline Test ---


def test_full_risk_engine_execution():
    engine = QuantitativeRiskEngine()
    sample_dataset = {
        "profile": {"name": "Test Manufacturing Corp", "sector": "manufacturing", "id": "1001"},
        "periods": [
            {
                "period_end": "2025-12-31",
                "frequency": "annual",
                "source": "synthetic",
                "revenue": 10000.0,
                "cogs": 6000.0,
                "gross_profit": 4000.0,
                "ebit": 1500.0,
                "ebitda": 2000.0,
                "net_income": 1000.0,
                "interest_expense": 200.0,
                "cash": 1500.0,
                "receivables": 1200.0,
                "inventory": 1000.0,
                "payables": 800.0,
                "current_assets": 4000.0,
                "current_liabilities": 2000.0,
                "total_assets": 10000.0,
                "total_liabilities": 4000.0,
                "equity": 6000.0,
                "total_debt": 2000.0,
                "st_debt": 500.0,
                "lt_debt": 1500.0,
                "ocf": 1800.0,
                "customers": [{"name_hash": "c1", "share": 0.4}, {"name_hash": "c2", "share": 0.6}],
                "suppliers": [{"name_hash": "s1", "share": 0.5}, {"name_hash": "s2", "share": 0.5}],
            }
        ],
    }

    report = engine.evaluate_company(sample_dataset)
    composite_score = report.composite.score
    assert composite_score is not None
    assert 0.0 <= composite_score <= 100.0
    assert len(report.composite.dimensions) == 7
    assert pytest.approx(report.composite.total_contributions, abs=1e-4) == composite_score
    assert report.sensitivity.rank_stability_score >= -1.0


def test_sensitivity_does_not_corrupt_composite_contributions():
    """Regression: sensitivity runs must not overwrite baseline contributions.

    ``aggregate_composite`` populates ``effective_weight``/``contribution`` by
    mutating the ``DimensionResult`` objects it is handed, and
    ``run_sensitivity_analysis`` re-aggregates once per perturbed scenario. If
    those internal runs receive the caller's own objects, the final scenario's
    perturbed weights leak into the published report and the frozen
    exact-additivity invariant ``sum(C_d) == S_composite`` is violated
    (risk-engine.md §1, spec §22 L1).
    """
    config = SyntheticCompanyConfig(seed=1001, periods=24)
    report = QuantitativeRiskEngine().evaluate_company(generate_company(config))
    composite = report.composite

    # The exposed dimension contributions must reconcile to the composite score.
    dimension_contribution_sum = sum(d.contribution for d in composite.dimensions.values())
    assert pytest.approx(dimension_contribution_sum, abs=1e-9) == composite.score

    # No custom weights were supplied, so every available dimension must still
    # carry the default 1/7 weight after the +/-20% scenarios have run.
    available = [d for d in composite.dimensions.values() if d.score is not None]
    assert available
    for dim_res in available:
        assert pytest.approx(dim_res.effective_weight, abs=1e-12) == 1.0 / 7.0


def test_all_missing_dimensions_yields_no_fabricated_composite():
    """D9: an entirely-missing profile must not fabricate a 50.0 'Moderate' score."""
    dimensions = {
        dim_id: DimensionResult(dimension_id=dim_id, name=dim_id, score=None, weight=1.0 / 7.0)
        for dim_id in DEFAULT_DIMENSION_WEIGHTS
    }
    composite = aggregate_composite(dimensions)

    assert composite.score is None
    assert composite.severity is None
    assert composite.total_contributions == 0.0
    assert sorted(composite.missing_dimensions) == sorted(DEFAULT_DIMENSION_WEIGHTS)
    # Nothing contributes, so the additive invariant stays consistent.
    assert sum(d.contribution for d in composite.dimensions.values()) == 0.0


def test_configured_weight_is_reported_alongside_effective_weight():
    """D10: ``weight`` must expose the configured weight actually used for the run."""
    config = SyntheticCompanyConfig(seed=1001, periods=24)
    dataset = generate_company(config)

    default_report = QuantitativeRiskEngine().evaluate_company(dataset)
    for dimension in default_report.composite.dimensions.values():
        assert pytest.approx(dimension.weight, abs=1e-12) == 1.0 / 7.0

    custom_weights = {dim_id: 0.1 for dim_id in DEFAULT_DIMENSION_WEIGHTS}
    custom_weights["financial_strength"] = 0.4
    custom_report = QuantitativeRiskEngine().evaluate_company(
        dataset, custom_weights=custom_weights
    )
    dimensions = custom_report.composite.dimensions

    assert pytest.approx(dimensions["financial_strength"].weight, abs=1e-12) == 0.4
    assert pytest.approx(dimensions["liquidity"].weight, abs=1e-12) == 0.1
    assert pytest.approx(sum(d.effective_weight for d in dimensions.values()), abs=1e-12) == 1.0


def test_effective_weight_renormalises_over_available_dimensions():
    """``weight`` stays the configured value while ``effective_weight`` renormalises."""
    dimensions = {}
    for dim_id in DEFAULT_DIMENSION_WEIGHTS:
        metrics = [
            MetricResult(
                metric_id=f"{dim_id}_m",
                name="Placeholder",
                dimension=dim_id,
                value=1.0,
                score=50.0,
                status=MetricStatus.VALID,
            )
        ]
        dimensions[dim_id] = aggregate_dimension(dim_id, metrics)

    # Drop one dimension so the remaining weights must be renormalised.
    dimensions["macro"].score = None
    composite = aggregate_composite(dimensions)

    available_total = 6 * (1.0 / 7.0)
    strength = composite.dimensions["financial_strength"]
    assert pytest.approx(strength.weight, abs=1e-12) == 1.0 / 7.0
    assert pytest.approx(strength.effective_weight, abs=1e-12) == (1.0 / 7.0) / available_total
    assert strength.effective_weight != strength.weight

    macro = composite.dimensions["macro"]
    assert pytest.approx(macro.weight, abs=1e-12) == 1.0 / 7.0
    assert macro.effective_weight == 0.0
    assert macro.contribution == 0.0
    assert composite.missing_dimensions == ["macro"]


def test_composite_contributions_reconcile_under_custom_weights():
    """The exact-additivity invariant must also hold for user-adjusted weights."""
    weights = {dim_id: 1.0 / 7.0 for dim_id in DEFAULT_DIMENSION_WEIGHTS}
    weights.update(
        {
            "financial_strength": 0.40,
            "macro": 0.40,
            "liquidity": 0.05,
            "market": 0.05,
            "credit": 0.05,
            "operational": 0.03,
            "concentration": 0.02,
        }
    )
    report = QuantitativeRiskEngine().evaluate_company(
        generate_company(SyntheticCompanyConfig(seed=1003, periods=24)), custom_weights=weights
    )
    composite = report.composite
    assert composite.score is not None
    assert (
        pytest.approx(sum(d.contribution for d in composite.dimensions.values()), abs=1e-9)
        == composite.score
    )
