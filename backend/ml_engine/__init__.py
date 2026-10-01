"""ML Engine for anomaly detection (Phase 5).

Deterministic Isolation Forest anomaly detection with SHAP attribution,
benchmarked against a rolling z-score / IQR rule baseline.

Architecture rule R3: this package must never import from ``agents``,
``llm``, ``app``, or ``services`` (enforced by
``backend/tests/unit/test_architecture_imports.py``).
"""

from __future__ import annotations
