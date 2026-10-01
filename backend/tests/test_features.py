from __future__ import annotations

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.features import (
    coverage_frame,
    exposure_frame,
    numeric_financial_frame,
    prepare_features,
)
from backend.data_engine.ingest.synthetic import generate_company


def test_features_are_raw_and_keep_missing_values() -> None:
    company = generate_company(SyntheticCompanyConfig(seed=1001))
    company.periods[0] = company.periods[0].model_copy(update={"tax": None, "fx_exposure": None})
    frame = numeric_financial_frame(company.periods)
    assert len(frame) == len(company.periods)
    assert frame.loc[0, "tax"] != frame.loc[0, "tax"]  # pandas NaN, not an invented zero
    assert "revenue_margin" not in frame.columns
    assert "revenue_growth" not in frame.columns
    exposures = exposure_frame(company.periods)
    assert "fx_exposure_foreign_revenue_share" in exposures.columns
    value = exposures.loc[0, "fx_exposure_foreign_revenue_share"]
    assert value != value  # NaN confirms missingness was not imputed.


def test_features_include_coverage_without_changing_raw_fields() -> None:
    company = generate_company(SyntheticCompanyConfig(seed=1002))
    frame, metadata = prepare_features(company)
    flags = coverage_frame(company.periods)
    assert len(frame) == len(flags) == 24
    assert frame["has_revenue"].all()
    assert metadata["required_coverage_pct"] == 100.0
    assert metadata["blocked"] is False
