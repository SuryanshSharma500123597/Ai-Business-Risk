"""Unit tests for the Scenario Engine (Phase 7): schema and envelope.

Frozen authority: docs/01_architecture/simulation.md §3 (schema, exact
bounds, clamp-within-1.25x/reject, unknown-keys-rejected) and §4 (presets).
Locked decisions A-L from the approved Phase 7 plan are cited inline.

Never calls the twin (no ``run_twin``/``simulate``): Phase 7 owns validation
only. No LLM, no network, no database.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pydantic
import pytest

from backend.core.errors import AppError, ErrorCode
from backend.simulation import scenarios as sc
from backend.simulation.scenarios import ScenarioOrigin


def form(raw: dict[str, Any]) -> sc.ValidatedScenario:
    return sc.validate_params(raw, origin=ScenarioOrigin.FORM)


def test_valid_full_scenario_passes_without_clamps() -> None:
    v = form(
        {
            "name": "revenue dip",
            "horizon_months": 12,
            "ramp_months": 0,
            "revenue_change_pct": -20.0,
            "interest_rate_change_pp": 2.0,
            "fx_change_pct": 10.0,
        }
    )
    assert v.confirmation_status is sc.ScenarioConfirmationStatus.VALIDATED
    assert v.clamped == []
    assert v.guardrail_events == []
    assert v.provenance.scenario_version == sc.SCENARIO_VERSION


def test_minimal_name_only_means_no_shock() -> None:
    v = form({"name": "baseline"})
    assert v.params.horizon_months == 12
    assert v.params.ramp_months == 0


def test_name_length_envelope() -> None:
    form({"name": "x"})
    form({"name": "x" * 80})
    with pytest.raises(AppError):
        form({"name": ""})
    with pytest.raises(AppError):
        form({"name": "x" * 81})


def test_missing_name_rejected() -> None:
    with pytest.raises(AppError) as exc:
        form({"revenue_change_pct": -10.0})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_unknown_key_rejected() -> None:
    with pytest.raises(AppError) as exc:
        form({"name": "x", "revenue_shock": -10.0})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_no_currency_field_in_schema() -> None:
    """Hard requirement 6: the frozen schema carries no currency field."""
    with pytest.raises(AppError):
        form({"name": "x", "currency": "USD"})


def test_non_mapping_rejected() -> None:
    with pytest.raises(AppError) as exc:
        sc.validate_params(["name"], origin=ScenarioOrigin.FORM)  # type: ignore[arg-type]
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_horizon_envelope() -> None:
    assert form({"name": "x", "horizon_months": 1}).params.horizon_months == 1
    assert form({"name": "x", "horizon_months": 36}).params.horizon_months == 36
    with pytest.raises(AppError):
        form({"name": "x", "horizon_months": 0})
    with pytest.raises(AppError):
        form({"name": "x", "horizon_months": 37})


def test_ramp_envelope() -> None:
    assert form({"name": "x", "ramp_months": 0}).params.ramp_months == 0
    assert form({"name": "x", "ramp_months": 12}).params.ramp_months == 12
    with pytest.raises(AppError):
        form({"name": "x", "ramp_months": 13})


def test_ramp_beyond_horizon_rejected_not_clamped() -> None:
    """Decision F: ramp_months > horizon_months is REJECTED."""
    with pytest.raises(AppError) as exc:
        form({"name": "x", "horizon_months": 6, "ramp_months": 7})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_ramp_equal_to_horizon_accepted() -> None:
    v = form({"name": "x", "horizon_months": 6, "ramp_months": 6})
    assert v.params.ramp_months == 6


def test_nonfinite_shock_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(AppError):
            form({"name": "x", "revenue_change_pct": bad})


def test_bool_shock_rejected() -> None:
    with pytest.raises(AppError) as exc:
        form({"name": "x", "revenue_change_pct": True})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_string_shock_rejected() -> None:
    with pytest.raises(AppError) as exc:
        form({"name": "x", "revenue_change_pct": "-20"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_exact_bounds_accepted() -> None:
    raw: dict[str, Any] = {"name": "edges"}
    for field, (lower, _upper) in sc.FIELD_BOUNDS.items():
        raw[field] = lower
    v = form(raw)
    assert v.clamped == []
    raw2: dict[str, Any] = {"name": "edges"}
    for field, (_lower, upper) in sc.FIELD_BOUNDS.items():
        if upper is not None:
            raw2[field] = upper
    v2 = form(raw2)
    assert v2.clamped == []


def test_inside_bounds_not_clamped() -> None:
    v = form({"name": "x", "revenue_change_pct": -49.9, "commodity_price_change_pct": 99.9})
    assert v.clamped == []


def test_clamp_band_clamps_with_info_event() -> None:
    # -60 is within 1.25x of the -50 lower bound (-62.5): clamps.
    v = form({"name": "x", "revenue_change_pct": -60.0})
    assert v.params.revenue_change_pct == -50.0
    assert v.clamped == ["revenue_change_pct"]
    (event,) = v.guardrail_events
    assert event.rule == "scenario_bounds.revenue_change_pct"
    assert event.severity == "info"
    assert event.action == "clamp"
    assert event.detail["observed"] == -60.0
    assert event.detail["bound"] == -50.0


def test_beyond_clamp_band_rejects() -> None:
    # -63 is beyond 1.25x of -50 (-62.5): rejects.
    with pytest.raises(AppError) as exc:
        form({"name": "x", "revenue_change_pct": -63.0})
    assert exc.value.code == ErrorCode.SCENARIO_OUT_OF_BOUNDS
    assert exc.value.details["field"] == "revenue_change_pct"


def test_clamp_band_edge_exactly_at_tolerance() -> None:
    v = form({"name": "x", "revenue_change_pct": -62.5})
    assert v.params.revenue_change_pct == -50.0
    assert v.clamped == ["revenue_change_pct"]


def test_upper_clamp_band() -> None:
    v = form({"name": "x", "revenue_change_pct": 60.0})
    assert v.params.revenue_change_pct == 50.0
    with pytest.raises(AppError) as exc:
        form({"name": "x", "revenue_change_pct": 63.0})
    assert exc.value.code == ErrorCode.SCENARIO_OUT_OF_BOUNDS


def test_supplier_zero_lower_bound_rejects_any_negative() -> None:
    """1.25x of the zero lower bound is still zero: negatives reject."""
    with pytest.raises(AppError) as exc:
        form({"name": "x", "supplier_disruption_pct": -0.5})
    assert exc.value.code == ErrorCode.SCENARIO_OUT_OF_BOUNDS
    v = form({"name": "x", "supplier_disruption_pct": 0.0})
    assert v.clamped == []


def test_supplier_upper_clamp_band() -> None:
    v = form({"name": "x", "supplier_disruption_pct": 120.0})
    assert v.params.supplier_disruption_pct == 100.0
    with pytest.raises(AppError):
        form({"name": "x", "supplier_disruption_pct": 126.0})


def test_capex_floor_minus_100_accepted() -> None:
    v = form({"name": "x", "capex_change_pct": -100.0})
    assert v.params.capex_change_pct == -100.0
    assert v.clamped == []


def test_one_off_cost_unbounded_above() -> None:
    """Decision K: no upper bound on one_off_cost — huge values validate."""
    v = form({"name": "x", "one_off_cost": 1e12})
    assert v.params.one_off_cost == 1e12
    assert v.clamped == []
    with pytest.raises(AppError):
        form({"name": "x", "one_off_cost": -1.0})


def test_multiple_clamps_all_recorded() -> None:
    v = form({"name": "x", "revenue_change_pct": -60.0, "cogs_change_pct": 60.0})
    assert sorted(v.clamped) == ["cogs_change_pct", "revenue_change_pct"]
    assert len(v.guardrail_events) == 2


def test_all_presets_validate_with_frozen_values() -> None:
    expected: dict[str, dict[str, float]] = {
        "recession": {"revenue_change_pct": -15.0, "ar_days_change": 10.0},
        "inflation": {"cogs_change_pct": 12.0, "opex_change_pct": 8.0},
        "rate_shock": {"interest_rate_change_pp": 2.0},
        "fx_shock": {"fx_change_pct": 10.0},
        "commodity_shock": {"commodity_price_change_pct": 25.0},
        "demand_collapse": {"revenue_change_pct": -30.0, "ar_days_change": 15.0},
        "supplier_disruption": {"supplier_disruption_pct": 40.0},
        "combined_stress": {
            "revenue_change_pct": -20.0,
            "cogs_change_pct": 10.0,
            "interest_rate_change_pp": 2.0,
            "commodity_price_change_pct": 15.0,
            "ar_days_change": 10.0,
        },
    }
    assert set(sc.PRESET_PARAMS) == set(expected)
    for preset_id, shocks in expected.items():
        v = sc.get_preset(preset_id)
        assert v.confirmation_status is sc.ScenarioConfirmationStatus.VALIDATED
        assert v.origin is ScenarioOrigin.PRESET
        assert v.params.name == preset_id
        assert v.params.horizon_months == 12
        assert v.params.ramp_months == 0
        for field, value in shocks.items():
            assert getattr(v.params, field) == value
        assert v.provenance.preset_id == preset_id
        assert v.provenance.scenario_version == sc.SCENARIO_VERSION


def test_preset_table_has_eight_entries() -> None:
    assert len(sc.PRESET_PARAMS) == 8
    assert len(sc.list_presets()) == 8


def test_list_presets_shape() -> None:
    for entry in sc.list_presets():
        assert set(entry) == {"preset_id", "name", "params", "description", "scenario_version"}
        assert entry["name"] == entry["preset_id"]
        assert entry["scenario_version"] == sc.SCENARIO_VERSION


def test_unknown_preset_rejected() -> None:
    with pytest.raises(AppError) as exc:
        sc.get_preset("zombie_apocalypse")
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_pct_divided_by_100() -> None:
    v = form({"name": "x", "revenue_change_pct": -20.0})
    assert sc.to_overrides(v).revenue_change == pytest.approx(-0.20)


def test_pp_divided_by_100() -> None:
    v = form({"name": "x", "interest_rate_change_pp": 2.0})
    assert sc.to_overrides(v).rate_change == pytest.approx(0.02)


def test_ar_days_and_cash_pass_through() -> None:
    v = form({"name": "x", "ar_days_change": 10.0, "one_off_cost": 5000.0})
    o = sc.to_overrides(v)
    assert o.ar_days_change == pytest.approx(10.0)
    assert o.one_off_cost == pytest.approx(5000.0)


def test_ramp_passes_through() -> None:
    v = form({"name": "x", "ramp_months": 4, "revenue_change_pct": -20.0})
    assert sc.to_overrides(v).ramp_months == 4


def test_unconfirmed_scenario_does_not_convert() -> None:
    pending = sc.validate_params({"name": "x"}, origin=ScenarioOrigin.AI)
    with pytest.raises(AppError) as exc:
        sc.to_overrides(pending)
    assert exc.value.code == ErrorCode.SCENARIO_PENDING_CONFIRM


def test_basis_points_normalize_explicitly() -> None:
    """Decision B: explicit 200bp -> 2.0pp, with a mapping note."""
    pp = sc.normalize_basis_points(200.0, note="rates +200bp -> +2pp")
    assert pp == pytest.approx(2.0)
    v = form({"name": "x", "interest_rate_change_pp": pp})
    assert sc.to_overrides(v).rate_change == pytest.approx(0.02)


def test_basis_points_invalid_inputs_rejected() -> None:
    with pytest.raises(AppError):
        sc.normalize_basis_points(float("nan"))
    with pytest.raises(AppError):
        sc.normalize_basis_points(True)


def test_ai_candidate_requires_confirmation_fd3() -> None:
    v = sc.validate_candidate(
        sc.TranslationCandidate(
            candidate={"name": "nl dip", "revenue_change_pct": -20.0},
            mapping_notes=["revenue falls 20% -> revenue_change_pct -20"],
            source_text="What if revenue falls 20%?",
            model="test-double",
        )
    )
    assert v.confirmation_status is sc.ScenarioConfirmationStatus.AWAITING_CONFIRMATION
    assert v.origin is ScenarioOrigin.AI
    assert v.mapping_notes == ["revenue falls 20% -> revenue_change_pct -20"]
    assert v.provenance.source_text == "What if revenue falls 20%?"
    assert v.provenance.model == "test-double"


def test_untrusted_translator_value_still_clamped() -> None:
    v = sc.validate_candidate(
        sc.TranslationCandidate(candidate={"name": "x", "revenue_change_pct": -60.0})
    )
    assert v.params.revenue_change_pct == -50.0
    assert v.clamped == ["revenue_change_pct"]


def test_untrusted_translator_value_still_rejected() -> None:
    with pytest.raises(AppError) as exc:
        sc.validate_candidate(
            sc.TranslationCandidate(candidate={"name": "x", "revenue_change_pct": -90.0})
        )
    assert exc.value.code == ErrorCode.SCENARIO_OUT_OF_BOUNDS


def test_translator_unknown_key_rejected() -> None:
    with pytest.raises(AppError) as exc:
        sc.validate_candidate(sc.TranslationCandidate(candidate={"name": "x", "vibes_pct": -10.0}))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_translator_ambiguous_unit_stays_unconfirmed() -> None:
    """Decision C: 'rates rise 2%' is never guessed — no pp default applied."""
    v = sc.validate_candidate(
        sc.TranslationCandidate(
            candidate={"name": "x"},
            mapping_notes=["AMBIGUOUS: 'rates rise 2%' could be +2pp or +2% relative"],
            source_text="rates rise 2%",
        )
    )
    assert v.confirmation_status is sc.ScenarioConfirmationStatus.AWAITING_CONFIRMATION
    assert v.params.interest_rate_change_pp == 0.0


def test_translator_failure_empty_candidate_invalid() -> None:
    with pytest.raises(AppError):
        sc.validate_candidate(sc.TranslationCandidate(candidate={}))


def test_translator_missing_field_means_no_shock_not_default() -> None:
    v = sc.validate_candidate(sc.TranslationCandidate(candidate={"name": "x"}))
    assert v.params.revenue_change_pct == 0.0


def test_translator_extra_field_rejected() -> None:
    with pytest.raises(AppError) as exc:
        sc.validate_candidate(sc.TranslationCandidate(candidate={"name": "x", "confidence": 0.9}))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_confirm_flips_to_validated_with_revalidation() -> None:
    pending = sc.validate_candidate(
        sc.TranslationCandidate(candidate={"name": "x", "revenue_change_pct": -20.0})
    )
    done = sc.confirm(pending)
    assert done.confirmation_status is sc.ScenarioConfirmationStatus.VALIDATED
    assert sc.to_overrides(done).revenue_change == pytest.approx(-0.20)


def test_confirm_requires_awaiting_status() -> None:
    with pytest.raises(AppError) as exc:
        sc.confirm(form({"name": "x"}))
    assert exc.value.code == ErrorCode.RUN_STATE_INVALID


def test_cancel_marks_cancelled() -> None:
    pending = sc.validate_candidate(sc.TranslationCandidate(candidate={"name": "x"}))
    out = sc.cancel(pending)
    assert out.confirmation_status is sc.ScenarioConfirmationStatus.CANCELLED


def test_cancel_requires_awaiting_status() -> None:
    with pytest.raises(AppError) as exc:
        sc.cancel(form({"name": "x"}))
    assert exc.value.code == ErrorCode.RUN_STATE_INVALID


def test_hash_is_sha256_of_canonical_params() -> None:
    v = form({"name": "x", "revenue_change_pct": -20.0})
    canonical = json.dumps(v.params.model_dump(mode="json"), sort_keys=True)
    assert v.provenance.validated_params_hash == hashlib.sha256(canonical.encode()).hexdigest()
    assert len(v.provenance.validated_params_hash) == 64


def test_same_input_identical_result_determinism() -> None:
    a = form({"name": "x", "revenue_change_pct": -20.0})
    b = form({"name": "x", "revenue_change_pct": -20.0})
    assert a == b
    assert a.provenance.validated_params_hash == b.provenance.validated_params_hash


def test_model_level_nonfinite_guard() -> None:
    """Direct-model nonfinite guard (defense in depth behind _apply_bounds)."""
    with pytest.raises(pydantic.ValidationError):
        sc.ScenarioParams(name="x", revenue_change_pct=float("inf"))


def test_unbounded_upper_has_no_clamp_band() -> None:
    assert sc._clamp_limit(None, upper=True) is None
