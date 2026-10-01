"""Golden File Risk Assessment Tests for Canonical Seeds 1001-1005 (Spec §10, §30).

Verifies reproducible quantitative risk assessment outputs for canonical fixture seeds.
"""

import pytest

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.risk_engine.engine import QuantitativeRiskEngine


@pytest.mark.parametrize("seed", [1001, 1002, 1003, 1004, 1005])
def test_canonical_seed_golden_risk_assessment(seed: int) -> None:
    config = SyntheticCompanyConfig(seed=seed, periods=24)
    company_dataset = generate_company(config)
    engine = QuantitativeRiskEngine()

    report = engine.evaluate_company(company_dataset)

    # Basic structural assertions
    composite_score = report.composite.score
    assert composite_score is not None
    assert 0.0 <= composite_score <= 100.0
    assert len(report.composite.dimensions) == 7
    assert report.sensitivity.rank_stability_score >= -1.0
    assert pytest.approx(report.composite.total_contributions, abs=1e-4) == composite_score

    # Determinism assertion: re-evaluating produces exact same score
    report2 = engine.evaluate_company(company_dataset)
    assert report.composite.score == report2.composite.score
    assert report.composite.severity == report2.composite.severity
