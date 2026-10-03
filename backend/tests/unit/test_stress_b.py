"""Unit tests for Stress Testing (Phase 8): waterfall, bridge, policy."""

from __future__ import annotations

import pytest

from backend.data_engine.contracts import CompanyDataset, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import stress as st


def dataset(seed: int = 1001) -> CompanyDataset:
    return generate_company(SyntheticCompanyConfig(seed=seed, periods=24))


def test_waterfall_order_and_closure_all_seeds() -> None:
    for seed in (1001, 1002, 1003, 1004, 1005):
        r = st.run_stress(dataset(seed), sc.get_preset("combined_stress"))
        assert [w.component for w in r.waterfall] == list(st.WATERFALL_ORDER)
        assert [b.component for b in r.below_bridge] == list(st.BRIDGE_ORDER)
        total = sum(m.ebitda for m in r.stressed.months) - sum(m.ebitda for m in r.baseline.months)
        parts = sum(w.delta_ebitda for w in r.waterfall)
        assert total - parts == pytest.approx(0.0, abs=max(0.005 * abs(total), 1e-9))


def test_waterfall_closure_all_presets() -> None:
    for preset in sc.list_presets():
        r = st.run_stress(dataset(), sc.get_preset(preset["preset_id"]))
        total = sum(m.ebitda for m in r.stressed.months) - sum(m.ebitda for m in r.baseline.months)
        parts = sum(w.delta_ebitda for w in r.waterfall)
        assert total - parts == pytest.approx(0.0, abs=max(0.005 * abs(total), 1e-9))


def test_bridge_closes_to_net_income() -> None:
    r = st.run_stress(dataset(), sc.get_preset("combined_stress"))
    total_ni = sum(m.net_income for m in r.stressed.months) - sum(
        m.net_income for m in r.baseline.months
    )
    total_ebitda = sum(m.ebitda for m in r.stressed.months) - sum(
        m.ebitda for m in r.baseline.months
    )
    bridge = sum(b.delta_ni or 0.0 for b in r.below_bridge)
    residual = total_ni - (total_ebitda + bridge)
    # The bridge is exact by construction (DA is assumption-identical across
    # runs), so the only gap is float dust on ~1e8 magnitudes: assert the
    # frozen 0.5% closure *and* that the dust is economically nothing.
    assert abs(residual) <= max(0.005 * abs(total_ni), 1e-9)
    assert residual == pytest.approx(0.0, abs=1e-6)


def test_one_off_cost_never_attributed_ebitda() -> None:
    """Frozen §2: one_off_cost is cash-flow-only; waterfall must not blame it."""
    v = sc.validate_params(
        {"name": "cash hit", "one_off_cost": 50000.0}, origin=sc.ScenarioOrigin.FORM
    )
    r = st.run_stress(dataset(), v)
    assert all(abs(w.delta_ebitda) < 1e-6 for w in r.waterfall)
    cash = next(i for i in r.kpi_impacts if i.metric == "min_cash" and i.scope == "end")
    assert cash.delta_absolute is not None and cash.delta_absolute < 0.0


def test_revenue_formula_matches_frozen_definition() -> None:
    r = st.run_stress(dataset(), sc.get_preset("recession"))
    revenue = next(w for w in r.waterfall if w.component == "revenue_effect")
    expected = 0.0
    for base, stress in zip(r.baseline.months, r.stressed.months, strict=True):
        gm = (base.revenue - base.cogs) / base.revenue if base.revenue else 0.0
        expected += (stress.revenue - base.revenue) * gm
    assert revenue.delta_ebitda == pytest.approx(expected)


def test_custom_policy_override_applies() -> None:
    v = sc.get_preset("combined_stress")
    strict = st.run_stress(dataset(), v, policy=st.BreachPolicy(dscr=5.0))
    dscr = next(b for b in strict.breaches if b.rule == "dscr_below_1_2")
    assert dscr.threshold == 5.0
    default = st.run_stress(dataset(), v)
    assert next(b for b in default.breaches if b.rule == "dscr_below_1_2").threshold == 1.2


def test_invalid_policy_rejected() -> None:
    import pydantic

    v = sc.get_preset("recession")
    with pytest.raises((st.AppError, pydantic.ValidationError, ValueError, TypeError)):
        st.run_stress(dataset(), v, policy=st.BreachPolicy(dscr=float("inf")))
