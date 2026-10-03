"""Unit tests for Sensitivity sweeps (Phase 8): determinism, ordering."""

from __future__ import annotations

import pytest

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import CompanyDataset, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import sensitivity as sn
from backend.simulation import stress as st


def dataset(seed: int = 1001) -> CompanyDataset:
    return generate_company(SyntheticCompanyConfig(seed=seed, periods=24))


def test_sweep_grid_covers_frozen_bounds_and_baseline() -> None:
    """Frozen §6.3: single-factor sweep over the §3 bounds (locked decision G)."""
    v = sc.get_preset("recession")
    r = sn.sweep_single_factor(dataset(), v, "revenue_change_pct")
    values = [p.value for p in r.points]
    lower, upper = sc.FIELD_BOUNDS["revenue_change_pct"]
    assert values == sorted(values)
    assert values[0] == lower and values[-1] == upper
    # grid is 9 inclusive-endpoint points; 0.0 is already on this grid, so
    # the union with the mandatory baseline point yields exactly 9 values.
    assert len(values) == sn.SWEEP_POINTS
    assert len(values) <= sn.MAX_SWEEP_RUNS
    base = [p for p in r.points if p.is_baseline_point]
    assert len(base) == 1 and base[0].value == 0.0
    assert r.reference == sn.SENSITIVITY_REFERENCE
    assert r.field == "revenue_change_pct" and r.horizon_months == 12


def test_sweep_adds_baseline_when_grid_omits_zero() -> None:
    """ar_days_change [-30, 60] has no 0.0 on the grid: baseline is added."""
    v = sc.get_preset("recession")
    r = sn.sweep_single_factor(dataset(), v, "ar_days_change")
    values = [p.value for p in r.points]
    assert len(values) == sn.SWEEP_POINTS + 1
    assert 0.0 in values
    assert sum(1 for p in r.points if p.is_baseline_point) == 1


def test_sweep_is_one_factor_at_a_time_from_zero_shock_base() -> None:
    """A combined scenario still sweeps one field against the flat baseline.

    The sweep reference is the same zero-override run ``run_stress`` uses
    (frozen §6.3 reads from baseline), so the scenario's *other* shocks must
    not leak into the curve: the baseline point reproduces the twin baseline
    exactly and the endpoints equal the bound values.
    """
    v = sc.get_preset("combined_stress")
    r = sn.sweep_single_factor(dataset(), v, "revenue_change_pct")
    base = next(p for p in r.points if p.is_baseline_point)
    for impact in base.kpi_impacts:
        assert impact.delta_absolute == pytest.approx(0.0, abs=1e-9)
        assert impact.stressed == pytest.approx(impact.baseline)
    flat = sn.sweep_single_factor(
        dataset(),
        sc.validate_params({"name": "flat"}, origin=sc.ScenarioOrigin.FORM),
        "revenue_change_pct",
    )
    assert [(p.value, [i.delta_absolute for i in p.kpi_impacts]) for p in r.points] == [
        (p.value, [i.delta_absolute for i in p.kpi_impacts]) for p in flat.points
    ]


def test_sweep_baseline_point_has_zero_deltas() -> None:
    v = sc.get_preset("recession")
    r = sn.sweep_single_factor(dataset(), v, "revenue_change_pct")
    base = next(p for p in r.points if p.is_baseline_point)
    for impact in base.kpi_impacts:
        assert impact.delta_absolute == pytest.approx(0.0, abs=1e-9)


def test_sweep_kpi_rows_use_frozen_order_and_breach_onset() -> None:
    v = sc.get_preset("recession")
    r = sn.sweep_single_factor(dataset(1002), v, "revenue_change_pct")
    for point in r.points:
        assert [(i.metric, i.scope) for i in point.kpi_impacts] == [
            (m, s) for m in st.KPI_ORDER for s in ("trough", "end")
        ]
        for rule in point.breaches:
            assert rule in st.BREACH_ORDER
        # unevaluable rules are never reported as breaches
        assert "current_ratio_proxy_below_1" not in point.breaches
    for rule, onset in r.breach_onset.items():
        breached = [p.value for p in r.points if rule in p.breaches]
        assert breached and onset == min(breached)
    assert set(r.breach_onset) == {rule for point in r.points for rule in point.breaches}


def test_sweep_timeout_of_scope_horizon_is_validated_horizon() -> None:
    v = sc.validate_params(
        {"name": "short", "horizon_months": 6, "revenue_change_pct": -10.0},
        origin=sc.ScenarioOrigin.FORM,
    )
    r = sn.sweep_single_factor(dataset(), v, "revenue_change_pct")
    assert r.horizon_months == 6
    assert all(len(p.kpi_impacts) == 12 for p in r.points)


def test_sweep_deterministic() -> None:
    v = sc.get_preset("inflation")
    a = sn.sweep_single_factor(dataset(1003), v, "cogs_change_pct")
    b = sn.sweep_single_factor(dataset(1003), v, "cogs_change_pct")
    assert a == b


def test_sweep_rejects_unknown_field() -> None:
    v = sc.get_preset("recession")
    with pytest.raises(AppError) as exc:
        sn.sweep_single_factor(dataset(), v, "one_off_cost")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_sweep_rejects_unvalidated() -> None:
    pending = sc.validate_params({"name": "x"}, origin=sc.ScenarioOrigin.AI)
    with pytest.raises(AppError) as exc:
        sn.sweep_single_factor(dataset(), pending, "revenue_change_pct")
    assert exc.value.code == ErrorCode.SCENARIO_PENDING_CONFIRM


def test_sweep_cap_enforced() -> None:
    v = sc.get_preset("recession")
    with pytest.raises(AppError) as exc:
        sn.sweep_single_factor(dataset(), v, "revenue_change_pct", points=11)
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_sweep_rejects_unbounded_and_degenerate_grids() -> None:
    v = sc.get_preset("recession")
    # one_off_cost has no frozen upper bound: no endpoints, no sweep.
    with pytest.raises(AppError) as unbounded:
        sn._sweep_grid("one_off_cost", sn.SWEEP_POINTS)
    assert unbounded.value.code == ErrorCode.VALIDATION_ERROR
    with pytest.raises(AppError) as degenerate:
        sn.sweep_single_factor(dataset(), v, "revenue_change_pct", points=1)
    assert degenerate.value.code == ErrorCode.VALIDATION_ERROR


def test_sweep_accepts_a_confirmed_ai_scenario() -> None:
    """FD-3: AI origin must be confirmed, then the sweep revalidates it."""
    pending = sc.validate_params(
        {"name": "ai", "revenue_change_pct": -10.0}, origin=sc.ScenarioOrigin.AI
    )
    with pytest.raises(AppError) as exc:
        sn.sweep_single_factor(dataset(), pending, "revenue_change_pct")
    assert exc.value.code == ErrorCode.SCENARIO_PENDING_CONFIRM

    r = sn.sweep_single_factor(dataset(), sc.confirm(pending), "revenue_change_pct")
    assert len(r.points) == sn.SWEEP_POINTS
    assert r.reference == sn.SENSITIVITY_REFERENCE


def test_d63_trough_cash_not_monotone_documented() -> None:
    """D-6-3 guard: contraction can raise trough cash via WC release.

    Seed 1002 under a revenue sweep: trough cash at -30% exceeds trough
    cash at baseline while EBITDA deteriorates. This pins the finding —
    it must never be 'fixed' into a monotonicity assertion.
    """
    v = sc.validate_params({"name": "d63"}, origin=sc.ScenarioOrigin.FORM)
    r = sn.sweep_single_factor(dataset(1002), v, "revenue_change_pct")
    by_value = {p.value: p for p in r.points}

    def stressed_at(value: float, metric: str) -> float:
        found = next(
            i.stressed
            for i in by_value[value].kpi_impacts
            if i.metric == metric and i.scope == "trough"
        )
        assert found is not None
        return found

    assert stressed_at(-37.5, "min_cash") > stressed_at(0.0, "min_cash")
    # WC release raises trough cash under a contraction...
    assert stressed_at(-37.5, "ebitda") < stressed_at(0.0, "ebitda")
