"""Independent numerical validation of the Digital Twin (Phase 6) and the
stress-testing pipeline (Phase 8).

Deliberately *additive* to the existing suite: it re-derives a handful of
frozen behaviours from first principles and checks the emitted outputs against
that arithmetic, rather than restating what the engine already computed. It
imports the frozen implementation only; it never modifies it.

Four independent checks (Workstream F):

* ``G1`` — the twin refuses to build t=0 from a period missing revenue, cash
  or total_debt, and never imputes the missing value.
* ``G2`` — the frozen Phase 4 ratio calculators' sentinel and negative-ratio
  branches, surfaced through the actual simulated-month outputs.
* ``G3`` — the stress EBITDA waterfall and below-EBITDA bridge, recomputed
  bucket-by-bucket from the raw monthly records (the existing tests assert only
  closure and the ``revenue_effect`` bucket; this recomputes every component).
* ``G4`` — the ordinary positive-denominator DSCR identity
  ``EBITDA / (interest + principal)``.

All expected values are derived from the frozen formulas by hand, never read
back from the engine's own ratio/waterfall output.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from backend.data_engine.contracts import CompanyDataset, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import stress as st
from backend.simulation.contracts import (
    DebtAmortization,
    SimulationAssumptions,
    SimulationInitialState,
    SimulationInput,
    SimulationMonth,
    SimulationOverrides,
)
from backend.simulation.twin import build_initial_state_from_period, run_twin

# Frozen sentinel emitted by calc_dscr / calc_interest_coverage on a zero or
# non-positive denominator (backend/risk_engine/metrics/financial_strength.py).
SENTINEL = 999.0


# --- local, hand-arithmetic builders (mirror the frozen unit-test helpers) ---
def _assumptions(**overrides: Any) -> SimulationAssumptions:
    base: dict[str, Any] = {
        "growth_rate": 0.0,
        "cogs_ratio": 0.50,
        "fixed_cost": 0.0,
        "variable_cost_ratio": 0.10,
        "da_monthly": 0.0,
        "dso": 0.0,
        "dio": 0.0,
        "dpo": 0.0,
        "capex_monthly": 0.0,
        "revenue_capacity": 1_000_000.0,
        "initial_debt": 0.0,
        "base_rate": 0.12,
        "floating_debt_share": 1.0,
        "min_cash_buffer": 0.0,
        "revolver_cap": 0.0,
        "tax_rate": 0.25,
        "fx_import_cost_share": 0.0,
        "fx_revenue_share": 0.0,
        "commodity_cost_share": 0.0,
        "pass_through": 0.3,
        "fx_demand_elasticity": 0.5,
    }
    base.update(overrides)
    return SimulationAssumptions(**base)


def _initial_state(**overrides: Any) -> SimulationInitialState:
    base: dict[str, Any] = {
        "period_end": date(2024, 12, 31),
        "revenue": 1000.0,
        "cash": 5000.0,
        "debt": 0.0,
        "nwc": 0.0,
        "history_periods": 12,
    }
    base.update(overrides)
    return SimulationInitialState(**base)


def _month(a: dict[str, Any] | None = None) -> SimulationMonth:
    """One projected month with fully specified round assumptions."""
    return run_twin(
        SimulationInput(
            horizon_months=1,
            assumptions=_assumptions(**(a or {})),
            initial_state=_initial_state(),
            overrides=SimulationOverrides(),
        )
    ).months[0]


def _dataset(seed: int = 1001) -> CompanyDataset:
    return generate_company(SyntheticCompanyConfig(seed=seed, periods=24))


# 1200 of debt in the 0-3m bucket, amortized evenly over 3 months -> 400/month
# starting in month 1 (frozen "equal amortization inside buckets", §1).
_EARLY_SCHEDULE = [
    DebtAmortization(bucket="0-3m", months=3, amount=1200.0, monthly_principal=400.0)
]


# ---------------------------------------------------------------------------
# G1 — missing required inputs are refused, never imputed

# ---------------------------------------------------------------------------
# G2 — undefined / negative ratio branches via the real simulated outputs
# ---------------------------------------------------------------------------
def test_g2a_zero_debt_service_yields_dscr_sentinel() -> None:
    # initial_debt 0 -> interest 0 and principal 0 -> debt_service 0.
    month = _month({"initial_debt": 0.0})
    assert month.interest_expense == pytest.approx(0.0)
    assert month.principal == pytest.approx(0.0)
    assert month.dscr.value == pytest.approx(SENTINEL)
    # Zero interest also trips the coverage sentinel in the same month.
    assert month.interest_coverage.value == pytest.approx(SENTINEL)


def test_g2b_zero_interest_with_positive_debt_service_yields_coverage_sentinel() -> None:
    # base_rate 0 -> interest 0, but principal 400 > 0 keeps DSCR a real ratio.
    month = _month(
        {"initial_debt": 1200.0, "base_rate": 0.0, "debt_amortization": _EARLY_SCHEDULE}
    )
    assert month.interest_expense == pytest.approx(0.0)
    assert month.principal == pytest.approx(400.0)
    # DSCR stays a genuine EBITDA / (0 + 400) ratio, NOT the sentinel.
    assert month.dscr.value == pytest.approx(month.ebitda / 400.0)
    assert month.dscr.value != pytest.approx(SENTINEL)
    # Interest coverage is undefined (0 interest) -> sentinel.
    assert month.interest_coverage.value == pytest.approx(SENTINEL)


def test_g2c_negative_ebitda_with_positive_debt_service_gives_negative_dscr() -> None:
    # variable_cost_ratio 2.0 -> opex 2000, EBITDA 500 - 2000 = -1500 < 0.
    month = _month(
        {
            "initial_debt": 1200.0,
            "variable_cost_ratio": 2.0,
            "debt_amortization": _EARLY_SCHEDULE,
        }
    )
    assert month.ebitda == pytest.approx(-1500.0)
    assert month.interest_expense > 0.0 or month.principal > 0.0
    # Negative EBITDA over positive debt service is a real negative DSCR,
    # never the 999 sentinel.
    assert month.dscr.value == pytest.approx(-1500.0 / (12.0 + 400.0))
    assert month.dscr.value is not None
    assert month.dscr.value < 0.0


def test_g2d_negative_ebit_with_positive_interest_gives_negative_coverage() -> None:
    # da_monthly 1000 -> EBIT = EBITDA(400) - 1000 = -600 < 0, interest 12 > 0.
    month = _month({"initial_debt": 1200.0, "da_monthly": 1000.0})
    assert month.ebit < 0.0
    assert month.interest_expense == pytest.approx(12.0)
    assert month.interest_coverage.value == pytest.approx(-600.0 / 12.0)
    assert month.interest_coverage.value is not None
    assert month.interest_coverage.value < 0.0


# ---------------------------------------------------------------------------
# G4 — ordinary positive-denominator DSCR identity
# ---------------------------------------------------------------------------
def test_g4_dscr_equals_ebitda_over_interest_plus_principal() -> None:
    # initial_debt 1200 @ 12%/yr floating -> interest 12; 0-3m bucket -> 400.
    # EBITDA = 1000 - 500 - 100 = 400. DSCR = 400 / (12 + 400).
    month = _month({"initial_debt": 1200.0, "debt_amortization": _EARLY_SCHEDULE})
    assert month.ebitda == pytest.approx(400.0)
    assert month.interest_expense == pytest.approx(12.0)
    assert month.principal == pytest.approx(400.0)
    expected = month.ebitda / (month.interest_expense + month.principal)
    assert month.dscr.value == pytest.approx(expected)
    assert month.dscr.value == pytest.approx(400.0 / 412.0)


# ---------------------------------------------------------------------------
# G3 — independent recomputation of the full stress waterfall + bridge
# ---------------------------------------------------------------------------
def test_g3_waterfall_buckets_match_independent_recomputation() -> None:
    """Every waterfall bucket is recomputed from the raw monthly records.

    Frozen definitions (stress.attribute_waterfall, simulation.md §5), per
    month t (baseline b, stressed s):

        GM_b = (Rev_b - COGS_b) / Rev_b   (0 when Rev_b == 0)
        CR_b = COGS_b / Rev_b             (0 when Rev_b == 0)
        revenue_effect    += (Rev_s - Rev_b) * GM_b
        input_cost_effect += (Rev_s - Rev_b) * CR_b - (COGS_s - COGS_b)
        opex_effect       += -(Opex_s - Opex_b)
        other_one_off     += dEBITDA - (Rev_s - Rev_b)*GM_b
                                    - ((Rev_s - Rev_b)*CR_b - dCOGS) + dOpex
        interest_effect   += -(Int_s - Int_b)
        tax_effect        += -(Tax_s - Tax_b)

    The expected values are the sum of those hand formulas over the months,
    NOT read from the waterfall output under test.
    """
    result = st.run_stress(_dataset(), sc.get_preset("recession"))

    revenue = input_cost = opex = other = 0.0
    interest = tax = 0.0
    total_ebitda_delta = total_ni_delta = 0.0
    for base, stressed in zip(result.baseline.months, result.stressed.months, strict=True):
        gm = (base.revenue - base.cogs) / base.revenue if base.revenue != 0.0 else 0.0
        cr = base.cogs / base.revenue if base.revenue != 0.0 else 0.0
        d_rev = stressed.revenue - base.revenue
        d_cogs = stressed.cogs - base.cogs
        d_opex = stressed.opex - base.opex
        d_ebitda = stressed.ebitda - base.ebitda
        revenue += d_rev * gm
        input_cost += d_rev * cr - d_cogs
        opex += -d_opex
        other += d_ebitda - d_rev * gm - (d_rev * cr - d_cogs) + d_opex
        interest += -(stressed.interest_expense - base.interest_expense)
        tax += -(stressed.tax - base.tax)
        total_ebitda_delta += d_ebitda
        total_ni_delta += stressed.net_income - base.net_income

    emitted = {w.component: w.delta_ebitda for w in result.waterfall}
    assert emitted["revenue_effect"] == pytest.approx(revenue)
    assert emitted["input_cost_effect"] == pytest.approx(input_cost)
    assert emitted["opex_effect"] == pytest.approx(opex)
    assert emitted["other_one_off"] == pytest.approx(other, abs=1e-6)

    # Interaction residual is the (floating-point) closure of the four buckets.
    recomputed_residual = total_ebitda_delta - (revenue + input_cost + opex + other)
    assert result.interaction_residual == pytest.approx(recomputed_residual, abs=1e-6)
    assert abs(result.interaction_residual) <= max(0.005 * abs(total_ebitda_delta), 1e-9)

    # Below-EBITDA bridge closes to the net-income delta (DA is identical
    # across runs, so the only gap is float dust).
    bridge = {b.component: (b.delta_ni or 0.0) for b in result.below_bridge}
    assert bridge["interest_effect"] == pytest.approx(interest)
    assert bridge["tax_effect"] == pytest.approx(tax)
    bridge_residual = total_ni_delta - (total_ebitda_delta + interest + tax)
    assert abs(bridge_residual) <= max(0.005 * abs(total_ni_delta), 1e-9)
    assert bridge_residual == pytest.approx(0.0, abs=1e-6)

    # initial_debt 1200 @ 12%/yr floating -> interest 12; 0-3m bucket -> 400.
    # EBITDA = 1000 - 500 - 100 = 400. DSCR = 400 / (12 + 400).
    month = _month({"initial_debt": 1200.0, "debt_amortization": _EARLY_SCHEDULE})
    assert month.ebitda == pytest.approx(400.0)
    assert month.interest_expense == pytest.approx(12.0)
    assert month.principal == pytest.approx(400.0)
    expected = month.ebitda / (month.interest_expense + month.principal)
    assert month.dscr.value == pytest.approx(expected)
    assert month.dscr.value == pytest.approx(400.0 / 412.0)

# ---------------------------------------------------------------------------
def test_g1_missing_revenue_is_refused_without_imputation() -> None:
    broken = _dataset().periods[-1].model_copy(update={"revenue": None})
    with pytest.raises(ValueError, match="missing inputs are never imputed"):
        build_initial_state_from_period(broken, _dataset())


def test_g1_missing_cash_is_refused_without_imputation() -> None:
    broken = _dataset().periods[-1].model_copy(update={"cash": None})
    with pytest.raises(ValueError, match="missing inputs are never imputed"):
        build_initial_state_from_period(broken, _dataset())


def test_g1_missing_total_debt_is_refused_without_imputation() -> None:
    broken = _dataset().periods[-1].model_copy(update={"total_debt": None})
    with pytest.raises(ValueError, match="missing inputs are never imputed"):
        build_initial_state_from_period(broken, _dataset())


def test_g1_complete_period_populates_exact_values() -> None:
    """When the inputs ARE present the built state carries them verbatim."""
    dataset = _dataset()
    latest = dataset.periods[-1]
    state = build_initial_state_from_period(latest, dataset)
    assert state.revenue == pytest.approx(latest.revenue)
    assert state.cash == pytest.approx(latest.cash)
    assert state.debt == pytest.approx(latest.total_debt)
