# Ground-Truth Recovery — Feasibility Report

**Project:** AI Business Risk — Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform
**Workstream:** A (Master Setback Resolution, Gate 2) · **Type:** Research/feasibility only — no labels obtained, no data downloaded, no models trained
**Baseline commit:** `dd6ac7e` (`feat(evaluation): add external financial dataset evaluation`) · **Report date:** 2026-10-10

---

## 1. Purpose and scope

The committed external-evaluation experiment (`docs/external-evaluation/external-financial-dataset-evaluation.md`)
established that **neither provided Kaggle dataset carries genuine outcome labels**, so all supervised
evaluation was correctly marked unavailable. This report answers the natural follow-up: **can a credible,
independently verifiable bankruptcy / financial-distress dataset with real labels be obtained to enable a
future supervised evaluation of AI Business Risk?**

In scope:
- Identify credible candidate datasets with genuine outcome labels.
- Verify source identity, license, linkage feasibility, label definition, prediction horizon, and sample size — to the extent public evidence permits.
- Distinguish verified facts from unverified claims and research assumptions.
- Produce a `FEASIBLE` / `BLOCKED` / `LICENSING_RESTRICTED` verdict per candidate.

Out of scope (explicit):
- **Downloading** any raw data, redistributing raw data, or installing dependencies.
- Training models or producing any supervised metric.
- Relabeling or joining the existing anonymized `Attr1–Attr64` rows (see §6 — this is shown to be impossible).

---

## 2. Why the current data cannot yield labels (restated as the problem statement)

Verified against the live repository (`data/raw/kaggle/…`, `data/processed/kaggle/*/provenance.json`):

| Dataset | Rows | Label? | Company ID? | Dates? | Features |
|---|---:|---|---|---|---|
| `bankruptcy/Bankruptcy.csv` | 5,000 | **No** (`Attr1–Attr64` + `ID` only) | No | No | 64 anonymized |
| `financial statements/Financial Statements.csv` | 161 | **No** (no target column) | Yes (`Company`) | Yes (`Year`, 2009–2023) | 20 numeric |

The bankruptcy file is the anonymized competition **test** feature matrix; its companion labeled train file
was previously shown to overlap only **55 / 5,000** rows, and the authoritative upstream download failed
(no Kaggle credentials). This is the blocker Workstream A exists to resolve.

---

## 3. Research process (reproducible description)

1. Confirmed live state: branch `main`, HEAD `dd6ac7e`, in sync with `origin/main`; only the six expected
   untracked intermediates present.
2. Re-read the existing report §1/§3/§6/§20/§22 and both `provenance.json` files to avoid duplicating the
   completed search (Kaggle credentials, 55/5,000 overlap, FS ODbL caveat).
3. Fetched the authoritative UCI dataset page (id 572) — license, instance/feature counts, target definition,
   anonymization, source, missing-value status all read directly from the page.
4. Fetched the Florida-UCLA-LoPucki BRD **FAQ** and **Use Conditions** pages — access model and copyright
   read directly.
5. Attempted to fetch two Kaggle dataset pages; they are JavaScript-rendered and did **not** return body
   content in this environment (documented as an access limitation, §8).
6. No downloads, installs, training, or file modifications occurred.

**Coverage caveat:** this is a **targeted** survey of three credible candidate families most likely to fit the
project's needs, not an exhaustive census of all financial-distress datasets.

---

## 4. Candidate comparison

| # | Candidate | Source / URL | Rows | Target | Company ID? | Dates? | License (status) | Verdict |
|---|---|---|---:|---|---|---|---|---|
| 1 | Taiwanese Bankruptcy Prediction (UCI 572) | `archive.ics.uci.edu/dataset/572` | **6,819** | `Bankrupt?` (0/1) | No (anonymized) | No (1999–2009 only as a range) | **CC BY 4.0 — VERIFIED** | **FEASIBLE** (independent benchmark) |
| 2 | Company Bankruptcy Prediction (Kaggle mirror of #1) | `kaggle.com/datasets/fedesoriano/company-bankruptcy-prediction` | 6,819 (mirror) | `Bankrupt?` (0/1) | No | No | Reported CC BY 4.0 — **NOT independently verified this session** | FEASIBLE (license unverified) |
| 3 | Florida-UCLA-LoPucki BRD | `lopucki.law.ufl.edu` | ~1,000+ (large-cap bankruptcies only) | Bankruptcy case (all positive) | **Yes** | **Yes (filing dates)** | Copyright UF/UCLA/LoPucki; registration + click-through agreement; **no explicit commercial/redistribution grant** | **BLOCKED** (access + licensing) |

---

## 5. Candidate details, label semantics, and licensing evidence

### 5.1 Candidate 1 — UCI 572 Taiwanese Bankruptcy Prediction — **FEASIBLE**

**Verified facts (from the UCI page):**
- **Instances:** 6,819 firms · **Features:** 95 (`X1…X95`) + **1 target** `Bankrupt?`.
- **Target definition:** `Bankrupt?` (integer, 0/1); bankruptcy defined per **Taiwan Stock Exchange business regulations**.
- **License:** **Creative Commons Attribution 4.0 International (CC BY 4.0)** — explicitly stated on the page
  (DOI `10.24432/C5004D`). This permits sharing and adaptation **with attribution**; redistribution of the raw
  data is permitted under these terms.
- **Anonymization:** fully anonymized — **no company identifiers, no observation dates** (only the 1999–2009
  collection window is stated).
- **Missing values:** none. Source: Taiwan Economic Journal, 1999–2009.

**Label semantics / horizon:** the `Bankrupt?` label reflects bankruptcy status under TWSE regulations for the
observation period. **The UCI metadata retrieved does not state an explicit forecasting horizon** (e.g., "1-year
ahead"); the financial ratios and the label describe the same firm-period. For a *prediction* framing, the
analyst must define and document the horizon explicitly rather than assume one (see §7 limitation L-4).

**Sample-size caveat:** this dataset is well known to be **highly class-imbalanced** (bankruptcies are a small
minority). The exact positive count/percentage was **not independently recomputed this session** and must be
confirmed at load time before any thresholding; PR-AUC (not ROC-AUC/accuracy) is the appropriate primary metric.

**Relationship to our existing file:** this dataset is the **95-feature origin lineage** of the anonymized
64-attribute competition file. It has a *different feature space* (95 vs 64) and no identifiers/dates.

### 5.2 Candidate 2 — Kaggle mirror — **FEASIBLE, license UNVERIFIED**

Widely used Kaggle mirror of the same UCI 572 Taiwan data (96 columns incl. `Bankrupt?`; no company names or
dates). Its declared license is commonly **CC BY 4.0**, but the Kaggle page is JavaScript-rendered and **did not
render in this environment**, so the license could **not be independently confirmed this session**. Because
candidate 1 provides the *same data* under a **verified** CC BY 4.0 license directly from UCI, the mirror adds
no licensing advantage and is **not recommended** over UCI.

### 5.3 Candidate 3 — Florida-UCLA-LoPucki BRD — **BLOCKED**

**Verified facts (from the LoPucki FAQ + Use Conditions pages):**
- Contains ~**1,000+ large public-company bankruptcy cases** with **200+ regression-ready fields**; data sourced
  from **PACER court files and SEC filings**.
- **Company identities and filing dates ARE present** — the only candidate with genuine entity + temporal info.
- **Access model (verified):** download of the Cases Table requires **registration** and acceptance of use
  conditions; **copyright is asserted** by UF/UCLA/LoPucki over the selection/organization and custom data items;
  **attribution is mandatory**; **no explicit commercial-use or redistribution grant** is provided.
- **Population limitation:** the BRD contains **only bankruptcy cases (all positive labels)** — it has no
  matched sample of non-bankrupt control firms, so it cannot support classification alone without an external
  control sample.


---

## 6. Linkage of labels to the EXISTING `Attr1–Attr64` rows — **NOT POSSIBLE**

This is the decisive feasibility result and is independent of which candidate is chosen:

- The existing 5,000 rows are **anonymized**: no company identifier, no date, and an intentional lossy
  encoding into **64** attributes.
- **No candidate carries identifiers or dates that could join to those rows.** Candidate 1/2 are themselves
  anonymized and use **95** features; candidate 3 has identities/dates but covers *different* firms (large US
  public bankruptcies) that cannot appear in the Taiwan anonymized set.
- The only theoretical join is **exact row-content matching** on the shared attributes, but the **64↔95 feature
  mapping is not published** (the anonymization is deliberate), and the prior investigation already showed the
  Kaggle companion train file overlapped only **55/5,000** rows.

**Conclusion:** new labels **cannot** be legitimately attached to the existing anonymized file. Any supervised
evaluation must be run as a **self-contained, independent experiment** on a labeled dataset in its own right —
not as a relabeling of the current 5,000 rows.

---

## 7. Feasibility verdict and recommendation

| Question | Answer |
|---|---|
| Can supervised evaluation of AI Business Risk be run at all? | **Yes** — on a genuinely labeled dataset (UCI 572, CC BY 4.0). |
| Can we relabel the existing anonymized `Attr1–Attr64` file? | **No** — anonymized, no IDs/dates, feature-space mismatch (§6). |
| Is any candidate ready to use without further action? | **Candidate 1 (UCI 572)** is the only one with a **verified** license and genuine labels. |
| Recommended next step | Treat **UCI 572** as a **new independent labeled benchmark** for a future Workstream D. Confirm class balance and define the prediction horizon **before** training. Do **not** merge with the existing file. |

**Remaining limitations (honest):**
- **L-1 — Not exhaustive:** only three candidate families were investigated this session.
- **L-2 — Kaggle license unverified:** candidate 2's page did not render; irrelevant given candidate 1's verified license.
- **L-3 — No data downloaded:** all facts are from public documentation pages; no raw file was retrieved or hashed.
- **L-4 — Horizon undefined:** UCI 572 metadata does not state a forecasting horizon; it must be defined and documented for any *predictive* claim.
- **L-5 — Class balance unverified:** positive-class rate for UCI 572 must be measured at load time (assumed imbalanced).
- **L-6 — Feature mapping unknown:** no published mapping between our 64 attributes and UCI's 95 features; none was assumed.

---

## 8. Access limitations encountered

- **Kaggle dataset pages** (`fedesoriano/company-bankruptcy-prediction` and its `/data` tab) are
  JavaScript-rendered and returned only page titles in this environment; their body metadata (including the
  declared license badge) could not be read. This is recorded rather than worked around.
- **No Kaggle API credentials** are configured (previously established), so no download was attempted.
- All conclusions above rest on facts read directly from the **UCI** and **LoPucki** authoritative pages, which
  did render.

---

## 9. Source references

- UCI Machine Learning Repository, *Taiwanese Bankruptcy Prediction* (id 572), CC BY 4.0, DOI `10.24432/C5004D`:
  `https://archive.ics.uci.edu/dataset/572/taiwanese+bankruptcy+prediction`
- Kaggle, *Company Bankruptcy Prediction* (`fedesoriano/company-bankruptcy-prediction`) — mirror of UCI 572;
  license not independently verified this session:
  `https://www.kaggle.com/datasets/fedesoriano/company-bankruptcy-prediction`
- Florida-UCLA-LoPucki Bankruptcy Research Database — FAQ:
  `https://lopucki.law.ufl.edu/frequently_asked_questions.php`
- Florida-UCLA-LoPucki Bankruptcy Research Database — Use Conditions:
  `https://lopucki.law.ufl.edu/conditions_of_use.php`
- Existing project evidence: `docs/external-evaluation/external-financial-dataset-evaluation.md` (§3, §6, §20, §22);
  `data/processed/kaggle/bankruptcy/provenance.json`; `data/processed/kaggle/financial-statements/provenance.json`.
