"""Rolling z-score / IQR rule baseline on the same feature matrix."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

RULE_WINDOW = 12
RULE_MIN_PERIODS = 8
RULE_Z_THRESHOLD = 3.0
RULE_IQR_MULTIPLIER = 1.5


@dataclass
class RuleBaselineResult:
    flags: list[bool] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    breached_features: list[list[str]] = field(default_factory=list)


def rolling_rule_baseline(
    frame: pd.DataFrame,
    *,
    window: int = RULE_WINDOW,
    min_periods: int = RULE_MIN_PERIODS,
    z_threshold: float = RULE_Z_THRESHOLD,
    iqr_multiplier: float = RULE_IQR_MULTIPLIER,
) -> RuleBaselineResult:
    """Rolling z-score / IQR rule using trailing windows only (no leakage)."""
    flags: list[bool] = []
    scores: list[float] = []
    breached: list[list[str]] = []
    for i in range(len(frame)):
        history = frame.iloc[max(0, i - window) : i]
        row = frame.iloc[i]
        period_flag = False
        period_breached: list[str] = []
        period_score = 0.0
        for name in frame.columns:
            hist = history[name].dropna().to_numpy(dtype=float)
            current = row[name]
            try:
                current_f = float(current)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(current_f) or len(hist) < min_periods:
                continue
            mean = float(np.mean(hist))
            std = float(np.std(hist, ddof=1)) if len(hist) > 1 else 0.0
            z_value = abs(current_f - mean) / std if std > 0 else 0.0
            quartiles = np.percentile(hist, [75, 25])
            iqr = float(quartiles[0] - quartiles[1])
            lower = float(quartiles[1]) - iqr_multiplier * iqr
            upper = float(quartiles[0]) + iqr_multiplier * iqr
            iqr_breach = bool(iqr > 0 and (current_f < lower or current_f > upper))
            period_score = max(period_score, z_value)
            if z_value >= z_threshold or iqr_breach:
                period_flag = True
                period_breached.append(name)
        flags.append(period_flag)
        scores.append(period_score)
        breached.append(sorted(period_breached))
    return RuleBaselineResult(flags=flags, scores=scores, breached_features=breached)
