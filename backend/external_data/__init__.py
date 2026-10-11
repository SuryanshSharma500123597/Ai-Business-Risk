"""External Kaggle dataset evaluation layer (isolated from the frozen core).

Public surface used by the experiment runner, notebook, and tests. Nothing in
this package modifies Risk Engine formulas, Phase 5 methodology, Digital Twin
equations, scenario/stress contracts, or golden fixtures.
"""

from __future__ import annotations

from backend.external_data.bankruptcy import (
    load_bankruptcy,
)
from backend.external_data.contracts import (
    EXPECTED_ANOMALY_RATE,
    EXTERNAL_EVAL_VERSION,
    RANDOM_SEED,
    AnomalyRun,
    DatasetAudit,
    EvaluationOutcome,
    LeakageReport,
    PreprocessingConfig,
)
from backend.external_data.evaluation import (
    evaluate_against_labels,
    run_isolation_forest,
    unavailable_evaluation,
)
from backend.external_data.financial_statements import (
    company_datasets,
    load_financial_statements,
    panel_summary,
)
from backend.external_data.provenance import sha256_file

__all__ = [
    "EXPECTED_ANOMALY_RATE",
    "EXTERNAL_EVAL_VERSION",
    "RANDOM_SEED",
    "AnomalyRun",
    "DatasetAudit",
    "EvaluationOutcome",
    "LeakageReport",
    "PreprocessingConfig",
    "company_datasets",
    "evaluate_against_labels",
    "load_bankruptcy",
    "load_financial_statements",
    "panel_summary",
    "run_isolation_forest",
    "sha256_file",
    "unavailable_evaluation",
]
