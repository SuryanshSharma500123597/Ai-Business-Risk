"""Unit tests for Phase 5 ML feature builder: leakage rules and determinism."""

from __future__ import annotations

from backend.data_engine.contracts import GeneratedCompany, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.ml_engine.features import (
    FEATURE_NAMES,
    FORBIDDEN_COLUMNS,
    build_feature_frame,
    fingerprint_frame,
)


def _company(seed: int = 1001, periods: int = 24) -> GeneratedCompany:
    return generate_company(SyntheticCompanyConfig(seed=seed, periods=periods))


def test_feature_schema_has_expected_shape() -> None:
    frame = build_feature_frame(_company().periods)
    assert list(frame.columns) == list(FEATURE_NAMES)
    assert frame.shape == (24, 27)


def test_forbidden_columns_never_in_matrix() -> None:
    frame = build_feature_frame(_company().periods)
    assert not (set(frame.columns) & set(FORBIDDEN_COLUMNS))
    for forbidden in ("company_id", "seed", "label", "sector", "currency", "period_end"):
        assert forbidden not in frame.columns


def test_absolute_currency_levels_never_enter_raw() -> None:
    company = _company()
    frame = build_feature_frame(company.periods)
    for column in frame.columns:
        assert column not in {
            "revenue",
            "cash",
            "total_assets",
            "total_debt",
            "ebitda",
            "net_income",
        }


def test_registry_scores_never_become_features() -> None:
    frame = build_feature_frame(_company().periods)
    for column in frame.columns:
        assert "score" not in column
        assert "severity" not in column


def test_feature_build_is_deterministic() -> None:
    first = build_feature_frame(_company().periods)
    second = build_feature_frame(_company().periods)
    assert first.equals(second)
    config = {"seed": 1001}
    assert fingerprint_frame(first, config=config) == fingerprint_frame(second, config=config)


def test_deltas_use_trailing_values_only() -> None:
    frame = build_feature_frame(_company().periods)
    # First period has no trailing history, so all deltas are missing.
    assert frame.loc[0, [c for c in frame.columns if c.endswith("_delta")]].isna().all()
    # A later delta equals current minus previous base value.
    current = frame.loc[5, "gross_margin"]
    previous = frame.loc[4, "gross_margin"]
    assert frame.loc[5, "gross_margin_delta"] == current - previous


def test_rolling_volatility_needs_minimum_history() -> None:
    frame = build_feature_frame(_company().periods)
    vol_columns = [c for c in frame.columns if c.endswith("_rollvol")]
    assert frame.loc[0, vol_columns].isna().all()
    assert frame.loc[10, vol_columns].notna().all()


def test_period_dict_supports_mapping_and_rejects_other_types() -> None:
    import pytest

    from backend.ml_engine.features import _period_dict

    assert _period_dict({"revenue": 1}) == {"revenue": 1}
    with pytest.raises(TypeError, match="unsupported period type"):
        _period_dict(42)


def test_finite_or_none_guards() -> None:
    from backend.ml_engine.features import _finite_or_none

    assert _finite_or_none(None) is None
    assert _finite_or_none("not-a-number") is None
    assert _finite_or_none(float("inf")) is None
    assert _finite_or_none(2.5) == 2.5


def test_malformed_period_values_become_missing_features() -> None:
    company = _company(seed=1001, periods=12)
    dump = company.periods[0].model_dump(mode="python")

    all_none = {key: None for key in dump}
    none_frame = build_feature_frame([all_none])
    assert none_frame["gross_margin"].isna().all()
    assert none_frame["ccc"].isna().all()

    with_string = dict(dump)
    with_string["revenue"] = "oops"
    string_frame = build_feature_frame([with_string])
    assert string_frame["gross_margin"].isna().all()
