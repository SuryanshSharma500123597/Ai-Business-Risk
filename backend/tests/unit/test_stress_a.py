"""Unit tests for Stress Testing (Phase 8): execution, KPIs, breaches."""

from __future__ import annotations

import pytest

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import CompanyDataset, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import stress as st


def dataset(seed: int = 1001) -> CompanyDataset:
    return generate_company(SyntheticCompanyConfig(seed=seed, periods=24))


def test_zero_delta_stressed_equals_baseline() -> None:
    v = sc.validate_params({"name": "flat"}, origin=sc.ScenarioOrigin.FORM)
    r = st.run_stress(dataset(), v)
    assert r.baseline.months == r.stressed.months
    assert r.interaction_residual == pytest.approx(0.0, abs=1e-9)
    for impact in r.kpi_impacts:
        assert impact.delta_absolute == pytest.approx(0.0, abs=1e-9)
        if impact.baseline == 0.0:
            # Decision D: a zero baseline has no defined percentage change.
            assert impact.delta_pct is None
            assert impact.delta_pct_reason == "zero_baseline"
        else:
            assert impact.delta_pct == pytest.approx(0.0, abs=1e-12)
            assert impact.delta_pct_reason == ""


def test_kpi_layout_frozen_order_trough_and_end() -> None:
    v = sc.get_preset("combined_stress")
    r = st.run_stress(dataset(), v)
    assert [(i.metric, i.scope) for i in r.kpi_impacts] == [
        (m, s) for m in st.KPI_ORDER for s in ("trough", "end")
    ]
    assert len(r.kpi_impacts) == 12


def test_revenue_delta_matches_hand_recomputation() -> None:
    v = sc.get_preset("recession")
    r = st.run_stress(dataset(), v)
    trough = next(i for i in r.kpi_impacts if i.metric == "revenue" and i.scope == "trough")
    base = min(m.revenue for m in r.baseline.months)
    stress = min(m.revenue for m in r.stressed.months)
    assert trough.baseline == pytest.approx(base)
    assert trough.stressed == pytest.approx(stress)
    assert trough.delta_absolute == pytest.approx(stress - base)
    assert trough.delta_pct == pytest.approx((stress - base) / abs(base))


def test_zero_baseline_pct_is_none() -> None:
    pct, reason = st._pct_change(0.0, 5.0)
    assert pct is None and reason == "zero_baseline"
    pct2, _ = st._pct_change(None, 5.0)
    assert pct2 is None


def test_unvalidated_scenario_refused() -> None:
    pending = sc.validate_params({"name": "x"}, origin=sc.ScenarioOrigin.AI)
    with pytest.raises(AppError) as exc:
        st.run_stress(dataset(), pending)
    assert exc.value.code == ErrorCode.SCENARIO_PENDING_CONFIRM


def test_horizon_override_must_match() -> None:
    v = sc.get_preset("recession")
    with pytest.raises(AppError) as exc:
        st.run_stress(dataset(), v, horizon_override=6)
    assert exc.value.code == ErrorCode.VALIDATION_ERROR
    ok = st.run_stress(dataset(), v, horizon_override=12)
    assert ok.horizon_months == 12


def test_breach_order_and_proxy_unevaluable() -> None:
    v = sc.get_preset("combined_stress")
    r = st.run_stress(dataset(), v)
    assert [b.rule for b in r.breaches] == list(st.BREACH_ORDER)
    proxy = next(b for b in r.breaches if b.rule == "current_ratio_proxy_below_1")
    assert proxy.status == "unevaluable"
    assert proxy.observed is None and proxy.periods == []
    # Blocker B1: the reason must name the missing levels and the decision,
    # so a reader can tell "not computable" from "computed as fine".
    assert "current_assets/current_liabilities" in proxy.reason
    assert "(D-4)" in proxy.reason
    assert "invent" in proxy.reason


def test_min_cash_buffer_helper_fails_loud_when_record_missing() -> None:
    """A silent 0.0 buffer would silently misreport "cash < B" (Phase 8 B1)."""
    run = st.run_stress(dataset(), sc.get_preset("rate_shock")).stressed
    assert st.resolve_min_cash_buffer(run) > 0.0
    stripped = run.model_copy(
        update={"diagnostics": run.diagnostics.model_copy(update={"assumption_records": []})}
    )
    with pytest.raises(AppError) as exc:
        st.resolve_min_cash_buffer(stripped)
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_breach_periods_chronological_and_consistent() -> None:
    v = sc.get_preset("demand_collapse")
    r = st.run_stress(dataset(1002), v)
    for breach in r.breaches:
        if breach.status == "breached" and breach.threshold is not None:
            assert breach.periods == sorted(breach.periods)


def test_dimension_deltas_deferred_with_missing_fields() -> None:
    v = sc.get_preset("recession")
    r = st.run_stress(dataset(), v)
    assert r.dimension_deltas is None
    assert r.dimension_deltas_note["status"] == "deferred"
    assert "equity" in r.dimension_deltas_note["missing_fields"]


def test_versions_and_hash_stamped() -> None:
    v = sc.get_preset("rate_shock")
    r = st.run_stress(dataset(), v)
    assert (r.stress_version, r.scenario_version, r.twin_version, r.registry_version) == (
        "1.0.0",
        "1.0.0",
        "1.0.0",
        "1.0.0",
    )
    assert r.validated_params_hash == v.provenance.validated_params_hash
    assert len(r.result_hash) == 64


def test_deterministic_rerun_hash_equal() -> None:
    v = sc.get_preset("inflation")
    a = st.run_stress(dataset(1003), v)
    b = st.run_stress(dataset(1003), v)
    assert a.result_hash == b.result_hash
    assert a == b
