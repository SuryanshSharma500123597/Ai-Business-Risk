"""Hand-computed fixture tests for every registry formula (NFR2, risk-engine.md §10.1).

One fixture per registered metric id (``test_fixture_<metric_id>``), each covering the
typical case plus the edge case from its frozen table row. Coverage of the *whole*
registry is enforced by ``test_registry_coverage.py``, which walks
``build_default_registry()`` and asserts a fixture exists per formula id.

Expected values are hand-derived from the frozen definitions (risk-engine.md §2-§8,
spec §17.1) rather than by re-running the implementation.
"""

import math

import pytest

from backend.risk_engine.contracts import MetricResult, MetricStatus
from backend.risk_engine.metrics import (
    calc_altman_z,
    calc_beta,
    calc_cash_ratio,
    calc_cash_runway_months,
    calc_ccc,
    calc_commodity_exposure_score,
    calc_cr1,
    calc_cr3,
    calc_current_ratio,
    calc_debt_to_ebitda,
    calc_debt_to_equity,
    calc_dio,
    calc_dpo,
    calc_dscr,
    calc_dso,
    calc_equity_volatility,
    calc_es_95,
    calc_fx_exposure_score,
    calc_gdp_sensitivity,
    calc_gross_margin,
    calc_hhi,
    calc_inflation_passthrough,
    calc_interest_coverage,
    calc_macro_fx_volatility,
    calc_merton_dd,
    calc_net_margin,
    calc_operating_margin,
    calc_opex_rigidity,
    calc_quick_ratio,
    calc_rate_environment,
    calc_rate_sensitivity,
    calc_receivable_trend,
    calc_revenue_volatility,
    calc_roa,
    calc_roe,
    calc_single_source_flags,
    calc_st_obligation_coverage,
    calc_var_95,
)
from backend.risk_engine.metrics.credit import _ALTMAN_CUTOFFS, _altman_anchors
from backend.risk_engine.registry import build_default_registry, interpolate_score
from backend.risk_engine.scoring import score_metric


def _anchors(metric_id: str) -> list[tuple[float, float]]:
    definition = build_default_registry().get(metric_id)
    assert definition is not None
    return definition.anchors


def _score(metric_id: str, result: MetricResult) -> float | None:
    """Score a result with the anchors the registry actually uses for that metric."""
    return score_metric(result, _anchors(metric_id)).score


def _alternating_returns(count: int, magnitude: float = 0.01) -> list[float]:
    """Returns alternating +m, -m so the mean is exactly zero when count is even."""
    return [magnitude if i % 2 == 0 else -magnitude for i in range(count)]


# --------------------------------------------------------------------------
# Financial Strength (risk-engine.md §2)
# --------------------------------------------------------------------------


def test_fixture_gross_margin():
    typical = calc_gross_margin({"revenue": 1000.0, "gross_profit": 400.0})
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 40.0
    # 40% sits exactly on the 40->25 anchor
    assert pytest.approx(_score("gross_margin", typical), abs=1e-9) == 25.0

    edge = calc_gross_margin({"revenue": 0.0, "gross_profit": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("gross_margin", edge) == 100.0


def test_fixture_operating_margin():
    typical = calc_operating_margin({"revenue": 1000.0, "ebit": 150.0})
    assert pytest.approx(typical.value, abs=1e-9) == 15.0
    # 15% sits on the 15->25 anchor
    assert pytest.approx(_score("operating_margin", typical), abs=1e-9) == 25.0

    edge = calc_operating_margin({"revenue": 0.0, "ebit": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("operating_margin", edge) == 100.0


def test_fixture_net_margin():
    typical = calc_net_margin({"revenue": 1000.0, "net_income": 60.0})
    assert pytest.approx(typical.value, abs=1e-9) == 6.0
    # 6% sits on the 6->45 anchor
    assert pytest.approx(_score("net_margin", typical), abs=1e-9) == 45.0

    edge = calc_net_margin({"revenue": 0.0, "net_income": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("net_margin", edge) == 100.0


def test_fixture_roa():
    typical = calc_roa({"net_income": 50.0, "total_assets": 1000.0})
    assert pytest.approx(typical.value, abs=1e-9) == 5.0
    # 5% sits two thirds of the way from the 3->55 to the 6->35 anchor
    assert pytest.approx(_score("roa", typical), abs=1e-9) == 125.0 / 3.0

    edge = calc_roa({"net_income": 0.0, "total_assets": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("roa", edge) == 100.0


def test_fixture_roe():
    typical = calc_roe({"net_income": 50.0, "equity": 500.0})
    assert pytest.approx(typical.value, abs=1e-9) == 10.0
    # 10% sits two sevenths of the way from the 8->55 to the 15->35 anchor
    assert pytest.approx(_score("roe", typical), abs=1e-9) == 345.0 / 7.0

    for equity in (-100.0, 0.0):
        edge = calc_roe({"net_income": 50.0, "equity": equity})
        assert edge.status == MetricStatus.FLAGGED
        assert _score("roe", edge) == 100.0


def test_fixture_debt_to_equity():
    typical = calc_debt_to_equity({"total_debt": 400.0, "equity": 200.0})
    assert pytest.approx(typical.value, abs=1e-9) == 2.0
    # 2.0 sits on the 2->55 anchor
    assert pytest.approx(_score("debt_to_equity", typical), abs=1e-9) == 55.0

    # Edge case: equity <= 0 -> worst band. Must not raise (previously produced inf).
    for equity in (-100.0, 0.0):
        edge = calc_debt_to_equity({"total_debt": 400.0, "equity": equity})
        assert edge.status == MetricStatus.FLAGGED
        assert edge.value is None
        assert _score("debt_to_equity", edge) == 100.0


def test_fixture_debt_to_ebitda():
    typical = calc_debt_to_ebitda({"total_debt": 600.0, "ebitda": 200.0})
    assert pytest.approx(typical.value, abs=1e-9) == 3.0
    # 3.0 sits on the 3->35 anchor
    assert pytest.approx(_score("debt_to_ebitda", typical), abs=1e-9) == 35.0

    # Edge case: EBITDA <= 0 -> worst band. Must not raise (previously produced inf).
    edge = calc_debt_to_ebitda({"total_debt": 600.0, "ebitda": -50.0})
    assert edge.status == MetricStatus.FLAGGED
    assert edge.value is None
    assert _score("debt_to_ebitda", edge) == 100.0


def test_fixture_interest_coverage():
    """Formula is frozen (spec §17.1: EBIT / interest); bands are NOT frozen (Q1)."""
    typical = calc_interest_coverage({"ebit": 300.0, "interest_expense": 100.0})
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 3.0

    # Spec §17.1: interest > 0 required; <=0 EBIT -> worst band. Asserted
    # band-agnostically because risk-engine.md §2 defines no anchors for this metric.
    worst_band = max(score for _, score in _anchors("interest_coverage"))
    edge = calc_interest_coverage({"ebit": -100.0, "interest_expense": 100.0})
    assert _score("interest_coverage", edge) == worst_band


def test_fixture_dscr():
    """Formula is frozen (spec §17.1: EBITDA / (interest + current portion LTD))."""
    typical = calc_dscr({"ebitda": 400.0, "interest_expense": 100.0, "st_debt": 100.0})
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 2.0

    missing = calc_dscr({"ebitda": None})
    assert missing.status == MetricStatus.MISSING_INPUT


# --------------------------------------------------------------------------
# Liquidity (risk-engine.md §3)
# --------------------------------------------------------------------------


def test_fixture_current_ratio():
    typical = calc_current_ratio({"current_assets": 500.0, "current_liabilities": 250.0})
    assert pytest.approx(typical.value, abs=1e-9) == 2.0
    # 2.0 sits on the 2->25 anchor
    assert pytest.approx(_score("current_ratio", typical), abs=1e-9) == 25.0

    edge = calc_current_ratio({"current_assets": 500.0, "current_liabilities": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("current_ratio", edge) == 5.0


def test_fixture_quick_ratio():
    typical = calc_quick_ratio(
        {"current_assets": 500.0, "inventory": 100.0, "current_liabilities": 250.0}
    )
    assert pytest.approx(typical.value, abs=1e-9) == 1.6

    edge = calc_quick_ratio(
        {"current_assets": 500.0, "inventory": 100.0, "current_liabilities": 0.0}
    )
    assert edge.status == MetricStatus.FLAGGED
    assert _score("quick_ratio", edge) == 5.0


def test_fixture_cash_ratio():
    typical = calc_cash_ratio({"cash": 125.0, "current_liabilities": 250.0})
    assert pytest.approx(typical.value, abs=1e-9) == 0.5
    # 0.5 sits on the 0.5->45 anchor
    assert pytest.approx(_score("cash_ratio", typical), abs=1e-9) == 45.0

    edge = calc_cash_ratio({"cash": 125.0, "current_liabilities": 0.0})
    assert edge.status == MetricStatus.FLAGGED
    assert _score("cash_ratio", edge) == 5.0


def test_fixture_cash_runway_months():
    typical = calc_cash_runway_months({"cash": 120.0, "ocf": -10.0})
    assert pytest.approx(typical.value, abs=1e-9) == 12.0
    # 12 months sits on the 12->45 anchor
    assert pytest.approx(_score("cash_runway_months", typical), abs=1e-9) == 45.0

    # Edge case: ocf >= 0 -> score 5, "n/a" label (not constrained)
    edge = calc_cash_runway_months({"cash": 120.0, "ocf": 50.0})
    assert edge.status == MetricStatus.FLAGGED
    assert edge.message is not None and "n/a" in edge.message
    assert _score("cash_runway_months", edge) == 5.0


def test_fixture_st_obligation_coverage():
    typical = calc_st_obligation_coverage({"cash": 1000.0, "st_debt": 1000.0})
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 1.0
    # 1.0 sits on the 1.0->50 anchor
    assert pytest.approx(_score("st_obligation_coverage", typical), abs=1e-9) == 50.0

    missing = calc_st_obligation_coverage({"cash": None})
    assert missing.status == MetricStatus.MISSING_INPUT


# --------------------------------------------------------------------------
# Market / External-Price Exposure (risk-engine.md §4)
# --------------------------------------------------------------------------


def test_fixture_rate_sensitivity():
    # 1000 * 0.5 * 0.01 = 5 interest increase; 5 / 100 EBITDA = 5%
    typical = calc_rate_sensitivity(
        {"total_debt": 1000.0, "rate_exposure": {"floating_debt_share": 0.5}, "ebitda": 100.0}
    )
    assert pytest.approx(typical.value, abs=1e-9) == 5.0
    # 5% sits on the 5->40 anchor
    assert pytest.approx(_score("rate_sensitivity", typical), abs=1e-9) == 40.0

    # Edge case: EBITDA <= 0 -> 100
    edge = calc_rate_sensitivity(
        {"total_debt": 1000.0, "rate_exposure": {"floating_debt_share": 0.5}, "ebitda": -10.0}
    )
    assert edge.status == MetricStatus.FLAGGED
    assert _score("rate_sensitivity", edge) == 100.0


def test_fixture_fx_exposure_score():
    # 100 * (0.6*0.5 + 0.4*0.5) * (1 - 0.3) = 35
    typical = calc_fx_exposure_score(
        {"fx_exposure": {"import_cost_share": 0.5, "foreign_revenue_share": 0.5}},
        pass_through=0.3,
    )
    assert pytest.approx(typical.value, abs=1e-9) == 35.0

    # Full pass-through capacity removes the exposure entirely
    hedged = calc_fx_exposure_score(
        {"fx_exposure": {"import_cost_share": 0.5, "foreign_revenue_share": 0.5}},
        pass_through=1.0,
    )
    assert pytest.approx(hedged.value, abs=1e-9) == 0.0


def test_fixture_commodity_exposure_score():
    # 100 * 0.4 * (1 - 0.3) = 28
    typical = calc_commodity_exposure_score(
        {"commodity_exposure": {"cost_share": 0.4}}, pass_through=0.3
    )
    assert pytest.approx(typical.value, abs=1e-9) == 28.0
    # 28 is midway between the 25->40 and 40->60 anchors
    assert pytest.approx(_score("commodity_exposure_score", typical), abs=1e-9) == 44.0

    none_reported = calc_commodity_exposure_score({"commodity_exposure": None})
    assert pytest.approx(none_reported.value, abs=1e-9) == 0.0


def test_fixture_revenue_volatility():
    # Revenues alternate x1.02 / x0.98 -> returns alternate +2% / -2% for exactly
    # 30 returns (mean 0), so sigma = 0.02 and the annualised figure is 0.02*sqrt(12).
    revenues = [1000.0]
    for i in range(30):
        revenues.append(revenues[-1] * (1.02 if i % 2 == 0 else 0.98))
    history = [{"revenue": value} for value in revenues]

    typical = calc_revenue_volatility(history)
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 0.02 * math.sqrt(12) * 100.0

    thin = calc_revenue_volatility(history[:5])
    assert thin.status == MetricStatus.INSUFFICIENT_HISTORY


def test_fixture_equity_volatility():
    # 120 alternating +/-1% returns -> mean 0, sigma = 1%, annualised by sqrt(252).
    typical = calc_equity_volatility(_alternating_returns(120, 0.01))
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 0.01 * math.sqrt(252) * 100.0

    # Listed mode only: fewer than 60 observations is unavailable
    assert calc_equity_volatility(None).status == MetricStatus.UNAVAILABLE
    assert calc_equity_volatility(_alternating_returns(59)).status == MetricStatus.UNAVAILABLE


def test_fixture_beta():
    # Asset returns are exactly twice the market returns, so beta = 2 by construction.
    market = _alternating_returns(120, 0.01)
    asset = [2.0 * r for r in market]

    typical = calc_beta(asset, market)
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 2.0

    # A series regressed on itself is always 1.0 (this is what the engine currently does)
    assert pytest.approx(calc_beta(market, market).value, abs=1e-9) == 1.0

    assert calc_beta(None, market).status == MetricStatus.UNAVAILABLE
    assert calc_beta(market[:119], market[:119]).status == MetricStatus.UNAVAILABLE


def test_fixture_var_95():
    # 95 small gains and 5 losses; the 95th percentile loss lands on the smallest
    # loss (0.01 -> 1%), and the alpha=0.95 tail mean is 3%.
    returns = [0.01] * 95 + [-0.05, -0.04, -0.03, -0.02, -0.01]

    typical = calc_var_95(returns)
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 1.0

    assert calc_var_95(None).status == MetricStatus.UNAVAILABLE
    assert calc_var_95(returns[:59]).status == MetricStatus.UNAVAILABLE


def test_fixture_es_95():
    returns = [0.01] * 95 + [-0.05, -0.04, -0.03, -0.02, -0.01]

    typical = calc_es_95(returns)
    assert typical.status == MetricStatus.VALID
    # Tail beyond the 95th percentile = mean(1%, 2%, 3%, 4%, 5%) = 3%
    assert pytest.approx(typical.value, abs=1e-9) == 3.0

    assert calc_es_95(None).status == MetricStatus.UNAVAILABLE
    assert calc_es_95(returns[:59]).status == MetricStatus.UNAVAILABLE


# --------------------------------------------------------------------------
# Credit (risk-engine.md §5, §9)
# --------------------------------------------------------------------------


def test_fixture_dso():
    # (100 / 730) * 365 = 50 days
    typical = calc_dso({"receivables": 100.0, "revenue": 730.0})
    assert pytest.approx(typical.value, abs=1e-9) == 50.0
    # 50 sits one third of the way from the 45->35 to the 60->50 anchor
    assert pytest.approx(_score("dso", typical), abs=1e-9) == 40.0

    zero_revenue = calc_dso({"receivables": 100.0, "revenue": 0.0})
    assert zero_revenue.status == MetricStatus.FLAGGED


def test_fixture_receivables_concentration():
    # Reuses the HHI definition; 0.5^2 + 0.3^2 + 0.2^2 = 0.38
    typical = calc_hhi([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(typical.value, abs=1e-9) == 0.38
    # Single customer holds everything -> HHI = 1.0 (degenerate)
    degenerate = calc_hhi([{"share": 1.0}])
    assert pytest.approx(degenerate.value, abs=1e-9) == 1.0


def test_fixture_receivable_trend():
    # Hold revenue at 365 so DSO == receivables; receivables rise by 1/day per
    # period -> slope is exactly 1.0 day/period -> 12.0 days/year.
    history = [{"receivables": 30.0 + i, "revenue": 365.0} for i in range(12)]
    typical = calc_receivable_trend(history)
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 12.0
    # 12 sits between the 10->40 and 20->55 anchors
    assert pytest.approx(_score("receivable_trend", typical), abs=1e-9) == 43.0

    assert calc_receivable_trend(history[:7]).status == MetricStatus.INSUFFICIENT_HISTORY


def test_altman_variant_cutoff_mapping():
    """D3: each variant keeps its own cutoffs; the original-Z cutoffs are not reused."""
    original = _altman_anchors(*_ALTMAN_CUTOFFS["Z"])
    private = _altman_anchors(*_ALTMAN_CUTOFFS["Z'"])
    non_mfg = _altman_anchors(*_ALTMAN_CUTOFFS["Z''"])

    assert original == [(0.0, 100.0), (1.81, 60.0), (2.99, 10.0)]
    assert private == [(0.0, 100.0), (1.23, 60.0), (2.675, 10.0)]
    assert non_mfg == [(0.0, 100.0), (1.1, 60.0), (2.6, 10.0)]

    for anchors, distress, safe in (
        (original, 1.81, 2.99),
        (private, 1.23, 2.675),
        (non_mfg, 1.1, 2.6),
    ):
        # D2: below the distress cut-off the mapping is linear to 100 at Z = 0.
        assert interpolate_score(0.0, anchors) == 100.0
        assert interpolate_score(distress, anchors) == 60.0
        assert interpolate_score(safe, anchors) == 10.0
        assert interpolate_score(safe + 5.0, anchors) == 10.0

    # Halfway between Z=0 (100) and the Z' distress cut-off (60) is exactly 80.
    assert pytest.approx(interpolate_score(0.615, private), abs=1e-9) == 80.0
    # A deep-distress value is no longer clamped at 60.
    assert interpolate_score(-1.0, private) == 100.0

    # The same Z scores differently per variant precisely because cutoffs differ.
    scores = [interpolate_score(2.5, anchors) for anchors in (original, private, non_mfg)]
    assert all(score is not None for score in scores)
    s0, s1, s2 = scores
    assert s0 is not None and s1 is not None and s2 is not None
    assert s0 > s1 > s2


def test_fixture_altman_z_distance():
    # x1=0.2, x2=0.05, x3=0.1, x4=equity/500, x5=2.0 -> hand-computable variants.
    period = {
        "total_assets": 1000.0,
        "total_liabilities": 500.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,
        "net_income": 50.0,
        "ebit": 100.0,
        "revenue": 2000.0,
        "equity": 600.0,
    }

    # 0.717*.2 + 0.847*.05 + 3.107*.1 + 0.420*1.2 + 0.998*2.0 = 2.99645
    private = calc_altman_z(period, profile={"sector": "manufacturing"})
    assert private.inputs_used["variant"] == "Z' (Private Manufacturer)"
    assert pytest.approx(private.value, abs=1e-9) == 2.99645
    assert _score("altman_z_distance", private) == 10.0

    # 1.2*.2 + 1.4*.05 + 3.3*.1 + 0.6*1.2 + 1.0*2.0 = 3.36
    public = calc_altman_z(
        period, profile={"sector": "manufacturing", "is_public": True}, market_equity=600.0
    )
    assert public.inputs_used["variant"] == "Z (Public Manufacturer)"
    assert pytest.approx(public.value, abs=1e-9) == 3.36
    assert _score("altman_z_distance", public) == 10.0

    # 6.56*.2 + 3.26*.05 + 6.72*.1 + 1.05*1.2 = 3.407
    non_mfg = calc_altman_z(period, profile={"sector": "retail"})
    assert non_mfg.inputs_used["variant"] == "Z'' (Non-Manufacturer)"
    assert pytest.approx(non_mfg.value, abs=1e-9) == 3.407
    assert _score("altman_z_distance", non_mfg) == 10.0


def test_fixture_merton_dd():
    # DD = [ln(V/D) + (mu - sigma^2/2)T] / (sigma*sqrt(T))
    typical = calc_merton_dd(1000.0, 500.0, 0.3)
    assert typical.status == MetricStatus.VALID
    expected_dd = (math.log(2.0) + (0.05 - 0.5 * 0.3**2)) / 0.3
    assert pytest.approx(typical.value, abs=1e-9) == expected_dd
    pd_approx = typical.inputs_used["pd"]
    assert 0.0 < pd_approx < 0.05

    # Listed mode only, off by default -> unavailable when volatility is unknown
    assert calc_merton_dd(1000.0, 400.0, None).status == MetricStatus.UNAVAILABLE
    assert calc_merton_dd(None, None, None).status == MetricStatus.UNAVAILABLE


# --------------------------------------------------------------------------
# Operational (risk-engine.md §6)
# --------------------------------------------------------------------------


def test_fixture_dio():
    # (100 / 730) * 365 = 50 days
    typical = calc_dio({"inventory": 100.0, "cogs": 730.0})
    assert pytest.approx(typical.value, abs=1e-9) == 50.0
    # 50 sits two thirds of the way from the 30->20 to the 60->40 anchor
    assert pytest.approx(_score("dio", typical), abs=1e-9) == 100.0 / 3.0

    # Edge case: cogs=0 -> skip (no score, excluded from the dimension mean)
    skipped = calc_dio({"inventory": 100.0, "cogs": 0.0})
    assert skipped.status == MetricStatus.UNAVAILABLE
    assert skipped.value is None
    assert _score("dio", skipped) is None


def test_fixture_dpo():
    # (60 / 730) * 365 = 30 days
    typical = calc_dpo({"payables": 60.0, "cogs": 730.0})
    assert pytest.approx(typical.value, abs=1e-9) == 30.0
    # 30 sits on the 30->40 anchor (two-sided U-curve)
    assert pytest.approx(_score("dpo", typical), abs=1e-9) == 40.0


def test_fixture_ccc():
    # 50 + 50 - 30 = 70 days
    typical = calc_ccc(50.0, 50.0, 30.0)
    assert pytest.approx(typical.value, abs=1e-9) == 70.0
    # 70 sits one third of the way from 60->60 to 90->80
    assert pytest.approx(_score("ccc", typical), abs=1e-9) == 200.0 / 3.0

    assert calc_ccc(None, 50.0, 30.0).status == MetricStatus.MISSING_INPUT


def test_fixture_supplier_concentration():
    typical = calc_hhi([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(typical.value, abs=1e-9) == 0.38

    dispersed = calc_hhi([{"share": 0.25}, {"share": 0.25}, {"share": 0.25}, {"share": 0.25}])
    assert pytest.approx(dispersed.value, abs=1e-9) == 0.25


def test_fixture_opex_rigidity():
    typical = calc_opex_rigidity({"opex": 100.0, "fixed_opex_share": 0.4})
    assert pytest.approx(typical.value, abs=1e-9) == 0.4
    # 0.4 is midway between the 0.3->20 and 0.5->40 anchors
    assert pytest.approx(_score("opex_rigidity", typical), abs=1e-9) == 30.0

    assert calc_opex_rigidity({"opex": None}).status == MetricStatus.MISSING_INPUT


def test_fixture_single_source_flags():
    # Three suppliers each above the 0.60 share threshold -> count 3 -> 95
    suppliers = [{"share": 0.9}, {"share": 0.8}, {"share": 0.7}]
    typical = calc_single_source_flags({"suppliers": suppliers})
    assert pytest.approx(typical.value, abs=1e-9) == 3.0
    assert _score("single_source_flags", typical) == 95.0

    # No supplier dominates -> count 0 -> 10
    none = calc_single_source_flags({"suppliers": [{"share": 0.5}, {"share": 0.5}]})
    assert pytest.approx(none.value, abs=1e-9) == 0.0
    assert _score("single_source_flags", none) == 10.0


# --------------------------------------------------------------------------
# Concentration (risk-engine.md §7)
# --------------------------------------------------------------------------


def test_fixture_hhi():
    # 0.5^2 + 0.3^2 + 0.2^2 = 0.38
    typical = calc_hhi([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(typical.value, abs=1e-9) == 0.38
    # 0.38 is midway between the 0.25->35 and 0.45->60 anchors
    assert pytest.approx(_score("hhi", typical), abs=1e-9) == 51.25

    # Degenerate: one bucket holds everything
    assert pytest.approx(calc_hhi([{"share": 1.0}]).value, abs=1e-9) == 1.0


def test_fixture_cr1():
    typical = calc_cr1([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(typical.value, abs=1e-9) == 0.5
    # 0.5 sits on the 0.5->45 anchor
    assert pytest.approx(_score("cr1", typical), abs=1e-9) == 45.0


def test_fixture_cr3():
    typical = calc_cr3([{"share": 0.5}, {"share": 0.3}, {"share": 0.2}])
    assert pytest.approx(typical.value, abs=1e-9) == 1.0
    # 1.0 sits on the 1.0->75 anchor
    assert pytest.approx(_score("cr3", typical), abs=1e-9) == 75.0

    # Top-3 of a four-way split: 0.4 + 0.3 + 0.2 = 0.9
    assert (
        pytest.approx(
            calc_cr3([{"share": 0.4}, {"share": 0.3}, {"share": 0.2}, {"share": 0.1}]).value,
            abs=1e-9,
        )
        == 0.9
    )


# --------------------------------------------------------------------------
# Macro (risk-engine.md §8)
# --------------------------------------------------------------------------


def test_fixture_inflation_passthrough():
    # margin gap = 1.0pp - 3.0% = -2.0pp
    typical = calc_inflation_passthrough(1.0, 3.0)
    assert pytest.approx(typical.value, abs=1e-9) == -2.0
    # -2 sits on the -2->45 anchor
    assert pytest.approx(_score("inflation_passthrough", typical), abs=1e-9) == 45.0

    assert calc_inflation_passthrough(None, 3.0).status == MetricStatus.MISSING_INPUT


def test_fixture_rate_environment():
    # gap = max(0, 6.0 - 3.0) = 3.0pp
    typical = calc_rate_environment(6.0, 3.0)
    assert pytest.approx(typical.value, abs=1e-9) == 3.0
    # 3.0 is midway between the 2->35 and 4->60 anchors
    assert pytest.approx(_score("rate_environment", typical), abs=1e-9) == 47.5

    # Rates below the trailing median become a zero gap
    assert pytest.approx(calc_rate_environment(2.0, 5.0).value, abs=1e-9) == 0.0
    assert calc_rate_environment(None, None).status == MetricStatus.MISSING_INPUT


def test_fixture_fx_volatility():
    # Alternating +/-1% daily returns -> mean 0, sigma 1%, annualised by sqrt(252).
    typical = calc_macro_fx_volatility(_alternating_returns(60, 0.01))
    assert typical.status == MetricStatus.VALID
    assert pytest.approx(typical.value, abs=1e-9) == 0.01 * math.sqrt(252) * 100.0

    assert calc_macro_fx_volatility(None).status == MetricStatus.UNAVAILABLE
    assert calc_macro_fx_volatility(_alternating_returns(29)).status == MetricStatus.UNAVAILABLE


def test_fixture_gdp_sensitivity():
    # Frozen elasticities [A]: manufacturing 1.2, retail 1.0, services 0.8 (GDP vol 1.0)
    assert pytest.approx(calc_gdp_sensitivity("manufacturing").value, abs=1e-9) == 1.2
    assert pytest.approx(calc_gdp_sensitivity("retail").value, abs=1e-9) == 1.0
    assert pytest.approx(calc_gdp_sensitivity("services_saas").value, abs=1e-9) == 0.8

    # 1.2 -> 55, 1.0 -> 45, 0.8 -> 35 against the frozen anchors
    assert (
        pytest.approx(_score("gdp_sensitivity", calc_gdp_sensitivity("manufacturing")), abs=1e-9)
        == 55.0
    )
    assert (
        pytest.approx(_score("gdp_sensitivity", calc_gdp_sensitivity("retail")), abs=1e-9) == 45.0
    )
    assert (
        pytest.approx(_score("gdp_sensitivity", calc_gdp_sensitivity("services_saas")), abs=1e-9)
        == 35.0
    )
