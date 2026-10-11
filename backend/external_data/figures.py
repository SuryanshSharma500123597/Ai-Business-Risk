"""Publication-quality deterministic figures for the external evaluation (Phase 16-17).

Rules enforced here:
- Agg backend (no display, headless-safe).
- dpi >= 180, descriptive titles, axis labels, legends, no clipped labels
  (``bbox_inches="tight"``).
- No timestamps, no absolute paths, no fabricated data — each function only
  plots values it is given.
- ``metadata={"Software": None}`` strips software tags from PNG bytes.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DPI = 200
COLORS = (
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A4E3",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
    "#D37295",
    "#B07AA1",
    "#FFBE7D",
    "#57A194",
)
GRID_ALPHA = 0.3


def _save(fig: plt.Figure, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=DPI, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return target


def _style_axes(ax: plt.Axes) -> None:
    ax.grid(True, alpha=GRID_ALPHA, linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def feature_distributions(
    frame: pd.DataFrame,
    columns: list[str],
    path: str | Path,
    *,
    title: str,
    max_panels: int = 12,
) -> Path:
    """Histogram grid over a deterministic subset of feature columns."""
    shown = columns[:max_panels]
    ncols = 3
    nrows = int(np.ceil(len(shown) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 2.4 * nrows))
    axes_flat = np.atleast_1d(axes).ravel()
    for index, column in enumerate(shown):
        ax = axes_flat[index]
        values = pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy(dtype=float)
        ax.hist(
            values,
            bins=40,
            color=COLORS[index % len(COLORS)],
            edgecolor="white",
            linewidth=0.3,
        )
        _style_axes(ax)
        ax.set_title(column, fontsize=9)
        ax.set_xlabel("value", fontsize=8)
        ax.set_ylabel("count", fontsize=8)
        ax.tick_params(labelsize=7)
    for index in range(len(shown), len(axes_flat)):
        axes_flat[index].set_visible(False)
    fig.suptitle(title, fontsize=11, y=1.0)
    fig.tight_layout()
    return _save(fig, path)


def anomaly_score_distribution(
    scores: list[float],
    path: str | Path,
    *,
    title: str,
    threshold: float | None = None,
    flagged: list[bool] | None = None,
) -> Path:
    """Anomaly-score histogram with the operating threshold marked."""
    values = np.asarray(scores, dtype=float)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.hist(values, bins=40, color=COLORS[0], edgecolor="white", linewidth=0.4, label="all rows")
    if flagged is not None:
        flags = np.asarray(flagged, dtype=bool)
        if flags.any():
            ax.hist(
                values[flags],
                bins=40,
                color=COLORS[2],
                edgecolor="white",
                linewidth=0.4,
                label="flagged at operating threshold",
            )
    _style_axes(ax)
    if threshold is not None:
        ax.axvline(
            threshold,
            color="#333333",
            linestyle="--",
            linewidth=1.2,
            label=f"threshold = {threshold:.3f}",
        )
    ax.set_xlabel("anomaly score (higher = more anomalous)")
    ax.set_ylabel("rows")
    ax.set_title(title, fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    return _save(fig, path)


def shap_summary(
    attribution_matrix: np.ndarray,
    feature_names: list[str],
    path: str | Path,
    *,
    title: str,
    top_k: int = 15,
) -> Path:
    """Deterministic strip plot of per-row attributions for top features.

    Features are ranked by mean |attribution| (the project's
    ``global_summary`` ranking convention); row positions use a fixed
    evenly-spaced jitter so pixels are reproducible.
    """
    means = np.abs(attribution_matrix).mean(axis=0)
    order = np.argsort(means)[::-1][:top_k][::-1]
    fig, ax = plt.subplots(figsize=(8.2, 0.42 * len(order) + 1.6))
    n_rows = attribution_matrix.shape[0]
    jitter = np.linspace(-0.28, 0.28, max(n_rows, 2))
    for position, feature_index in enumerate(order):
        values = attribution_matrix[:, feature_index]
        colors = np.where(values >= 0, COLORS[0], COLORS[2])
        ax.scatter(
            values,
            position + jitter[: len(values)],
            s=9,
            c=colors,
            alpha=0.65,
            linewidths=0,
        )
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([str(feature_names[i]) for i in order], fontsize=8)
    ax.axvline(0.0, color="#333333", linewidth=0.8)
    _style_axes(ax)
    ax.set_xlabel("attribution to isolation decision (negative = pushes anomalous)")
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def dataset_overview(
    coverage: pd.DataFrame,
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Company x year coverage heatmap (1 = observation present)."""
    fig, ax = plt.subplots(figsize=(9.0, 0.45 * len(coverage.index) + 1.8))
    ax.imshow(coverage.to_numpy(dtype=float), aspect="auto", cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(coverage.columns)))
    ax.set_xticklabels([str(c) for c in coverage.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(coverage.index)))
    ax.set_yticklabels([str(i) for i in coverage.index], fontsize=8)
    ax.set_xlabel("year")
    ax.set_ylabel("company")
    ax.set_title(title, fontsize=11)
    ax.grid(False)
    fig.tight_layout()
    return _save(fig, path)


def company_coverage(
    per_company: dict[str, int],
    path: str | Path,
    *,
    title: str,
    minimum_periods: int | None = 12,
) -> Path:
    """Observation count per company with the >=12-period reference line."""
    names = sorted(per_company)
    counts = [per_company[name] for name in names]
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    bars = ax.bar(names, counts, color=[COLORS[i % len(COLORS)] for i in range(len(names))])
    if minimum_periods is not None:
        ax.axhline(
            minimum_periods,
            color="#333333",
            linestyle="--",
            linewidth=1.1,
            label=f"{minimum_periods}-period reference (monthly Digital Twin minimum)",
        )
        ax.legend(frameon=False, fontsize=8)
    for bar, count in zip(bars, counts, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            count + 0.15,
            str(count),
            ha="center",
            fontsize=8,
        )
    _style_axes(ax)
    ax.set_ylabel("annual observations")
    ax.set_xlabel("company")
    ax.set_title(title, fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return _save(fig, path)


def financial_trends(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    title: str,
    value_columns: list[str] | None = None,
) -> Path:
    """Per-company annual trend lines, one panel per financial column."""
    columns = value_columns or ["Revenue"]
    fig, axes = plt.subplots(
        len(columns),
        1,
        figsize=(8.6, 3.9 * len(columns)),
        squeeze=False,
        sharex=True,
    )
    companies = sorted(frame["Company"].unique())
    for panel, value_column in enumerate(columns):
        ax = axes[panel][0]
        for index, company in enumerate(companies):
            subset = frame[frame["Company"] == company].sort_values("Year", kind="mergesort")
            ax.plot(
                subset["Year"],
                subset[value_column],
                marker="o",
                markersize=3,
                linewidth=1.3,
                color=COLORS[index % len(COLORS)],
                label=str(company),
            )
        _style_axes(ax)
        ax.set_ylabel(f"{value_column} (source units)")
        ax.set_title(f"{value_column} by year", fontsize=10)
        if panel == 0:
            ax.legend(frameon=False, fontsize=7, ncol=3, loc="best")
    axes[-1][0].set_xlabel("year")
    fig.suptitle(title, fontsize=11, y=1.0)
    fig.tight_layout()
    return _save(fig, path)



def risk_dimension_distribution(
    dimension_scores: dict[str, dict[str, float | None]],
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Company-level scores per Risk Engine dimension (None = unavailable)."""
    dimensions = sorted(dimension_scores)
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    width = 0.8 / max(len(dimensions), 1)
    dimension_colors = {
        "financial_strength": COLORS[0],
        "liquidity": COLORS[1],
        "market": COLORS[2],
        "credit": COLORS[3],
        "operational": COLORS[4],
        "concentration": COLORS[5],
        "macro": COLORS[6],
    }
    companies = sorted(next(iter(dimension_scores.values())))
    for position, dimension_id in enumerate(dimensions):
        values = []
        for company in companies:
            score = dimension_scores[dimension_id][company]
            values.append(np.nan if score is None else score)
        xs = np.arange(len(companies)) + position * width - 0.4 + width / 2
        ax.bar(
            xs,
            values,
            width=width * 0.94,
            color=dimension_colors.get(dimension_id, COLORS[position % len(COLORS)]),
            label=dimension_id,
        )
    ax.set_xticks(np.arange(len(companies)) + 0.4 - width / 2)
    ax.set_xticklabels(companies, rotation=30, ha="right", fontsize=8)
    _style_axes(ax)
    ax.set_ylabel("dimension risk score (0-100)")
    ax.set_xlabel("company")
    ax.set_title(title, fontsize=11)
    ax.legend(frameon=False, fontsize=7, ncol=4)
    fig.tight_layout()
    return _save(fig, path)


def anomaly_results_scatter(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    title: str,
    score_column: str = "anomaly_score",
    flag_column: str = "flagged",
) -> Path:
    """Anomaly score by year; flagged rows highlighted."""
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    companies = sorted(frame["Company"].unique())
    for index, company in enumerate(companies):
        subset = frame[frame["Company"] == company].sort_values("Year", kind="mergesort")
        ax.plot(
            subset["Year"],
            subset[score_column],
            linewidth=1.0,
            color=COLORS[index % len(COLORS)],
            alpha=0.75,
            label=str(company),
        )
        flagged = subset[subset[flag_column].astype(bool)]
        ax.scatter(
            flagged["Year"],
            flagged[score_column],
            marker="X",
            s=60,
            color=COLORS[2],
            edgecolor="#333333",
            linewidth=0.5,
            zorder=3,
        )
    _style_axes(ax)
    ax.set_xlabel("year")
    ax.set_ylabel("anomaly score (0-1)")
    ax.set_title(title + "  [X = flagged at operating threshold]", fontsize=11)
    ax.legend(frameon=False, fontsize=7, ncol=3)
    fig.tight_layout()
    return _save(fig, path)


def unavailable_notice(
    path: str | Path,
    *,
    title: str,
    lines: list[str],
) -> Path:
    """Honest placeholder PNG for a requested output the data cannot support.

    Used only for label-gated outputs (PR/ROC/confusion/class-distribution)
    where computing the plot would require fabricated labels. The PNG states
    exactly why the output is unavailable instead of fabricating it.
    """
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.text(0.5, 0.72, "output unavailable", ha="center", va="center", fontsize=14, color="#555555")
    wrapped = "\n".join(lines)
    ax.text(0.5, 0.42, wrapped, ha="center", va="center", fontsize=10, color="#333333")
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    return _save(fig, path)


def risk_dimension_comparison(
    coverage_matrix: pd.DataFrame,
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Cross-dataset risk-dimension computability (0 = none, 1 = fully)."""
    fig, ax = plt.subplots(figsize=(7.6, 0.6 * len(coverage_matrix.index) + 1.8))
    ax.imshow(coverage_matrix.to_numpy(dtype=float), cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(coverage_matrix.columns)))
    ax.set_xticklabels([str(c) for c in coverage_matrix.columns], fontsize=9)
    ax.set_yticks(range(len(coverage_matrix.index)))
    ax.set_yticklabels([str(i) for i in coverage_matrix.index], fontsize=8)
    for row in range(coverage_matrix.shape[0]):
        for column in range(coverage_matrix.shape[1]):
            value = float(coverage_matrix.iloc[row, column])
            ax.text(
                column,
                row,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=8,
                color="#222222",
            )
    ax.set_title(title, fontsize=11)
    ax.grid(False)
    fig.tight_layout()
    return _save(fig, path)


def model_comparison_placeholder(
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Honest placeholder for the supervised-comparison chart (no labels)."""
    return unavailable_notice(
        path,
        title=title,
        lines=[
            "No genuine labels exist for either dataset,",
            "so no supervised reference model was trained",
            "and no PR-AUC/ROC-AUC comparison can be plotted.",
            "Unsupervised flag rates are tabulated in the report.",
        ],
    )


def feature_importance_comparison(
    importance_by_dataset: dict[str, dict[str, float]],
    path: str | Path,
    *,
    title: str,
    top_k: int = 10,
) -> Path:
    """Top mean |attribution| features per dataset (normalized within panel)."""
    datasets = sorted(importance_by_dataset)
    fig, axes = plt.subplots(1, len(datasets), figsize=(6.4 * len(datasets), 5.0), squeeze=False)
    for panel, dataset_id in enumerate(datasets):
        ax = axes[0][panel]
        importance = importance_by_dataset[dataset_id]
        ranked = sorted(importance.items(), key=lambda item: item[1], reverse=True)[:top_k][::-1]
        if not ranked:
            ax.text(0.5, 0.5, "no attributions", ha="center", va="center")
            ax.set_axis_off()
            continue
        names = [item[0] for item in ranked]
        values = [item[1] for item in ranked]
        peak = max(values) or 1.0
        normalized = [value / peak for value in values]
        ax.barh(names, normalized, color=COLORS[panel % len(COLORS)])
        _style_axes(ax)
        ax.set_xlabel("mean |attribution| (normalized within dataset)")
        ax.set_title(f"{dataset_id} (top {top_k})", fontsize=10)
        ax.tick_params(axis="y", labelsize=8)
    fig.suptitle(title, fontsize=11, y=1.0)
    fig.tight_layout()
    return _save(fig, path)
