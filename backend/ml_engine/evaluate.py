"""Evaluation of IF anomaly scores vs injected labels and the rule baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from backend.ml_engine.contracts import SYNTHETIC_EVAL_DISCLAIMER

Verdict = Literal["if_beats_baseline", "baseline_wins_or_tie", "insufficient_labels"]


def _roc_auc(scores: list[float], labels: list[bool]) -> float:
    positives = [s for s, flag in zip(scores, labels, strict=True) if flag]
    negatives = [s for s, flag in zip(scores, labels, strict=True) if not flag]
    if not positives or not negatives:
        return 0.5
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def _pr_auc(scores: list[float], labels: list[bool]) -> float:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    total_pos = sum(1 for flag in labels if flag)
    if total_pos == 0:
        return 0.0
    area = 0.0
    hits = 0
    prev_recall = 0.0
    for rank, index in enumerate(order, start=1):
        if labels[index]:
            hits += 1
            recall = hits / total_pos
            area += (hits / rank) * (recall - prev_recall)
            prev_recall = recall
    return area


def _prf_at_flags(flags: list[bool], labels: list[bool]) -> dict[str, float]:
    true_pos = sum(1 for f, y in zip(flags, labels, strict=True) if f and y)
    false_pos = sum(1 for f, y in zip(flags, labels, strict=True) if f and not y)
    false_neg = sum(1 for f, y in zip(flags, labels, strict=True) if not f and y)
    true_neg = sum(1 for f, y in zip(flags, labels, strict=True) if not f and not y)
    precision = true_pos / (true_pos + false_pos) if (true_pos + false_pos) else 0.0
    recall = true_pos / (true_pos + false_neg) if (true_pos + false_neg) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = false_pos / (false_pos + true_neg) if (false_pos + true_neg) else 0.0
    fnr = false_neg / (false_neg + true_pos) if (false_neg + true_pos) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "fnr": fnr,
        "true_positives": float(true_pos),
    }


def _precision_recall_at_k(scores: list[float], labels: list[bool], k: int) -> dict[str, float]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: max(k, 1)]
    hits = sum(1 for i in order if labels[i])
    total_pos = sum(1 for flag in labels if flag)
    denom = min(max(k, 1), len(scores))
    return {
        f"precision_at_{k}": hits / denom if denom else 0.0,
        f"recall_at_{k}": hits / total_pos if total_pos else 0.0,
    }


@dataclass
class MethodScores:
    roc_auc: float = 0.5
    pr_auc: float = 0.0
    metrics_at_threshold: dict[str, float] = field(default_factory=dict)
    at_k: dict[str, float] = field(default_factory=dict)


@dataclass
class EvaluationReport:
    model: MethodScores = field(default_factory=MethodScores)
    baseline: MethodScores = field(default_factory=MethodScores)
    verdict: Verdict = "insufficient_labels"
    dataset_fingerprint: str = ""
    threshold_policy: str = ""
    limitation: str = SYNTHETIC_EVAL_DISCLAIMER
    detail: dict[str, Any] = field(default_factory=dict)


def evaluate_methods(
    *,
    model_scores: list[float],
    model_flags: list[bool],
    baseline_scores: list[float],
    baseline_flags: list[bool],
    labels: list[bool],
    k_values: tuple[int, ...] = (5, 10),
    dataset_fingerprint: str = "",
    threshold_policy: str = "",
) -> EvaluationReport:
    """Score IF and baseline on identical labels with the frozen metric set."""
    n = len(labels)
    aligned = (
        len(model_scores) == len(model_flags) == len(baseline_scores) == len(baseline_flags) == n
    )
    if not aligned:
        raise ValueError("evaluation inputs must align row-for-row")
    if sum(1 for flag in labels if flag) == 0:
        return EvaluationReport(
            dataset_fingerprint=dataset_fingerprint,
            threshold_policy=threshold_policy,
            verdict="insufficient_labels",
        )
    model_at_k: dict[str, float] = {}
    baseline_at_k: dict[str, float] = {}
    for k in k_values:
        model_at_k.update(_precision_recall_at_k(model_scores, labels, k))
        baseline_at_k.update(_precision_recall_at_k(baseline_scores, labels, k))
    model = MethodScores(
        roc_auc=_roc_auc(model_scores, labels),
        pr_auc=_pr_auc(model_scores, labels),
        metrics_at_threshold=_prf_at_flags(model_flags, labels),
        at_k=model_at_k,
    )
    baseline = MethodScores(
        roc_auc=_roc_auc(baseline_scores, labels),
        pr_auc=_pr_auc(baseline_scores, labels),
        metrics_at_threshold=_prf_at_flags(baseline_flags, labels),
        at_k=baseline_at_k,
    )
    model_f1 = model.metrics_at_threshold["f1"]
    baseline_f1 = baseline.metrics_at_threshold["f1"]
    verdict: Verdict = (
        "if_beats_baseline"
        if model.pr_auc > baseline.pr_auc and model_f1 > baseline_f1
        else "baseline_wins_or_tie"
    )
    return EvaluationReport(
        model=model,
        baseline=baseline,
        verdict=verdict,
        dataset_fingerprint=dataset_fingerprint,
        threshold_policy=threshold_policy,
        detail={"n_periods": n, "n_injected": sum(1 for flag in labels if flag)},
    )
