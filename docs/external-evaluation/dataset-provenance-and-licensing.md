# External Dataset Provenance & Licensing Audit

**Workstream E of the external-evaluation research program.**

This report establishes what can be **independently verified** about the
origin, contents, attribution, and reuse permissions of the two downloaded
datasets. It deliberately separates three things that are often conflated:

1. **Download location** — where the current copy was obtained.
2. **Original source** — who originally collected/published the data.
3. **Applicable license** — the legal terms governing the copy and the
   underlying material.

An identical copy on another platform does **not**, by itself, establish
original provenance or license rights. Nothing here is legal advice.

**Method.** Each candidate source was fetched and inspected this session
(2026-10-11). Authoritative license texts (Open Data Commons, Creative Commons)
and primary repositories (UCI, SEC-filing-derived aggregators) were read
directly. Kaggle dataset pages are JavaScript-rendered and returned only a page
shell this session; that limitation is recorded rather than worked around. **No
new datasets were downloaded or redistributed.**

---

## 1. Summary verdicts

| Dataset | Download location | Original source (verified?) | License | Verdict |
|---|---|---|---|---|
| Bankruptcy.csv | Local: `data/raw/kaggle/bankruptcy/`; reported Kaggle match `lupitaastari/bankruptcy` (`bankruptcy_Test_X.csv`) | **Secondary** (Univ. of Trieste course readme): EMIS, Polish companies, 2000–2012 | **Unverified** (Kaggle page inaccessible) | **LICENSING_RESTRICTED / UNVERIFIED** — do not redistribute |
| Financial Statements.csv | Kaggle `rish59/financial-statements-of-major-companies2009-2023` | **Not independently confirmed** (Kaggle page inaccessible) | ODbL **declared**; ODbL text verified; **applicability unverified** | **LICENSING_RESTRICTED** — ODbL obligations apply if the declaration holds |

Neither dataset license could be **fully verified from its own distribution
page this session**. This is a hard, honest limitation — not a claim that the
licenses are wrong.

---

## 2. Bankruptcy dataset

### 2.1 What is in the file

`Bankruptcy.csv` = `ID + Attr1..Attr64`, **5,000 rows, no outcome label**. The
committed provenance records a **reported row-content equality** with the
upstream `bankruptcy_Test_X.csv` file (Kaggle `lupitaastari/bankruptcy`)
across all 5,000 data rows; headers differ by the ID/X1 alias. This is a
reported match, **not** a verified byte-identical file or whole-file SHA-256
match; it was **not** re-verified here (the Kaggle page is inaccessible).
The companion `bankruptcy_Train.csv` carries the `class` label (0/1) but
is a **different row set** (only 55/5,000 content-identical), so it cannot
label these rows. Supervised evaluation on this file is therefore structurally
unavailable.

### 2.2 Original source — verified via secondary documentation

A University of Trieste course exercise readme
(`Esercizio_impresePL_readme.txt`, "PL" = *imprese polacche* / Polish
companies) documents the dataset's construction:

> "The dataset is about bankruptcy prediction of Polish companies. The data was
> collected from Emerging Markets Information Service (EMIS)… The bankrupt
> companies were analyzed in the period 2000-2012, while the still operating
> companies were evaluated from 2007 to 2013."
>
> "bankruptcy_Train.csv - the training set with both predictors and response
> variable; bankruptcy_Test_X.csv - the test set with ID and predictors"
>
> "class - the response variable Y: 0 = did not bankrupt; 1 = bankrupt"

It also lists `attr1–attr64` as **named financial ratios** (e.g. `attr1` = net
profit / total assets, `attr27` = one if total liability exceeds total assets).
**Source:** https://moodle2.units.it/pluginfile.php/326729/mod_resource/content/0/Esercizio_impresePL_readme.txt
(**secondary** — a course document, not the original publisher; **no license
stated**).

### 2.3 UCI 572 is a *different* dataset — not the source

UCI dataset 572 ("Taiwanese Bankruptcy Prediction", DOI
10.24432/C5004D, CC BY 4.0) is a genuinely labeled, well-documented benchmark:
**6,819 instances, 95 features + `Bankrupt?` target**, Taiwan Economic Journal
1999–2009, no missing values. **Source:**
https://archive.ics.uci.edu/dataset/572/taiwanese+bankruptcy+prediction
(**primary**).

It is **NOT** the source of our anonymized 64-feature file: different feature
count (95 vs 64), different country/source (Taiwan Economic Journal vs
EMIS/Polish), different structure. It is a valid **separate** supervised
benchmark (see the Ground-Truth Feasibility report) but **cannot** be
row-linked to `Attr1–Attr64`, which has no IDs or dates and no published
64↔95 mapping. No such linkage is claimed or attempted.

### 2.4 License status — unverified

The Kaggle `lupitaastari/bankruptcy` page returned only a JS shell
(`Content-Type: text/html`, 9 KB, title only) — **inaccessible this session**.
The Trieste readme states **no license**. Therefore the license governing this
file is **UNVERIFIED**. Absent verification, raw redistribution is **not**
permitted or recommended.

---

## 3. Financial Statements dataset

### 3.1 What is in the file

`Financial Statements.csv` = **161 rows, 12 companies, 2009–2023 annual**, 23
columns. One missing `Market Cap` observation (PYPL 2014). The raw file is
immutable (SHA-256 unchanged).

### 3.2 Download location & declared license

Reported Kaggle source: `rish59/financial-statements-of-major-companies2009-2023`.
The Kaggle page returned only a JS shell this session (**inaccessible**), so
the **declared ODbL license could not be re-confirmed from the page directly**.
The ODbL declaration recorded in `provenance.json` (`license_verified: false`)
therefore stands as an **unverified declaration**, not a verified fact.

### 3.3 Spot-check against primary filings (1 company, 1 year)

Only a single company-year was checked; verifying all 161 rows against primary
filings was **not** performed. **Sample:** Microsoft (MSFT), fiscal year 2023.

| Field | Dataset value | SEC 10-K FY2023 (via filing aggregator) | Match |
|---|---:|---:|:--:|
| Revenue | 211,915 ($211.9B) | $211.91B | ✅ |
| Net Income | 72,361 ($72.4B) | $72.36B | ✅ |

**Source for corroboration:**
https://www.analystlens.com/stocks/msft/10k/fy2023 (a **secondary** aggregator
citing Microsoft's FY2023 Form 10-K filed 2023-07-27; the **primary** source is
the SEC filing on EDGAR). Units are raw USD in the dataset (Revenue 211,915 =
$211.9B); `Market Cap` is separately in $B.

**Interpretation.** One company-year traces to a primary filing, supporting
that the values are real reported figures. This is a **1-of-161 spot-check**; it
does **not** verify the remaining rows, the currency/unit conventions of every
column, or that all values share the same derivation.

### 3.4 Earliest verifiable original publisher

Not independently confirmed this session (Kaggle page inaccessible). The
dataset is a **secondary/derived compilation** of company financial statements;
its values appear consistent with primary filings (per §3.3), but the
compiler's data-collection method is undocumented in an accessible primary
source. Treat the compiler (Kaggle `rish59`) as the **reported** source.

---

## 4. License texts (verified) and obligations

### 4.1 ODbL 1.0 (Open Data Commons) — governs Financial Statements *if* declared

**Source (authoritative, verified):**
https://opendatacommons.org/licenses/odbl/1-0/

Key obligations for a database under ODbL:

- **Attribution (§4.4):** must give credit proportional to the contribution.
- **Notice of changes (§4.5):** altered/derived databases must carry notice.
- **Share-alike on Derivative Databases (§5.2):** a Derivative Database offered
  publicly must be licensed under ODbL or a later/compatible version.
- **Public use of a Derivative Database (§5.2.1):** must offer the adapted
  database (or its contents) under ODbL.
- **Produced Works are exempt from share-alike (§1.0, §5.2.1(b)):** analysis
  results, charts, and reports *produced from* the database are not required to
  be shared alike.
- **Commercial use is permitted** (no non-commercial clause), subject to the
  above. Database Rights are addressed for EU jurisdictions.

**Practical consequence for this project.** Our derived metrics, charts, and
the evaluation report are **Produced Works** (no share-alike trigger). If we
ever publicly distribute an *adapted database* built from it, ODbL share-alike
would apply. Since applicability of ODbL to the Kaggle copy is **unverified**,
this section is contingent.

### 4.2 CC BY 4.0 (Creative Commons) — governs UCI 572 (separate benchmark)

**Source (authoritative, verified):**
https://creativecommons.org/licenses/by/4.0/legalcode

Key terms:

- **Attribution (§3(a)):** required — give appropriate credit, link to license,
  indicate changes.
- **Commercial use permitted; modification/derivatives permitted; redistribution
  permitted** under attribution.
- **No share-alike obligation.**
- **Sui Generis Database Rights (§4):** extraction/reuse of substantial database
  contents is permitted with attribution.

**Consequence.** UCI 572 is the most permissive, well-verified option for a
future labeled benchmark: CC BY 4.0 permits research and commercial reuse with
attribution and **no** share-alike.

---

## 5. Evidence quality

| Claim | Source URL | Type | Status |
|---|---|---|---|
| ODbL 1.0 obligations (attribution, share-alike, produced works) | opendatacommons.org/licenses/odbl/1-0/ | Primary (license authority) | **Verified** |
| CC BY 4.0 obligations (attribution, commercial OK, no share-alike) | creativecommons.org/licenses/by/4.0/legalcode | Primary (license authority) | **Verified** |
| UCI 572: 6,819 instances, 95 features, `Bankrupt?` target, CC BY 4.0, DOI 10.24432/C5004D | archive.ics.uci.edu/dataset/572/... | Primary (UCI) | **Verified** |
| MSFT FY2023 Revenue $211.91B / Net Income $72.36B (dataset matches) | analystlens.com/stocks/msft/10k/fy2023 | Secondary (cites SEC 10-K) | **Verified** (secondary) |
| Bankruptcy file origin = EMIS, Polish companies; `Attr1–64` = financial ratios; `class` 0/1 | moodle2.units.it/.../Esercizio_impresePL_readme.txt | Secondary (course doc) | **Verified** (secondary; no license) |
| Kaggle `rish59/...` ODbL declaration | kaggle.com/datasets/rish59/... | Aggregator | **Inaccessible** (JS shell) → unverified |
| Kaggle `lupitaastari/bankruptcy` license & file list | kaggle.com/datasets/lupitaastari/bankruptcy | Aggregator | **Inaccessible** (JS shell) → unverified |
| Reported row-content equality across all 5,000 data rows; headers differ by the ID/X1 alias. Whole-file byte identity and SHA-256 equality have not been established. | (prior session) | — | **Reported, not re-verified** |

---

## 6. Remaining unknowns and their impact

- **L-1 — Licenses of both Kaggle copies unverified this session.** Impact: raw
  redistribution is **not** recommended for either dataset. This does **not**
  block the existing internal analysis (already performed on local copies) or
  any *Produced Works* (reports/charts), but blocks republishing the raw CSVs.
- **L-2 — Original publisher of the Financial Statements compilation not
  independently confirmed.** Impact: attribution wording must credit the Kaggle
  compiler as the *reported* source, not a verified primary publisher.
- **L-3 — Only 1/161 FS rows spot-checked against filings.** Impact: field
  definitions, units, and per-column derivations are not uniformly verified.
- **L-4 — No license stated in the Trieste readme.** Impact: the Bankruptcy
  file's reuse terms remain unknown.
- **L-5 — No forecasting horizon defined for UCI 572.** Impact: any *predictive*
  claim on that benchmark requires defining the horizon first (see Ground-Truth
  Feasibility report).

---

## 7. Recommendations

1. **Do not redistribute either raw CSV** in the public repository. Keep them
   local/immutable (current practice).
2. **For a future labeled benchmark, prefer UCI 572** — CC BY 4.0, verified,
   genuine `Bankrupt?` labels, 95 features — as a **separate** experiment, never
   joined to the anonymized 64-feature file.
3. **If ODbL applicability is later confirmed** for the Financial Statements
   copy, add attribution in the README/report and keep derived outputs as
   **Produced Works** (no share-alike). Confirm the Kaggle license from a
   non-JS source before relying on it.
4. **Expand the FS spot-check** to a defined, reported sample (e.g., 3–5
   company-years across the 12 firms) before making any data-quality claim.
5. **Treat the Trieste readme as the attribution source** for the Bankruptcy
   file's semantics (EMIS, Polish companies), while its license stays unknown.

---

## 8. Reproduction of this audit

Every URL above was fetched this session via the standard web-fetch tool; the
MSFT figures were corroborated against a filing-citing aggregator. Raw-file
integrity is enforced by SHA-256 (both hashes match the recorded values). No
license is claimed as verified unless the authoritative license text or primary
repository page was read directly.
