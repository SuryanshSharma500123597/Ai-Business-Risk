"""Golden stress comparisons for the canonical fixture seeds 1001-1005.

Frozen authority: testing.md §4 — golden files are committed JSON,
"regenerated only by ``pytest --regen-golden`` ... A golden change without a
registry/twin version bump is a defect". This module extends that rule to
Phase 8: a stress comparison or sweep curve only moves when
``STRESS_VERSION`` (or the twin / scenario / registry version it stamps)
moves.

These are *new* files (``stress_seed_*.json``). ``seed_*.json`` (Phase 4
composite profiles), ``twin_seed_*.json`` (Phase 6 trajectories) and
``ml_anomaly_golden.json`` (Phase 5) are never read, written or regenerated
by this module.

Regenerate with::

    pytest backend/tests/golden --regen-golden

then review the JSON diff and note it in the development log.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.simulation import scenarios as sc
from backend.simulation import sensitivity as sn
from backend.simulation import stress as st
from backend.simulation.contracts import REGISTRY_VERSION, TWIN_VERSION

GOLDEN_DIR = Path(__file__).resolve().parent
CANONICAL_SEEDS = (1001, 1002, 1003, 1004, 1005)
CANONICAL_SCENARIOS = ("recession", "combined_stress", "demand_collapse")
SWEEP_FIELD = "revenue_change_pct"
HORIZON = 12
TOLERANCE = 1e-9


def _golden_path(seed: int) -> Path:
    return GOLDEN_DIR / f"stress_seed_{seed}.json"


def _impact_payload(impacts: list[st.KPIImpact]) -> list[dict[str, Any]]:
    return [
        {
            "metric": impact.metric,
            "scope": impact.scope,
            "baseline": impact.baseline,
            "stressed": impact.stressed,
            "delta_absolute": impact.delta_absolute,
            "delta_pct": impact.delta_pct,
            "delta_pct_reason": impact.delta_pct_reason,
        }
        for impact in impacts
    ]


def _scenario_payload(result: st.StressTestResult) -> dict[str, Any]:
    return {
        "scenario_name": result.scenario_name,
        "validated_params_hash": result.validated_params_hash,
        "result_hash": result.result_hash,
        "interaction_residual": result.interaction_residual,
        "dimension_deltas": result.dimension_deltas,
        "dimension_deltas_status": result.dimension_deltas_note["status"],
        "kpi_impacts": _impact_payload(result.kpi_impacts),
        "breaches": [
            {
                "rule": breach.rule,
                "status": breach.status,
                "threshold": breach.threshold,
                "observed": breach.observed,
                "periods": list(breach.periods),
            }
            for breach in result.breaches
        ],
        "waterfall": [
            {"component": w.component, "delta_ebitda": w.delta_ebitda} for w in result.waterfall
        ],
        "below_bridge": [
            {"component": b.component, "delta_ni": b.delta_ni} for b in result.below_bridge
        ],
    }


def _sweep_payload(seed: int) -> dict[str, Any]:
    """The frozen §6.3 response curve for one field, plus breach onset."""
    sweep = sn.sweep_single_factor(
        generate_company(SyntheticCompanyConfig(seed=seed, periods=24)),
        sc.validate_params(
            {"name": "sweep", "horizon_months": HORIZON}, origin=sc.ScenarioOrigin.FORM
        ),
        SWEEP_FIELD,
    )

    def curve(metric: str) -> list[float | None]:
        return [
            next(
                impact.stressed
                for impact in point.kpi_impacts
                if impact.metric == metric and impact.scope == "trough"
            )
            for point in sweep.points
        ]

    return {
        "field": sweep.field,
        "reference": sweep.reference,
        "values": [point.value for point in sweep.points],
        "baseline_point_index": next(
            index for index, point in enumerate(sweep.points) if point.is_baseline_point
        ),
        "trough_min_cash": curve("min_cash"),
        "trough_ebitda": curve("ebitda"),
        "breached_rules": [list(point.breaches) for point in sweep.points],
        "breach_onset": sweep.breach_onset,
    }


def _golden(seed: int) -> dict[str, Any]:
    """Regenerate the deterministic Phase 8 golden for one seed."""
    dataset = generate_company(SyntheticCompanyConfig(seed=seed, periods=24))
    scenarios: dict[str, Any] = {
        preset_id: _scenario_payload(st.run_stress(dataset, sc.get_preset(preset_id)))
        for preset_id in CANONICAL_SCENARIOS
    }
    return {
        "seed": seed,
        "stress_version": st.STRESS_VERSION,
        "scenario_version": sc.SCENARIO_VERSION,
        "twin_version": TWIN_VERSION,
        "registry_version": REGISTRY_VERSION,
        "horizon_months": HORIZON,
        "scenarios": scenarios,
        "sensitivity": _sweep_payload(seed),
    }


def _compare(expected: Any, actual: Any, path: str) -> None:
    """Recursively compare a golden document with a live one, floats within tolerance."""
    if expected is None or actual is None:
        assert expected is None and actual is None, f"{path}: {actual!r} != {expected!r}"
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a mapping"
        assert set(expected) == set(actual), (
            f"{path}: keys differ ({sorted(set(expected) ^ set(actual))})"
        )
        for key in sorted(expected):
            _compare(expected[key], actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual), f"{path}: length differs"
        for index, (exp_item, act_item) in enumerate(zip(expected, actual, strict=True)):
            _compare(exp_item, act_item, f"{path}[{index}]")
        return
    if isinstance(expected, bool | str):
        assert expected == actual, f"{path}: {actual!r} != {expected!r}"
        return
    assert actual == pytest.approx(expected, abs=TOLERANCE), f"{path}: {actual!r} != {expected!r}"


def test_stress_goldens_exist_for_all_canonical_seeds(regen_golden: bool) -> None:
    if regen_golden:
        pytest.skip("goldens are being regenerated by this run")
    missing = [seed for seed in CANONICAL_SEEDS if not _golden_path(seed).exists()]
    assert not missing, f"missing stress goldens for seeds {missing}; run --regen-golden"


@pytest.mark.parametrize("seed", CANONICAL_SEEDS)
def test_golden_stress_comparison(seed: int, regen_golden: bool) -> None:
    actual = _golden(seed)
    path = _golden_path(seed)

    if regen_golden:
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    assert path.exists(), f"missing {path.name}; regenerate with --regen-golden"
    golden = json.loads(path.read_text(encoding="utf-8"))

    # A golden change without a stress version bump is a defect (testing.md §4).
    assert golden["stress_version"] == st.STRESS_VERSION, (
        f"{path.name} was generated by stress {golden['stress_version']} but the code now "
        f"reports {st.STRESS_VERSION}: regenerate and review the diff"
    )
    assert golden["twin_version"] == TWIN_VERSION
    assert golden["scenario_version"] == sc.SCENARIO_VERSION
    _compare(golden, actual, path.name)


@pytest.mark.parametrize("seed", CANONICAL_SEEDS)
def test_golden_stress_is_reproducible(seed: int) -> None:
    """Same seed + same scenario => byte-identical golden document (R6)."""
    assert _golden(seed) == _golden(seed)


@pytest.mark.parametrize("seed", CANONICAL_SEEDS)
def test_golden_stress_records_waterfall_and_breach_order(seed: int) -> None:
    golden = json.loads(_golden_path(seed).read_text(encoding="utf-8"))
    for scenario in golden["scenarios"].values():
        assert [w["component"] for w in scenario["waterfall"]] == list(st.WATERFALL_ORDER)
        assert [b["component"] for b in scenario["below_bridge"]] == list(st.BRIDGE_ORDER)
        assert [b["rule"] for b in scenario["breaches"]] == list(st.BREACH_ORDER)
        assert scenario["dimension_deltas"] is None
        assert scenario["dimension_deltas_status"] == "deferred"
        assert len(scenario["result_hash"]) == 64


def test_golden_pins_d63_non_monotone_trough_cash() -> None:
    """D-6-3: contraction raises trough cash via WC release while EBITDA falls."""
    golden = json.loads(_golden_path(1002).read_text(encoding="utf-8"))
    sweep = golden["sensitivity"]
    baseline_index = sweep["baseline_point_index"]
    cash = sweep["trough_min_cash"]
    ebitda = sweep["trough_ebitda"]
    assert sweep["field"] == SWEEP_FIELD
    assert sweep["values"][0] == sc.FIELD_BOUNDS[SWEEP_FIELD][0]
    assert cash[0] > cash[baseline_index]  # WC release lifts trough cash
    assert ebitda[0] < ebitda[baseline_index]  # while EBITDA falls
    assert sweep["reference"] == sn.SENSITIVITY_REFERENCE


def test_stress_goldens_do_not_touch_other_phase_goldens() -> None:
    for seed in CANONICAL_SEEDS:
        assert _golden_path(seed).name.startswith("stress_seed_")
        assert (GOLDEN_DIR / f"twin_seed_{seed}.json").exists()
        assert (GOLDEN_DIR / f"seed_{seed}.json").exists()


def test_stress_golden_payload_shape_is_frozen() -> None:
    """Phase 4 / 5 goldens stay out of the Phase 8 payload by construction."""
    golden = json.loads(_golden_path(CANONICAL_SEEDS[0]).read_text(encoding="utf-8"))
    assert "composite_score" not in json.dumps(golden)
    assert set(golden) == {
        "seed",
        "stress_version",
        "scenario_version",
        "twin_version",
        "registry_version",
        "horizon_months",
        "scenarios",
        "sensitivity",
    }
    assert set(golden["scenarios"]) == set(CANONICAL_SCENARIOS)
