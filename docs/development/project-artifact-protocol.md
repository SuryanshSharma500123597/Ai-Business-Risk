# Project Artifact Protocol

Permanent rules for every artifact this project produces. Applies to code, data,
reports, figures, and generated graphs.

## 0. The workflow (apply to every phase or substantial experiment)

Each phase or substantial experiment runs the same lifecycle. Sections 1–12 below
are the standing rules that make each step safe; this section is the order you run
them in. The full per-phase record lives in `docs/development-log.md` (newest first)
and the phase's own `phase-report.md` where one exists.

1. **Plan before coding.** Record, in the development-log entry (or a scoped plan the
   entry points to): the objective, explicit **scope** (in and out), assumptions,
   dependencies, the deliverables, **acceptance criteria** (the observable conditions
   that mean "done"), and the **approval gate** (what must be reviewed before commit).
   No implementation starts before the acceptance criteria are written down.
2. **Implement with a decision log.** As you build, log every significant decision:
   the options considered, the one chosen, and why. Note any deviation from the plan
   and its reason. Record files created and modified. Keep the log in the phase report
   (`phase-report.md` §"Decisions" precedent: Phase 8 §2 "Locked decisions A–L").
3. **Prove it.** Run the relevant tests and static checks (§3, §5, §6) and record the
   **actual** results — counts, exit codes, failures — never "should pass".
4. **Save real outputs.** Regenerate every artifact from source (§1) with a documented
   reproduction command; save figures under `docs/assets/` (§8); write notebooks and
   execute them (§9); record provenance and hashes (§2).
5. **Close with a phase report.** Write `phase-report.md` covering implementation, the
   actual test results, generated outputs, **limitations**, **deferred items**
   (labelled `D-x-y`, see § below), and **known failures** — honestly, including any
   frozen invariant a result contradicts rather than smoothing it over.
6. **Update the surface.** Update `docs/development-log.md` (newest-first entry with an
   Approval gate), the README documentation map, and regenerate Graphify (§10) after
   meaningful structural changes.
7. **Verify and stop.** Confirm raw-input hashes, frozen-phase integrity (§6), and the
   Git diff (§11); report; then **stop for user review before commit or push** (§12).

Deferred items follow the existing convention: a stable label (`D-6-3`, `D-1`, …) plus a
one-line reason and its gate. "Deferred" means recorded and unblocked-for-later, never
silently dropped.

## 1. Regenerate, never hand-edit

Any file under `data/processed/` and any PNG under `docs/assets/` is **generated
output**. It must be reproducible from source by a single command:

```bash
python -m backend.external_data.run_experiment   # external Kaggle evaluation
```

Never edit these files by hand, and never commit a figure that was not produced by
the generator. If an output is wrong, fix the generator and regenerate.

The exception is documentation: Markdown and `.ipynb` narrative cells are authored
directly, but any number or claim they contain must trace back to a generated
artifact.

## 2. Raw inputs are read-only

Files under `data/raw/` are opened read-only, never rewritten. `run_experiment.py`
hashes each raw CSV (SHA-256) before and after the run and aborts if it changed,
which is what makes the recorded hashes a real integrity guarantee rather than a
comment. Provenance for each run is written to
`data/processed/kaggle/<dataset>/provenance.json`.

Recorded hashes (verified before and after the current run):

| Raw file | SHA-256 |
| --- | --- |
| `data/raw/kaggle/bankruptcy/Bankruptcy.csv` | `4d3c07357112cd3839d3c813363743777be032f2899604ba01219a9936eeba64` |
| `data/raw/kaggle/financial statements/Financial Statements.csv` | `32e38512643a626340b43a4255bf79d45a7afc66ffe9058326507cc2885cb1b5` |

## 3. No fabricated results

An unsupported computation is recorded as an explicit unavailable outcome, never as
a placeholder number. Concretely: label-gated metrics (PR-AUC, ROC-AUC, precision,
recall, F1, confusion matrices) exist only when genuine labels exist. Both external
datasets are unlabeled, so those slots emit honest "unavailable" notices and
`evaluation.json` records `"available": false` with a reason string.

The same rule forced two corrections in this layer, and they are the precedent for
future work:

- **Baseline applicability.** The frozen rolling z-score/IQR baseline assumes an
  ordered temporal series. Applied to a cross-sectional matrix it produces a
  confident but meaningless flag rate (4615/5000 = 92.3 %). It is now
  applicability-gated: bankruptcy is recorded as unavailable, and the
  financial-statements panel is evaluated per company in ascending year order so
  no window crosses a company boundary or sees the future.
- **Method naming.** The Phase 5 explanation path emits the internal label
  `shap_exact`, which the frozen golden fixture depends on. That label is a
  misnomer: no TreeSHAP/TreeExplainer is used. The identifier is preserved for
  fixture compatibility while `explainer_runtime_class` records the actual runtime
  class and `attribution_method` describes it accurately.

**Rule:** when a frozen identifier and a factual description disagree, preserve the
identifier and correct the description. Never silently rename what a fixture pins.

## 4. Determinism

Runs are seeded (seed 42) and must be bit-reproducible: same raw inputs, same
artifacts. Row sampling is evenly spaced and index-based, timestamps are never
computation inputs, and figures are written with the Agg backend at DPI 200 with
software tags stripped. Re-running the experiment twice must produce identical
bytes; if it does not, the nondeterminism is a bug.

## 5. Verify before claiming

No step is reported complete without evidence: a test run, a hash comparison, an
execution count, or a real file listing. Report actual output, including failures
and blockers. "It should work" is not a result.

## 6. Frozen phases stay frozen

Phases 4–8 (scoring formulas, anomaly methodology, Digital Twin, scenario
contracts, stress testing) and the golden fixtures are inputs to external
evaluation, not targets of it. Improving an external metric by editing frozen
methodology invalidates the experiment. The external layer may only *wrap*,
*gate*, or *choose whether to call* frozen code — never modify it. `git diff -- backend/`
against frozen paths must stay empty.

## 7. Dependency discipline

No new dependency is added for analysis work. Figures use the matplotlib already
pinned; models use the scikit-learn and shap already declared in `pyproject.toml`.
New packages change the reproducibility surface and need explicit justification.

## 8. Artifact-to-doc linkage

Every report claim cites a real file, and the assets README lists every PNG in
`docs/assets/external-evaluation/`. Stale references are treated as bugs: if a
figure is renamed or regenerated, its documentation is updated in the same change.

## 9. Notebooks

Notebooks are reproducible research surfaces, not production code (see
`docs/03_data-engineering/`). A notebook is only complete when it has been
executed top-to-bottom with zero error outputs and all code cells carry an
execution count. Notebooks must not reimplement project logic; they import it from
`backend/`.

## 10. Generated graphs

`graphify-out/` is tool output and is git-ignored (see `.gitignore`). Graphs are
regenerated on demand and never hand-edited or committed.

## 11. What belongs in Git

Commit intent, not bulk. Version-control source, tests, phase reports, the
development log, README, this protocol, executed notebooks, and **selected evidence**
(small, deterministic figures under `docs/assets/` and small machine-readable
summaries that cite the corrected results). Keep out of Git — via `.gitignore`, not by
deleting files:

- raw datasets and anything under `data/raw/` and `data/synthetic/`;
- secrets and credentials (`.env`), virtual environments, and caches;
- large reproducible intermediates under `data/processed/` — they regenerate from one
  command (§1), so keep only the small evidence summaries that the report cites;
- logs, temporary scratch scripts, and local databases.

Before staging, run `git status --short` and `git diff --stat`; never use
`git add .`. Confirm the diff contains only intended changes and that no frozen file,
raw dataset, or golden fixture appears.

## 12. Stop for review

No phase commits or pushes on its own. The final step is always a report plus a
**stop** for user review. An approval gate in the development-log entry states
explicitly that no commit or push has occurred and that review is required.
