"""Risk Engine evaluation over external canonical datasets (Phase 3).

Runs the *unmodified* ``QuantitativeRiskEngine`` on per-company datasets built
by ``financial_statements``. Metrics whose inputs are absent come back as
``MISSING_INPUT`` (score ``None``), dimensions without any valid metric report
no score, and the composite only aggregates available dimensions — the frozen
no-fabrication behavior. Mapping facts are recorded, never forced.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from backend.external_data.financial_statements import company_datasets
from backend.risk_engine.engine import QuantitativeRiskEngine


def evaluate_companies(
    frame: pd.DataFrame,
    *,
    engine: QuantitativeRiskEngine | None = None,
) -> dict[str, Any]:
    """Evaluate every company; return raw reports plus JSON-ready dumps."""
    risk_engine = engine or QuantitativeRiskEngine()
    datasets = company_datasets(frame)
    raw: dict[str, Any] = {}
    dumped: dict[str, Any] = {}
    for company, data in datasets.items():
        report = risk_engine.evaluate_company(data)
        raw[company] = report
        dumped[company] = report.model_dump(mode="json")
    return {"raw": raw, "dumped": dumped}


def availability_summary(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Aggregate metric/dimension availability across companies (empirical).

    This *is* the Phase 3 mapping evidence: for every registry metric we record
    how many companies produced a VALID/FLAGGED result versus MISSING_INPUT,
    with a sample value and unit.
    """
    metric_facts: dict[str, dict[str, Any]] = {}
    dimension_scores: dict[str, dict[str, float | None]] = {}
    composite_scores: dict[str, float | None] = {}
    for company, report in evaluation["raw"].items():
        for metric in report.metrics:
            facts = metric_facts.setdefault(
                metric.metric_id,
                {
                    "metric_id": metric.metric_id,
                    "dimension": metric.dimension,
                    "unit": metric.unit,
                    "statuses": {},
                    "sample_values": [],
                },
            )
            status = str(metric.status)
            facts["statuses"][status] = facts["statuses"].get(status, 0) + 1
            if metric.value is not None and len(facts["sample_values"]) < 3:
                facts["sample_values"].append(round(float(metric.value), 6))
        for dimension_id, dimension in report.composite.dimensions.items():
            dimension_scores.setdefault(dimension_id, {})[company] = dimension.score
        composite_scores[company] = report.composite.score
    computable = sum(
        1
        for facts in metric_facts.values()
        if any(status in ("valid", "flagged") for status in facts["statuses"])
    )
    return {
        "metrics": dict(sorted(metric_facts.items())),
        "metrics_computable": computable,
        "metrics_total": len(metric_facts),
        "dimension_scores": dimension_scores,
        "composite_scores": composite_scores,
    }
