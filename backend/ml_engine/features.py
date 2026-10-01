"""Phase 5 ML feature builder.

Builds per-period ratio vectors from raw canonical periods plus
period-over-period deltas and rolling volatility of key ratios.

Leakage rules (frozen spec + plan D-ML5):
- identifiers (company_id), timestamps, generator seeds, anomaly labels,
  and metadata (sector/size/health/currency) NEVER enter the matrix.
- absolute currency-unit levels never enter raw; size/scale enter only via
  scale-free ratios, growth rates, and bounded deltas.
- registry ``score``/``severity`` outputs are Phase 4 judgments and are
  excluded; only measured ratio ``value`` fields are used.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pandas as pd

from backend.ml_engine.contracts import FEATURE_SCHEMA_VERSION
from backend.risk_engine.contracts import MetricStatus
from backend.risk_engine.metrics.credit import calc_dso
from backend.risk_engine.metrics.financial_strength import (
    calc_debt_to_ebitda,
    calc_debt_to_equity,
    calc_gross_margin,
    calc_net_margin,
    calc_operating_margin,
    calc_roa,
    calc_roe,
)
from backend.risk_engine.metrics.liquidity import (
    calc_cash_ratio,
    calc_current_ratio,
    calc_quick_ratio,
    calc_st_obligation_coverage,
)
from backend.risk_engine.metrics.operational import calc_ccc, calc_dio, calc_dpo

# Base ratio features: (feature_name, calculator).
# Only single-period, scale-free calculators are used. History-dependent
# metrics (receivable_trend, revenue_volatility, cash_runway_months),
# listed-only metrics (equity_volatility, beta, var_95, es_95, merton_dd,
# altman_z_distance), exposure-share inputs, concentration buckets, and
# constant defaults (opex_rigidity) are excluded by design.
_BASE_CALCULATORS: tuple[tuple[str, Any], ...] = (
    ("gross_margin", calc_gross_margin),
    ("operating_margin", calc_operating_margin),
    ("net_margin", calc_net_margin),
    ("roa", calc_roa),
    ("roe", calc_roe),
    ("debt_to_equity", calc_debt_to_equity),
    ("debt_to_ebitda", calc_debt_to_ebitda),
    ("current_ratio", calc_current_ratio),
    ("quick_ratio", calc_quick_ratio),
    ("cash_ratio", calc_cash_ratio),
    ("st_obligation_coverage", calc_st_obligation_coverage),
    ("dso", calc_dso),
    ("dio", calc_dio),
    ("dpo", calc_dpo),
)

# Key ratios carrying a delta + rolling-volatility pair each.
_KEY_RATIOS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roa",
    "current_ratio",
    "dso",
)

ROLLING_WINDOW = 12
MIN_ROLLING_OBS = 8

# Identifier / metadata / label columns that must never become features.
FORBIDDEN_COLUMNS = frozenset(
    {
        "company_id",
        "company_name",
        "period_start",
        "period_end",
        "fiscal_year",
        "quarter",
        "frequency",
        "source",
        "currency",
        "sector",
        "size",
        "health",
        "seed",
        "label",
        "injected_label",
        "anomaly",
    }
)


def _period_dict(period: Any) -> dict[str, Any]:
    if hasattr(period, "model_dump"):
        return dict(period.model_dump(mode="python"))
    if isinstance(period, dict):
        return dict(period)
    raise TypeError(f"unsupported period type: {type(period)!r}")


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ordered_columns() -> list[str]:
    return (
        [name for name, _ in _BASE_CALCULATORS]
        + ["ccc"]
        + [f"{name}_delta" for name in _KEY_RATIOS]
        + [f"{name}_rollvol" for name in _KEY_RATIOS]
    )


FEATURE_NAMES: tuple[str, ...] = tuple(_ordered_columns())


def _base_ratio_row(period_dict: dict[str, Any]) -> dict[str, float | None]:
    row: dict[str, float | None] = {}
    for name, calculator in _BASE_CALCULATORS:
        try:
            result = calculator(period_dict)
        except Exception:  # noqa: BLE001 - a failed ratio is a missing feature
            row[name] = None
            continue
        if result.status not in (MetricStatus.VALID, MetricStatus.FLAGGED):
            row[name] = None
        else:
            row[name] = _finite_or_none(result.value)
    try:
        ccc_result = calc_ccc(row.get("dso"), row.get("dio"), row.get("dpo"))
    except Exception:  # noqa: BLE001 - a failed ratio is a missing feature
        ccc_result = None
    if ccc_result is None or ccc_result.status not in (
        MetricStatus.VALID,
        MetricStatus.FLAGGED,
    ):
        row["ccc"] = None
    else:
        row["ccc"] = _finite_or_none(ccc_result.value)
    return row


def build_feature_frame(
    periods: list[Any],
    *,
    company_id: str = "",
) -> pd.DataFrame:
    """Build the Phase 5 ML feature matrix for one company's periods."""
    del company_id  # identifiers never enter the matrix, by contract
    dicts = [_period_dict(period) for period in periods]
    order = sorted(range(len(dicts)), key=lambda i: str(dicts[i].get("period_end")))
    ordered = [dicts[i] for i in order]
    base_rows = [_base_ratio_row(period) for period in ordered]
    frame = pd.DataFrame(base_rows)
    for name in _KEY_RATIOS:
        deltas: list[float | None] = [None] * len(frame)
        vols: list[float | None] = [None] * len(frame)
        history: list[float] = []
        for i in range(len(frame)):
            raw = frame.loc[i, name]
            value = float(raw) if raw is not None and math.isfinite(float(raw)) else None
            if value is not None and history:
                deltas[i] = value - history[-1]
            if value is not None:
                history.append(value)
            window = history[-ROLLING_WINDOW:]
            if len(window) >= MIN_ROLLING_OBS:
                mean = sum(window) / len(window)
                var = sum((v - mean) ** 2 for v in window) / (len(window) - 1)
                vols[i] = math.sqrt(var) if var > 0 else 0.0
        frame[f"{name}_delta"] = deltas
        frame[f"{name}_rollvol"] = vols
    frame = frame[_ordered_columns()]
    forbidden = set(frame.columns) & set(FORBIDDEN_COLUMNS)
    if forbidden:
        raise ValueError(f"leakage: forbidden columns present: {sorted(forbidden)}")
    return frame


def fingerprint_frame(frame: pd.DataFrame, *, config: dict[str, Any]) -> str:
    """Stable SHA-256 fingerprint of a feature matrix plus build config."""
    payload = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "columns": list(frame.columns),
        "rows": [
            [None if v is None or not math.isfinite(float(v)) else float(v) for v in row]
            for row in frame.itertuples(index=False, name=None)
        ],
        "config": config,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
