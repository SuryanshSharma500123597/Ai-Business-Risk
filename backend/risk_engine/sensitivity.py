"""Sensitivity Analysis Module (Spec §1, §17.2, §23, §24).

Perturbs dimension weights +/- 20% (renormalized), recomputes composite risk scores,
evaluates score stability ranges, and tracks dimension rank order shifts.
"""

from __future__ import annotations

from backend.risk_engine.contracts import (
    DimensionResult,
    SensitivityResult,
    SensitivityScenario,
)
from backend.risk_engine.registry import DEFAULT_DIMENSION_WEIGHTS
from backend.risk_engine.scoring import aggregate_composite


def _calculate_spearman_rank(rank1: list[str], rank2: list[str]) -> float:
    """Calculate Spearman rank correlation between two dimension orderings."""
    if len(rank1) <= 1 or len(rank1) != len(rank2):
        return 1.0

    pos1 = {item: i for i, item in enumerate(rank1)}
    pos2 = {item: i for i, item in enumerate(rank2)}

    n = len(rank1)
    d_sq_sum = sum((pos1[item] - pos2[item]) ** 2 for item in rank1)
    return 1.0 - (6.0 * d_sq_sum) / (n * (n**3 - n))


def _snapshot(
    dimension_results: dict[str, DimensionResult],
) -> dict[str, DimensionResult]:
    """Independent copies of the dimension results.

    ``aggregate_composite`` populates ``effective_weight``/``contribution`` by
    mutating the ``DimensionResult`` objects it is given. Sensitivity re-runs
    aggregation once per perturbed scenario, so it must never hand the caller's
    objects to it — otherwise the final scenario's perturbed weights would
    overwrite the baseline contributions already published in the report and
    break the frozen exact-additivity invariant (``sum(C_d) == S_composite``,
    risk-engine.md §1, spec §22 L1).
    """
    return {dim_id: result.model_copy(deep=True) for dim_id, result in dimension_results.items()}


def run_sensitivity_analysis(
    dimension_results: dict[str, DimensionResult],
    base_weights: dict[str, float] | None = None,
    perturbation_pct: float = 0.20,
) -> SensitivityResult:
    """Run weight sensitivity analysis with +/- 20% weight perturbations."""
    baseline = aggregate_composite(_snapshot(dimension_results), custom_weights=base_weights)
    baseline_score = baseline.score

    weights = (
        base_weights
        if base_weights is not None
        else {k: DEFAULT_DIMENSION_WEIGHTS.get(k, 1.0 / 7.0) for k in dimension_results}
    )
    available_dims = [k for k, v in dimension_results.items() if v.score is not None]

    if not available_dims:
        return SensitivityResult(
            baseline_score=baseline_score,
            min_score=baseline_score,
            max_score=baseline_score,
            score_range=0.0,
            scenarios=[],
            rank_stability_score=1.0,
        )

    # Baseline dimension rank ordering (highest risk score to lowest)
    baseline_ranks = sorted(
        available_dims, key=lambda k: dimension_results[k].score or 0.0, reverse=True
    )

    scenarios: list[SensitivityScenario] = []
    scores: list[float] = [] if baseline_score is None else [baseline_score]
    rank_correlations: list[float] = []

    for dim_id in available_dims:
        for direction in (+perturbation_pct, -perturbation_pct):
            new_weights = weights.copy()
            orig_w = new_weights.get(dim_id, 1.0 / len(weights))
            perturbed_w = orig_w * (1.0 + direction)
            new_weights[dim_id] = perturbed_w

            # Renormalize other weights
            other_sum = sum(w for k, w in weights.items() if k != dim_id)
            target_other_sum = 1.0 - perturbed_w
            if other_sum > 0 and target_other_sum > 0:
                for k in weights:
                    if k != dim_id:
                        new_weights[k] = weights[k] * (target_other_sum / other_sum)

            scen_result = aggregate_composite(
                _snapshot(dimension_results), custom_weights=new_weights
            )
            scen_score = scen_result.score
            if scen_score is None:
                # Unreachable: this loop iterates dimensions that are available, and
                # aggregate_composite always scores when at least one dimension is available.
                continue
            scores.append(scen_score)

            scen_ranks = sorted(
                available_dims, key=lambda k: scen_result.dimensions[k].score or 0.0, reverse=True
            )
            corr = _calculate_spearman_rank(baseline_ranks, scen_ranks)
            rank_correlations.append(corr)

            scenarios.append(
                SensitivityScenario(
                    perturbed_dimension=dim_id,
                    direction=direction,
                    weights=new_weights,
                    composite_score=scen_score,
                    dimension_ranks=scen_ranks,
                )
            )

    min_s = min(scores)
    max_s = max(scores)
    avg_corr = sum(rank_correlations) / len(rank_correlations) if rank_correlations else 1.0

    return SensitivityResult(
        baseline_score=baseline_score,
        min_score=min_s,
        max_score=max_s,
        score_range=max_s - min_s,
        scenarios=scenarios,
        rank_stability_score=max(-1.0, min(1.0, avg_corr)),
    )
