"""Scoring and Aggregation Engine (Spec §1, §17.2, §20, §21, §22).

Calculates metric 0-100 scores, dimension scores, exact additive contributions,
composite risk score, and severity classifications.
"""

from __future__ import annotations

from backend.risk_engine.contracts import (
    CompositeResult,
    DimensionResult,
    MetricResult,
    MetricStatus,
    SeverityLabel,
    get_severity_label,
)
from backend.risk_engine.registry import (
    DEFAULT_DIMENSION_WEIGHTS,
    DIMENSIONS,
    REGISTRY_VERSION,
    interpolate_score,
)


def score_metric(metric_res: MetricResult, anchors: list[tuple[float, float]]) -> MetricResult:
    """Assign a 0-100 risk score and severity to a calculated metric result.

    A metric may carry ``forced_score`` to encode a frozen edge-case outcome
    (risk-engine.md §2-§8 "Edge cases" column). It is applied verbatim instead of
    interpolating ``value``, so zero-denominator cases land on their frozen target
    score and never produce non-finite values.
    """
    if metric_res.status not in (MetricStatus.VALID, MetricStatus.FLAGGED):
        metric_res.score = None
        metric_res.severity = None
        return metric_res

    if metric_res.forced_score is not None:
        metric_res.score = metric_res.forced_score
        metric_res.severity = get_severity_label(metric_res.score)
        return metric_res

    if metric_res.value is None:
        metric_res.score = None
        metric_res.severity = None
        return metric_res

    score = interpolate_score(metric_res.value, anchors)
    metric_res.score = score
    metric_res.severity = get_severity_label(score)
    return metric_res


def aggregate_dimension(
    dimension_id: str,
    metrics: list[MetricResult],
    configured_weight: float | None = None,
) -> DimensionResult:
    """Aggregate metric scores into a dimension score with exact contributions.

    Dimension score S_d = mean of valid metric scores S_m.
    Metric contribution to dimension C_{m,d} = (1 / N_avail) * S_m.
    """
    if configured_weight is None:
        configured_weight = DEFAULT_DIMENSION_WEIGHTS.get(dimension_id, 1.0 / 7.0)

    dim_name = DIMENSIONS.get(dimension_id, dimension_id.title())
    valid_metrics = [m for m in metrics if m.score is not None]
    total_count = len(metrics)
    available_count = len(valid_metrics)

    if not valid_metrics:
        return DimensionResult(
            dimension_id=dimension_id,
            name=dim_name,
            score=None,
            severity=None,
            weight=configured_weight,
            effective_weight=0.0,
            contribution=0.0,
            metrics=metrics,
            available_count=0,
            total_count=total_count,
        )

    # Equal metric weighting within dimension by default
    metric_weight = 1.0 / available_count
    for m in metrics:
        if m.score is not None:
            m.weight_in_dimension = metric_weight
            m.contribution_to_dimension = metric_weight * m.score
        else:
            m.weight_in_dimension = 0.0
            m.contribution_to_dimension = 0.0

    dim_score = sum(m.contribution_to_dimension for m in valid_metrics)
    clamped_score = max(0.0, min(100.0, dim_score))

    return DimensionResult(
        dimension_id=dimension_id,
        name=dim_name,
        score=clamped_score,
        severity=get_severity_label(clamped_score),
        weight=configured_weight,
        effective_weight=configured_weight,
        contribution=0.0,  # Will be populated during composite aggregation
        metrics=metrics,
        available_count=available_count,
        total_count=total_count,
    )


def aggregate_composite(
    dimension_results: dict[str, DimensionResult],
    custom_weights: dict[str, float] | None = None,
    registry_version: str = REGISTRY_VERSION,
) -> CompositeResult:
    """Aggregate dimension scores into a single weighted composite risk score.

    Composite score S_composite = sum(w'_d * S_d) for available dimensions.
    Exact additive contributions: C_d = w'_d * S_d, sum(C_d) == S_composite.
    Metric contribution to composite C_{m,composite} = w'_d * C_{m,d}.
    """
    weights = custom_weights or DEFAULT_DIMENSION_WEIGHTS.copy()
    available_dims = {k: v for k, v in dimension_results.items() if v.score is not None}
    missing_dims = [k for k, v in dimension_results.items() if v.score is None]

    if not available_dims:
        # No dimension produced a score, so there is no composite to report.
        # Emitting a placeholder value would fabricate risk data (risk-engine.md §1
        # freezes the composite as sum(w_d * S_d) over available dimensions only),
        # so the score stays explicitly unknown and every dimension is listed missing.
        return CompositeResult(
            score=None,
            severity=None,
            registry_version=registry_version,
            dimensions=dimension_results,
            total_contributions=0.0,
            missing_dimensions=missing_dims,
        )

    # Renormalize weights over available dimensions
    total_avail_weight = sum(weights.get(k, 0.0) for k in available_dims)
    if total_avail_weight <= 0:
        normalized_weights = {k: 1.0 / len(available_dims) for k in available_dims}
    else:
        normalized_weights = {k: weights.get(k, 0.0) / total_avail_weight for k in available_dims}

    composite_score = 0.0
    for dim_id, dim_res in dimension_results.items():
        # ``weight`` reports the configured weight actually used for this run
        # (registry defaults or user-supplied); ``effective_weight`` is that value
        # after renormalisation over the available dimensions.
        dim_res.weight = weights.get(dim_id, 0.0)
        dim_res.registry_version = registry_version
        if dim_id in available_dims and dim_res.score is not None:
            w_eff = normalized_weights[dim_id]
            dim_res.effective_weight = w_eff
            dim_res.contribution = w_eff * dim_res.score
            composite_score += dim_res.contribution

            # Propagate metric contribution to composite
            for m in dim_res.metrics:
                if m.score is not None:
                    m.contribution_to_composite = w_eff * m.contribution_to_dimension
                else:
                    m.contribution_to_composite = 0.0
        else:
            dim_res.effective_weight = 0.0
            dim_res.contribution = 0.0

    clamped_composite = max(0.0, min(100.0, composite_score))
    sev = get_severity_label(clamped_composite) or SeverityLabel.MODERATE

    return CompositeResult(
        score=clamped_composite,
        severity=sev,
        registry_version=registry_version,
        dimensions=dimension_results,
        total_contributions=sum(d.contribution for d in dimension_results.values()),
        missing_dimensions=missing_dims,
    )
