# External Evaluation Figures

All PNGs here are generated deterministically (DPI 200, Agg backend). The `bankruptcy/`,
`financial-statements/` and cross-dataset comparison charts come from
`python -m backend.external_data.run_experiment`; `cross-dataset/threshold-sensitivity.png` and
`cross-dataset/seed-rank-stability.png` come from `python -m backend.external_data.stability`.
No fabricated curves: label-gated
slots (PR/ROC/confusion/class-distribution/model-comparison) are honest "unavailable"
notices explaining that no genuine labels exist.

**No UCI figures exist.** The UCI supervised benchmark
([report](../../external-evaluation/uci-bankruptcy-benchmark-report.md)) is tabular evidence only:
report tables plus `data/processed/uci-bankruptcy/benchmark_results.json`.

## bankruptcy/ (8)

- `feature-distributions.png` — 12-panel histograms of the first 12 of 64 anonymized Attr columns
- `anomaly-score-distribution.png` — frozen Phase 5 score distribution + threshold + flagged overlay
- `shap-summary.png` — global mean |attribution| over 100 sampled rows (Phase 5 path: permutation-family Shapley estimator; frozen label shap_exact is a known misnomer, see report section 13)
- `dataset-class-distribution.png` — **unavailable notice** (unlabeled test matrix)
- `pr-curve.png` — **unavailable notice** (no labels)
- `roc-curve.png` — **unavailable notice** (no labels)
- `confusion-matrix.png` — **unavailable notice** (no labels)
- `model-comparison.png` — **unavailable notice** (no supervised model possible)

## financial-statements/ (6)

- `dataset-overview.png` — company × year coverage heatmap (2009–2023)
- `company-coverage.png` — observations per company vs. 12-period monthly-Twin reference
- `financial-trends.png` — Revenue / Net Income / EBITDA by company (source units)
- `risk-dimension-distribution.png` — Risk Engine dimension scores per company (0–100, None = unavailable)
- `anomaly-results.png` — anomaly score by year, flagged rows marked (score-vs-year scatter)
- `shap-summary.png` — global mean |attribution| over 100 sampled rows (Phase 5 path: permutation-family Shapley estimator; frozen label shap_exact is a known misnomer, see report section 13)

## cross-dataset/ (5 PNG + 1 JSON + 1 CSV)

- `risk-dimension-comparison.png` — dimension computability heatmap (bankruptcy vs. financial-statements)
- `feature-importance-comparison.png` — top mean |attribution| features per dataset (normalized within panel)
- `model-performance-comparison.png` — **unavailable notice** (neither dataset has labels)
- `threshold-sensitivity.png` — frozen-IF flagged count vs. expected-rate operating point (Workstream C1)
- `seed-rank-stability.png` — frozen-IF Spearman rank correlation vs. seed (Workstream C2)
- `comparison-summary.json` — independent-evaluation comparison record (no merging)
- `model-performance-comparison.csv` — observation/feature/flag counts per dataset

## Related reports

- [External financial dataset evaluation](../../external-evaluation/external-financial-dataset-evaluation.md)
- [Anomaly stability & threshold sensitivity analysis](../../external-evaluation/anomaly-stability-analysis.md) — source of the two stability figures above
- [UCI bankruptcy benchmark plan](../../external-evaluation/uci-bankruptcy-benchmark-plan.md)
- [UCI bankruptcy benchmark report](../../external-evaluation/uci-bankruptcy-benchmark-report.md)
- [Dataset provenance & licensing audit](../../external-evaluation/dataset-provenance-and-licensing.md)
- [Ground-truth feasibility](../../external-evaluation/ground-truth-feasibility.md)
- [Digital Twin & stress validation report](../../external-evaluation/digital-twin-stress-validation-report.md)
