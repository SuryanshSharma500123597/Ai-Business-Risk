"""Property-style tests for Stress Testing (Phase 8). Seeded, no Hypothesis."""

from __future__ import annotations

import random
from typing import Any

import pytest

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import sensitivity as sn
from backend.simulation import stress as st

SEED = 42
SAMPLES = 60


def _rng() -> random.Random:
    return random.Random(SEED)


def test_fuzzed_scenarios_close_and_stay_deterministic() -> None:
    rng = _rng()
    fields = [f for f in sc.SHOCK_FIELDS if f != "one_off_cost"]
    for i in range(SAMPLES):
        raw: dict[str, Any] = {"name": f"fuzz-{i}"}
        for field in rng.sample(fields, 3):
            lower, upper = sc.FIELD_BOUNDS[field]
            assert upper is not None
            raw[field] = rng.uniform(lower, upper)
        v = sc.validate_params(raw, origin=sc.ScenarioOrigin.FORM)
        seed = rng.choice([1001, 1002, 1003, 1004, 1005])
        ds = generate_company(SyntheticCompanyConfig(seed=seed, periods=24))
        a = st.run_stress(ds, v)
        b = st.run_stress(ds, v)
        assert a.result_hash == b.result_hash
        total = sum(m.ebitda for m in a.stressed.months) - sum(m.ebitda for m in a.baseline.months)
        parts = sum(w.delta_ebitda for w in a.waterfall)
        assert total - parts == pytest.approx(0.0, abs=max(0.005 * abs(total), 1e-9))
        assert [x.rule for x in a.breaches] == list(st.BREACH_ORDER)


def test_breach_iff_condition_holds() -> None:
    """Frozen §6.4: a flag exists iff its condition holds (live rules)."""
    rng = _rng()
    for i in range(20):
        raw: dict[str, Any] = {
            "name": f"br-{i}",
            "revenue_change_pct": rng.uniform(-50.0, 50.0),
        }
        v = sc.validate_params(raw, origin=sc.ScenarioOrigin.FORM)
        ds = generate_company(SyntheticCompanyConfig(seed=1001, periods=24))
        r = st.run_stress(ds, v)
        by_rule = {b.rule: b for b in r.breaches}
        cash = r.stressed.trajectory("cash")
        buf = float(
            next(
                x.value
                for x in r.stressed.diagnostics.assumption_records
                if x.parameter == "min_cash_buffer"
            )
        )
        cash_breach = by_rule["cash_below_buffer"]
        expect = [t + 1 for t, c in enumerate(cash) if c < buf]
        assert (cash_breach.status == "breached") == bool(expect)
        assert cash_breach.periods == expect
        assert by_rule["funding_gap_occurred"].periods == list(
            r.stressed.summary.funding_gap_months
        )


def test_sweep_grids_deterministic_ascending() -> None:
    rng = _rng()
    for field in ("revenue_change_pct", "interest_rate_change_pp", "fx_change_pct"):
        v = sc.validate_params({"name": "s"}, origin=sc.ScenarioOrigin.FORM)
        ds = generate_company(SyntheticCompanyConfig(seed=rng.choice([1001, 1004]), periods=24))
        a = sn.sweep_single_factor(ds, v, field)
        b = sn.sweep_single_factor(ds, v, field)
        assert a == b
        assert [p.value for p in a.points] == sorted(p.value for p in a.points)
        assert sum(1 for p in a.points if p.is_baseline_point) == 1
