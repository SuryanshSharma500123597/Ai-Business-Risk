"""Isolation Forest wrapper and rolling z-score / IQR rule baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

DEFAULT_RANDOM_STATE = 42
DEFAULT_N_ESTIMATORS = 200
DEFAULT_MAX_FEATURES = 1.0

RULE_WINDOW = 12
RULE_MIN_PERIODS = 8
RULE_Z_THRESHOLD = 3.0
RULE_IQR_MULTIPLIER = 1.5


@dataclass
class IsolationForestConfig:
    n_estimators: int = DEFAULT_N_ESTIMATORS
    max_samples: str = "auto"
    max_features: float = DEFAULT_MAX_FEATURES
    bootstrap: bool = False
    random_state: int = DEFAULT_RANDOM_STATE

    def build(self) -> IsolationForest:
        return IsolationForest(
            n_estimators=self.n_estimators,
            max_samples=self.max_samples,
            max_features=self.max_features,
            bootstrap=self.bootstrap,
            random_state=self.random_state,
            n_jobs=1,
        )


@dataclass
class FittedIsolationForest:
    """Fitted IF model plus median/IQR preprocessing state."""

    model: IsolationForest
    feature_names: list[str] = field(default_factory=list)
    medians: dict[str, float] = field(default_factory=dict)
    iqrs: dict[str, float] = field(default_factory=dict)
    train_decision: list[float] = field(default_factory=list)
    random_state: int = DEFAULT_RANDOM_STATE
    config: dict[str, Any] = field(default_factory=dict)

    def scaled_matrix(self, frame: pd.DataFrame) -> np.ndarray:
        ordered = frame[self.feature_names]
        scaled = ordered.copy()
        for name in self.feature_names:
            median = self.medians.get(name, 0.0)
            iqr = self.iqrs.get(name, 1.0) or 1.0
            scaled[name] = (ordered[name] - median) / iqr
        return scaled.to_numpy(dtype=float)

    def decision_values(self, frame: pd.DataFrame) -> list[float]:
        raw = self.model.decision_function(self.scaled_matrix(frame))
        return [float(v) for v in raw]

    def anomaly_scores(self, frame: pd.DataFrame) -> list[float]:
        """Rank-CDF normalized scores in [0, 1]; higher = more anomalous."""
        current = self.decision_values(frame)
        pooled = sorted([-v for v in self.train_decision] + [-v for v in current])
        total = len(pooled)
        scores: list[float] = []
        for value in current:
            rank = sum(1 for v in pooled if v <= -value) / total
            scores.append(min(1.0, max(0.0, rank)))
        return scores


def _robust_params(frame: pd.DataFrame) -> tuple[dict[str, float], dict[str, float]]:
    medians: dict[str, float] = {}
    iqrs: dict[str, float] = {}
    for name in frame.columns:
        series = frame[name].dropna().to_numpy(dtype=float)
        if len(series) == 0:
            medians[name] = 0.0
            iqrs[name] = 1.0
            continue
        median = float(np.median(series))
        quartiles = np.percentile(series, [75, 25])
        iqr = float(quartiles[0] - quartiles[1])
        medians[name] = median
        iqrs[name] = iqr if iqr > 0 else 1.0
    return medians, iqrs


def fit_isolation_forest(
    frame: pd.DataFrame,
    *,
    config: IsolationForestConfig | None = None,
) -> FittedIsolationForest:
    """Fit an Isolation Forest on complete training rows only."""
    cfg = config or IsolationForestConfig()
    complete = frame.dropna()
    if complete.empty:
        raise ValueError("no complete feature rows available for training")
    medians, iqrs = _robust_params(complete)
    model = cfg.build()
    scaled = complete.copy()
    for name in complete.columns:
        scaled[name] = (complete[name] - medians[name]) / (iqrs[name] or 1.0)
    matrix = scaled.to_numpy(dtype=float)
    model.fit(matrix)
    train_decision = [float(v) for v in model.decision_function(matrix)]
    return FittedIsolationForest(
        model=model,
        feature_names=list(complete.columns),
        medians=medians,
        iqrs=iqrs,
        train_decision=train_decision,
        random_state=cfg.random_state,
        config={
            "n_estimators": cfg.n_estimators,
            "max_samples": cfg.max_samples,
            "max_features": cfg.max_features,
            "bootstrap": cfg.bootstrap,
            "random_state": cfg.random_state,
        },
    )


def threshold_from_expected_rate(train_decision: list[float], expected_rate: float) -> float:
    """Operating threshold on ``-decision_function`` at an expected rate."""
    if not 0.0 < expected_rate < 1.0:
        raise ValueError("expected_rate must be in (0, 1)")
    ordered = sorted(-v for v in train_decision)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * (1.0 - expected_rate))))
    return float(ordered[index])
