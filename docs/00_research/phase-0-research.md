# AI Business Risk — Phase 0 Research Report

**Project:** AI Business Risk — Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform
**Phase:** 0 — Research + Master Specification
**Research date:** 2026-09-21 (all URLs accessed on this date)

> **Verification rule.** Every external claim in this document was checked against the cited source
> during the research session on 2026-09-21. Claims that could not be confirmed from a primary source
> (or from a clearly-labeled secondary source) are marked **NOT VERIFIED** and must be re-verified in a
> later phase before being relied upon. Nothing in this document is fabricated. Where a figure comes
> from third-party reporting rather than the vendor itself, that is stated explicitly.

---

## 1. Method

Research was performed via web search and direct fetch of official pages: standards bodies (ISO, COSO),
regulators (BIS, U.S. Federal Reserve, U.S. SEC, St. Louis Fed, World Bank), vendor sites, arXiv,
GitHub, and PyPI. Coverage areas:

1. How business-risk management works in practice (frameworks and process models).
2. Existing commercial system categories (ERM/GRC, financial analytics, BI, credit risk, AI risk, LLM analysts, multi-agent frameworks, simulation approaches).
3. Academic and open-source literature relevant to the proposed system.
4. Stress-testing methodology.
5. Quantitative finance foundations (formulas the risk engine will implement).
6. Data sources: **source vs access method**, licensing, coverage, limitations.
7. LLM provider landscape for the reasoning layer.

---

## 2. How business-risk management works in the real world

Modern enterprise risk management (ERM) follows two canonical reference frameworks:

**ISO 31000:2018** (second edition, published February 2018) defines risk as the *“effect of uncertainty
on objectives”* and organizes risk management into three pillars:

- **Principles** (led by “value creation and protection”; includes integrated, structured &
  comprehensive, customized, inclusive, dynamic, best available information, human & cultural factors,
  continual improvement).
- **Framework** (leadership & commitment, integration, design, implementation, evaluation, improvement).
- **Process**: communication & consultation → **scope, context, criteria** → **risk assessment**
  (identification → analysis → evaluation) → **risk treatment** → **monitoring & review** →
  **recording & reporting**.

**COSO ERM 2017** — *“Enterprise Risk Management — Integrating with Strategy and Performance”* —
contains **5 components and 20 principles**: (1) Governance and Culture, (2) Strategy and
Objective-Setting, (3) Performance, (4) Review and Revision, (5) Information, Communication, and
Reporting.

**Implication for this project.** Both frameworks place *risk assessment* (identify → analyze →
evaluate) inside a larger governance loop owned by humans. Our platform automates and deepens the
assessment/quantification/scenario portion of that loop and produces auditable evidence for the human
governance steps. It does **not** replace governance, treatment decisions, or accountability.

---

## 3. Existing systems landscape

For each category: what it does, verified examples, strengths, limitations, what this project can
realistically improve, and what we explicitly do **not** claim as novel.

### 3.1 Traditional ERM / GRC platforms

- **What they do:** risk registers, assessment workflows, control testing, policy lifecycle, compliance
  mapping, audit management, vendor risk, reporting.
- **Verified examples:**
  - **MetricStream** — cloud GRC/IRM software for enterprise-wide GRC programs across industries.
  - **ServiceNow IRM** — modules for Risk Management (register, assessments, scoring, mitigation),
    Policy and Compliance Management, Audit Management, plus Vendor/Third-Party and Operational Risk.
  - **Archer (formerly RSA Archer)** — enterprise GRC/IRM platform (enterprise & operational risk, IT &
    security risk, audit, compliance, third-party governance); **Archer Insight** adds quantitative risk
    measurement.
  - **LogicGate Risk Cloud** — no-code GRC workflow platform built on a graph data model, 40+ prebuilt
    applications.
- **Strengths:** process maturity, configurability, audit trails, enterprise adoption, compliance
  integration.
- **Limitations:** primarily qualitative (registers, scores, workflows); little automated quantitative
  analysis of a company's own financial statements; no scenario stress propagation through financial
  statements; no agent-driven analysis; enterprise pricing and deployment weight.
- **What we improve (realistic):** automated, quantitative, statement-level risk analysis and stress
  testing for a single business, with an auditable multi-agent workflow and explanations.
- **NOT claimed as novel:** risk registers, workflow automation, control/compliance mapping, audit
  trails (GRC platforms already do these well).

### 3.2 Financial data & analytics platforms

- **Verified examples:**
  - **Bloomberg Terminal** — real-time/historical market data, news, analytics, trading, messaging.
    Pricing is not published by Bloomberg; publicly reported ≈ **US$24,000–30,000 per user/year**
    (third-party reporting; **NOT VERIFIED as an official figure**) and ~325,000 subscribers (2022).
  - **FactSet Workstation** — integrated market data, analytics, and workflow tools for investment
    professionals.
  - **S&P Capital IQ Pro** — company/sector data platform (marketing cites 60M+ private and 109K+ public
    company records).
  - **Moody's** — credit ratings/research plus credit platforms (e.g., **CreditLens**, Lending Suite).
- **Strengths:** data breadth and quality, analytics depth, trust, breadth of covered entities.
- **Limitations:** high cost; closed ecosystems; built for analysts querying markets, not for
  autonomous, end-to-end risk analysis and stress testing of one (possibly private) business; limited
  SME/private-company financial coverage at affordable tiers.
- **What we improve:** an open, low-cost pipeline that turns one company's own financials into a
  multi-dimensional risk profile, scenario simulations, and stress tests.
- **NOT claimed as novel:** market-data provision, screening, ratio displays, charting.

### 3.3 Business intelligence dashboards

- **Verified examples:** Microsoft **Power BI** (“unified, scalable platform for self-service and
  enterprise BI”), **Tableau** (visual analytics), Google Cloud **Looker** (BI on a governed semantic
  model).
- **Strengths:** excellent visualization and distribution of *existing* metrics.
- **Limitations:** they render what upstream models compute; no risk reasoning, no simulation, no
  explanation of *why* risk changed, no agent workflow.
- **What we improve:** the upstream intelligence (deterministic risk engine + digital twin + agents);
  our frontend then presents it (a dashboard is our output layer, not our contribution).
- **NOT claimed as novel:** dashboarding/visualization itself.

### 3.4 Credit-risk systems and methodology

- **Verified examples:** Moody's CreditLens / Lending Suite (credit assessment workflow platforms);
  scoring methodologies across the industry.
- **Verified methodology foundations** (see §6 for formulas): **Altman Z-score** (Altman 1968 —
  multiple-discriminant bankruptcy model with published coefficients and zone cutoffs; private-firm Z′
  and non-manufacturer Z″ variants), **Merton model** (Merton 1974 — structural default model; KMV/EDF
  mapping builds on it).
- **Strengths:** statistically grounded, decades of validation literature, regulatory familiarity.
- **Limitations:** single-dimension (default-risk) focus; mostly periodic, static scoring; not a
  multi-risk view of a whole business; not interactive scenario tools for management.
- **What we improve:** embed credit-style analytics (e.g., Altman-Z as a reference signal) inside a
  broader multi-dimensional, scenario-aware risk profile.
- **NOT claimed as novel:** credit scoring methodology itself (we adapt published formulas).

### 3.5 AI/ML risk systems in industry

- **Verified (kept deliberately minimal):** vendors embed AI/ML in credit workflows (Moody's CreditLens)
  and market intelligence (S&P Capital IQ Pro is marketed with “AI-powered insights”). Major GRC vendors
  are adding generative-AI assistants (vendor marketing; specifics **NOT VERIFIED** and therefore not
  itemized).
- **Strengths:** production scale, proprietary data advantages.
- **Limitations:** closed/opaque; not reproducible research platforms; typically narrow (credit or
  market) rather than whole-business risk.
- **What we improve:** an open, reproducible, explainable architecture whose reasoning steps and
  calculations can be fully audited — suitable as a research contribution.
- **NOT claimed as novel:** “AI for finance” as a concept.

### 3.6 LLM-based business/financial analysis

- **Direct LLM chat (ChatGPT/Claude/Gemini/GLM used directly):** strong language and interpretation,
  but no deterministic grounding — arithmetic and consistency are unreliable; no audit trail. This is
  the core weakness our architecture is designed around (LLM interprets, deterministic engines compute).
- **BloombergGPT** (Wu et al. 2023, arXiv:2303.17564): 50-billion-parameter LLM trained on a 363B-token
  financial corpus mixed with 345B general tokens. Closed model.
- **FinGPT** (Yang, Liu & Wang 2023, arXiv:2306.06031; FinLLM Symposium @ IJCAI 2023): open-source,
  data-centric financial LLM framework (automated data curation + lightweight LoRA fine-tuning; demos
  in robo-advising and algorithmic trading).
- **FinRobot** (Yang et al. 2024, arXiv:2405.14767, AI4Finance Foundation): open-source AI **agent**
  platform for financial applications with a four-layer architecture (Financial AI Agents with
  Financial Chain-of-Thought; Financial LLM Algorithms; LLM/DataOps; Multi-source LLM Foundation
  Models). Focus: market analysis, trading, financial reporting tasks for analysts.
- **Limitations of this line of work (verified focus, not speculation):** emphasis on markets/trading/
  sentiment/earnings analysis; whole-business, multi-dimensional **risk + stress testing with
  deterministic propagation through financial statements** is not their core; numerical grounding and
  guardrails are left to the application.
- **What we improve:** deterministic-tool-grounded multi-agent risk analysis for a single business,
  with guardrails that verify every number an LLM emits, plus scenario stress simulation.
- **NOT claimed as novel:** LLM financial text analysis, sentiment analysis, fine-tuning methods.

### 3.7 Multi-agent LLM frameworks (general-purpose)

- **LangGraph** (LangChain; MIT license; `langgraph` v1.2.11 on PyPI as of 2026-08-11): low-level,
  graph-based orchestration for **stateful** agents/workflows — `StateGraph` (nodes = agents/functions,
  edges = control flow), state management, checkpointing, human-in-the-loop, multi-agent
  orchestration. **Selected as our orchestration backbone.**
- **AutoGen** (Wu et al. 2023, arXiv:2308.08155): conversation-driven multi-agent framework; v0.4
  rewrite (Jan 2025) moved to an asynchronous, event-driven actor model; community continuation as
  **AG2** (github.com/ag2ai/ag2).
- **CAMEL** (Li et al., NeurIPS 2023, arXiv:2303.17760): *“CAMEL: Communicative Agents for ‘Mind’
  Exploration of Large Language Model Society”* — role-playing communicative agents via inception
  prompting. (Caution: the often-quoted title “Communicative Agents for Software Development” belongs
  to **ChatDev**, Qian et al., arXiv:2307.07924, ACL 2024 — a different paper.)
- **MetaGPT** (Hong et al., arXiv:2308.00352, ICLR 2024 Oral): encodes human Standard Operating
  Procedures as role-based assembly-line workflows; structured intermediate outputs reduce cascading
  hallucination.
- **Survey** (Guo et al. 2024, arXiv:2402.01680, IJCAI 2024): taxonomy of LLM-based multi-agent systems
  and their open challenges — supports the framing that reliability/guardrails remain open problems.
- **Limitations:** general-purpose frameworks provide orchestration, not domain grounding; none ship a
  business-risk deterministic engine, stress-test methodology, or guardrail-verified numerical output.
- **What we improve:** a domain-specific instantiation: supervisor–specialist graph over deterministic
  financial tools with permissioned tool access and output verification.
- **NOT claimed as novel:** multi-agent orchestration itself (we build on LangGraph).

### 3.8 Quantitative / simulation approaches (traditional)

- **Stress testing practice:** see §5. **Scenario analysis** and **sensitivity analysis** are standard
  risk-management techniques; **Monte Carlo simulation** is standard for distributional risk.
- **What we adopt:** deterministic scenario propagation (baseline vs stressed trajectories), sensitivity
  analysis, threshold-breach monitoring. Monte Carlo variants are **future scope**.
- **NOT claimed as novel:** scenario analysis and stress testing as techniques (we apply them with a
  digital-twin propagation model and agent orchestration).

---

## 4. Academic and open-source literature (verified)

### 4.1 Multi-agent orchestration

| Work | Citation (verified) | Relevance to this project |
|---|---|---|
| LangGraph | LangChain; MIT; PyPI `langgraph` v1.2.11 (2026-08-11) | Chosen backbone: `StateGraph`, state management, checkpointing, human-in-the-loop |
| AutoGen | Wu et al. 2023, arXiv:2308.08155; v0.4 event-driven rewrite; AG2 fork | Canonical conversational multi-agent design; alternative considered |
| CAMEL | Li et al., NeurIPS 2023, arXiv:2303.17760 | Role-based agent cooperation pattern |
| MetaGPT | Hong et al., ICLR 2024 (Oral), arXiv:2308.00352 | SOP/role decomposition; structured intermediate outputs reduce cascading hallucination — informs our specialist-agent contracts |
| Multi-agent LLM survey | Guo et al., IJCAI 2024, arXiv:2402.01680 | Framing: progress taxonomy + open challenges (reliability) |

### 4.2 Financial AI agents / finance LLMs

| Work | Citation (verified) | Relevance |
|---|---|---|
| BloombergGPT | Wu et al. 2023, arXiv:2303.17564 (50B params; 363B financial + 345B general tokens) | Closed domain-tuned LLM — reference point; not reproducible |
| FinGPT | Yang, Liu & Wang 2023, arXiv:2306.06031 | Open financial LLM toolchain; data-centric fine-tuning |
| FinRobot | Yang et al. 2024, arXiv:2405.14767 | Closest open architecture: 4-layer agent platform for financial apps; market/analysis focus — our differentiation is whole-business risk + deterministic stress testing + guardrails |

### 4.3 Explainability (XAI)

| Work | Citation (verified) | Relevance |
|---|---|---|
| SHAP | Lundberg & Lee, NeurIPS 2017, arXiv:1705.07874 | Unified Shapley-value feature attribution for model outputs |
| TreeSHAP | Lundberg et al., Nature Machine Intelligence 2(1):56–67, 2020, DOI 10.1038/s42256-019-0138-9 | Polynomial-time exact SHAP for tree ensembles — used for the anomaly model |
| LIME | Ribeiro, Singh & Guestrin, KDD 2016, arXiv:1602.04938 | Model-agnostic local surrogates (comparison/baseline explainer) |
| Permutation importance | Breiman, “Random Forests”, Machine Learning 45(1):5–32, 2001, DOI 10.1023/A:1010933404324 | Original permutation-based variable importance — cheap baseline attribution |
| Counterfactual explanations | Wachter, Mittelstadt & Russell, arXiv:1711.00399; Harvard Journal of Law & Technology vol. 31 (2018 print; 2017 preprint) | “Smallest change to the world to obtain a desirable outcome” — conceptual basis for scenario-based counterfactuals |

### 4.4 Anomaly detection, digital twins, observability

| Work | Citation (verified) | Relevance |
|---|---|---|
| Isolation Forest | Liu, Ting & Zhou, ICDM 2008, pp. 413–422 | Chosen anomaly detector; ships as `sklearn.ensemble.IsolationForest` |
| Digital twin survey | Tao, Zhang, Liu & Nee, “Digital Twin in Industry: State-of-the-Art”, IEEE Trans. Industrial Informatics 15(4):2405–2415, 2019 | Canonical DT framing (virtual counterpart updated via data exchange) — we build a *financial-layer* business digital twin |
| SDV (Synthetic Data Vault) | DataCebo; github.com/sdv-dev/SDV | Synthetic tabular data generation. **License is Business Source License (BSL), not MIT** — optional tool only; our primary synthetic generator is custom in-repo code |
| Langfuse | github.com/langfuse/langfuse; langfuse.com/docs | Open-source LLM observability (traces, prompts, evaluations); **MIT except `ee/` folders**; self-hostable (Docker/K8s; ClickHouse-backed) — optional exporter behind our own trace store |

---

## 5. Stress-testing approaches

**Regulatory practice (verified):**

- **Basel Committee on Banking Supervision, “Stress testing principles”** (published 17 October 2018,
  BIS d450; replaces the 2009 principles): principles covering objectives, governance, policies,
  processes, methodology, resources, and documentation, with considerations for both banks and
  supervisors. Stress testing is described as “a critical element of risk management for banks and a
  core tool for banking supervisors”. (The commonly cited count of “17 principles” is secondary-sourced
  only — **NOT VERIFIED from the BIS document itself** in this session.)
- **U.S. Federal Reserve DFAST / CCAR:** **DFAST** (Dodd-Frank Act Stress Test) is a forward-looking
  quantitative evaluation of bank capital under hypothetical recession scenarios, conducted annually
  with a minimum of two scenarios; since 2020 its results set the **stress capital buffer (SCB)**.
  **CCAR** was the annual capital-planning review (run 2011–2021; qualitative element moved to
  confidential supervision in 2019, quantitative element replaced by SCB in 2020). The **2025 severely
  adverse scenario** illustrates the design pattern: a severe global recession with unemployment rising
  ~5.9 percentage points to a 10% peak, ~33% house-price decline, ~30% commercial-real-estate price
  decline, and a 50% equity-price decline (2025 scenario publication; trading-book firms additionally
  receive a global market shock and counterparty default component).
- **Reverse stress testing** (start from failure, search for the scenario causing it) is part of
  supervisory practice — **future scope** for this project.

**Methodological takeaways we adopt:**

1. **Severe-but-plausible, multi-factor scenarios** with an explicit horizon (regulators publish
   parameterized scenario tables — our preset scenario library mirrors this pattern at business scale).
2. **Baseline vs stressed trajectory comparison** on defined metrics with **threshold breaches**
   (regulators watch capital ratios; we watch business KPIs: cash runway, DSCR, interest coverage).
3. **Sensitivity analysis** (single-factor sweeps) alongside full scenarios.
4. **Documented, reviewable methodology** — every scenario parameter, threshold, and weight is explicit
   and configurable.

**What is deliberately different for a non-bank business:** propagation happens through the firm's own
income statement / balance sheet / cash flow (via the business digital twin, §6 of the specification),
not through regulatory capital models.

---

## 6. Quantitative foundations (formulas the risk engine will implement)

These are standard, textbook/published formulations. The original academic PDFs for Altman (1968) and
Merton (1974) are paywalled; coefficients/formulations below were verified through multiple consistent
secondary sources (Investopedia, Wall Street Prep, academic/technical write-ups) and will be
re-validated against hand-computed fixtures during implementation (Phase 4).

### 6.1 Financial ratios (definitions; implemented from definitions)

- **Liquidity:** Current Ratio = Current Assets / Current Liabilities; Quick Ratio = (Current Assets −
  Inventory) / Current Liabilities; Cash Ratio = Cash & Equivalents / Current Liabilities.
- **Leverage:** Debt-to-Equity = Total Debt / Total Equity; Debt-to-EBITDA = Total Debt / EBITDA.
- **Coverage:** Interest Coverage = EBIT / Interest Expense; DSCR = EBITDA / (Interest + Current
  Portion of Long-Term Debt).
- **Profitability:** Gross / Operating / Net Margin (Gross Profit, EBIT, Net Income ÷ Revenue); ROA =
  Net Income / Total Assets; ROE = Net Income / Total Equity.
- **Efficiency (working capital):** DSO = Receivables/Revenue × 365; DIO = Inventory/COGS × 365;
  DPO = Payables/COGS × 365; Cash Conversion Cycle = DSO + DIO − DPO.
- **Liquidity runway:** Cash Runway (months) = Cash & Equivalents / average monthly net cash burn
  (burn = max(0, −operating cash flow trend)); Short-Term Obligation Coverage = Cash & Equivalents +
  undrawn committed facilities (if known) / Current Liabilities.

### 6.2 Market risk (standard definitions)

- Annualized volatility: σ_ann = stdev(daily log returns, sample) × √252.
- Beta: β = Cov(r_asset, r_market) / Var(r_market) over a rolling window vs a configurable index.
- Historical VaR at level α: VaR_α = −Quantile(r, 1−α) (reported as a positive loss).
- Expected Shortfall: ES_α = E[loss | loss ≥ VaR_α].

### 6.3 Concentration (standard definitions)

- Herfindahl–Hirschman Index over shares sᵢ: HHI = Σ sᵢ² (reported on 0–1 scale; ×10,000 = points).
- Top-k concentration: CR_k = Σ of k largest shares (customers, suppliers, products, geographies).

### 6.4 Reference models (verified; used as reference signals, not core engines)

- **Altman Z-score (1968, public manufacturing firms):**
  Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5 where
  X1 = Working Capital/Total Assets, X2 = Retained Earnings/Total Assets, X3 = EBIT/Total Assets,
  X4 = Market Value of Equity/Total Liabilities, X5 = Sales/Total Assets.
  Zones (1968 calibration): **Z > 2.99 safe; 1.81–2.99 grey; Z < 1.81 distress.**
  Variants (different coefficients — never mix): Z′ private firms (0.717/0.847/3.107/0.420/0.998,
  cutoffs 2.675/1.23, X4 = book equity); Z″ non-manufacturers/emerging markets 4-ratio model
  (6.56/3.26/6.72/1.05, cutoffs 2.6/1.1).
- **Merton model (1974):** equity as a call option on firm assets V with debt face value D.
  d1 = [ln(V/D) + (r + σ²/2)T] / (σ√T); d2 = d1 − σ√T = [ln(V/D) + (r − σ²/2)T] / (σ√T);
  risk-neutral distance-to-default DD = d2 and PD = Φ(−d2); the physical-measure variant replaces r
  with expected asset return μ. KMV/Moody's EDF maps DD to empirical default frequencies. Limitations:
  V and σ are unobservable (backed out from equity), GBM asset dynamics, single zero-coupon debt
  assumption. **Positioned as optional reference methodology, not core engine.**

---

## 7. Data sources and access (source vs access method — verified)

Per project rules, each entry separates the **SOURCE** (who publishes the data) from the **ACCESS
METHOD** (official API / official download / unofficial library), with verified availability, access
method, licensing/terms, historical coverage, and limitations.

### 7.1 SEC EDGAR (company financial statements — optional real-data import)

- **SOURCE:** U.S. Securities and Exchange Commission, EDGAR database.
- **ACCESS:** Official, **keyless** JSON APIs on `data.sec.gov`: `/api/xbrl/companyfacts/CIK##########.json`
  (all XBRL facts per filer), `/companyconcept/`, `/frames/`; nightly bulk ZIP
  `sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` (documented as the most efficient means to
  fetch large amounts). Official documentation states these APIs “do not require any authentication or
  API keys”.
- **AUTH:** none; a declared User-Agent header is required (`Sample Company Name AdminContact@domain`).
- **RATE LIMIT (exact official wording):** “Current max request rate: 10 requests/second.”
- **TERMS:** free for anyone to access and download; U.S. government works are not copyrighted
  (17 U.S.C. §105) — effectively public domain; SEC reserves the right to limit request rates.
- **COVERAGE:** U.S.-registered filers only; XBRL-tagged facts from 10-Q/10-K/8-K/20-F/40-F/6-K;
  standard taxonomies (us-gaap, ifrs-full, dei, srt); structured XBRL coverage effectively **2009+**
  (phased mandate 2009–2011, Release 33-8924).
- **LIMITS:** no CORS support; ~1-minute processing delay on XBRL APIs; raw us-gaap concept tags need
  mapping to our internal schema; no SEC technical support for scripted access.

### 7.2 FRED (macroeconomic time series — primary macro source)

- **SOURCE:** Federal Reserve Bank of St. Louis (aggregates BLS, BEA, Board of Governors, EIA, IMF,
  OECD, etc.).
- **ACCESS:** official REST API `https://api.stlouisfed.org/fred/` (API key required); a keyless CSV
  graph endpoint `fred.stlouisfed.org/graph/fredgraph.csv` also exists.
- **AUTH:** free API key via a FRED account; “All web service requests require an API key”; developers
  should use a distinct key per application.
- **TERMS:** FRED legal notices state the series are under copyright but may be used **with proper
  attribution** (“provided you have not engaged in any prohibited uses…”); attribution required for
  display/redistribution; U.S.-government-source series are public domain at origin.
- **RATE LIMITS:** no numeric limit found on official pages this session (third-party reports of
  ~120 requests/min are **NOT VERIFIED**).
- **SERIES IDs verified live (2026-09-21):** `FEDFUNDS` (Federal Funds Effective Rate; 3.63% Aug 2026),
  `CPIAUCSL` (CPI-U All Items; 334.131 Aug 2026), `GDPC1` (Real GDP, Q2 2026), `UNRATE` (Unemployment
  Rate; 4.1% Aug 2026), `DEXINUS` (**Indian Rupees to U.S. Dollar** spot rate — direction is INR per
  USD; 95.55 on 2026-09-11). **`DCOILWTTI` (WTI crude) returned 404 on repeated attempts this session —
  existence NOT VERIFIED here**; commodity prices may instead come from Stooq commodity symbols
  (verify both in Phase 3).
- **LIMITS:** H.10 FX series are noon buying rates, not market closes; some third-party series carry
  extra licensing strings.

### 7.3 Stooq (market data — candidate primary market source)

- **SOURCE:** Stooq (stooq.com), a Polish financial-data site.
- **ACCESS:** CSV downloads via web URL patterns (`q/d/l/?s=…&i=d` style); **no official API
  documentation**; third-party documentation confirms daily OHLCV CSV for stocks/indices/FX/commodities.
- **AUTH:** none / optional free account.
- **TERMS (stated explicitly per project rules):** the site footer states verbatim: **“This data is
  intended solely for personal use. Any commercial use is prohibited.”** A “Terms of service” footer
  link exists but its full text could not be retrieved this session (candidate URLs returned 404).
  **There is no published data license (no CC/public-domain statement); the status of automated/
  programmatic download is UNCLEAR.** Data is credited on-site to third-party vendors (Infront,
  Barchart, CoinAPI, 1Forge), implying underlying vendor rights.
- **COVERAGE:** daily OHLCV for stocks (US/EU/Asia incl. India), indices, FX, commodities, some
  bonds/macro; many US series reach back to the 1990s (exact per-symbol depth **NOT VERIFIED**).
- **LIMITS:** no SLA, no accuracy guarantee, no documented rate limits, variable history depth.
- **Project verdict:** usable for a **private, educational prototype** with local caching, throttling,
  and attribution — not for redistribution. This caveat is recorded in the specification and docs.

### 7.4 Yahoo Finance (source) vs `yfinance` (access library)

- **SOURCE:** Yahoo Finance (Yahoo LLC) — **no official free historical-data API for public use**.
- **ACCESS LIBRARY:** `yfinance` — unofficial open-source library by Ran Aroussi, **Apache-2.0
  licensed**. README states: “not affiliated, endorsed, or vetted by Yahoo, Inc.”; “uses Yahoo's
  publicly available APIs, and is intended for research and educational purposes”; “the Yahoo! finance
  API is intended for personal use only”; users must refer to Yahoo's terms for rights to the data.
- **YAHOO ToS (verbatim clause, terms updated 2025-05-06):** users “may not access or collect data…
  using any automated means… for any purpose without our express, prior permission.”
- **KNOWN ISSUES 2024–2026:** active rate limiting (429 responses, including “Failed to get crumb,
  status 429” reported Dec 2025); the library now relies on browser-impersonation (`curl_cffi`) and
  continues to adapt (releases 1.5.2 → 1.7.0 through 2026); no SLA; breakage risk.
- **Project verdict:** acceptable as a **fallback** market-data source for a private educational
  prototype (cached, throttled, no redistribution); primary source is Stooq, with both clearly flagged
  for terms risk. For any public deployment, a licensed data vendor would be required.

### 7.5 World Bank Open Data (annual macro context)

- **SOURCE:** World Bank (World Development Indicators and other datasets).
- **ACCESS:** official API v2, `https://api.worldbank.org/v2/` (JSON via `format=json`); examples:
  `/country/all/indicator/NY.GDP.MKTP.CD?date=2006`.
- **AUTH:** documented examples require no key.
- **TERMS:** **CC BY 4.0** is the default license for World Bank open data (attribution required; must
  not imply World Bank endorsement).
- **INDICATORS verified via API metadata (2026-09-21):** `NY.GDP.MKTP.KD.ZG` (GDP growth, annual %),
  `FP.CPI.TOTL.ZG` (inflation, consumer prices, annual %).
- **LIMITS (documented):** max 60 indicators per URL; max 4,000-character URL; no sorting; no
  published rate limit on the reviewed page. Annual frequency only (monthly/quarterly context must
  come from FRED).

### 7.6 Synthetic data (primary company-level source)

- **Rationale:** company-level financials for private businesses are not freely available; stress
  testing requires controllable, reproducible inputs; licensing risk must be zero for the core path.
- **Approach:** a **custom deterministic synthetic-company generator** written in-repo (seeded,
  parameterized by sector/size/health, emits full statements + concentration buckets + optional
  injected anomalies for ML evaluation). This gives full control, testability, and reproducibility.
- **Optional library:** **SDV** (DataCebo) can generate synthetic tabular/relational/sequential data,
  but its GitHub README states a **Business Source License (BSL), not MIT** — use only after checking
  BSL terms; treated as optional, not core.

### 7.7 Data strategy decision (carried into the specification)

**Hybrid:** synthetic company core (deterministic, seeded) + real macro series from FRED (attribution)
and World Bank (CC BY 4.0) + market series from Stooq CSV (primary, cached) with yfinance fallback
(terms-flagged) + optional SEC EDGAR import of real listed-company statements (public domain, 10 req/s,
keyless). All downloads cached locally with source, license tag, fetch timestamp, and attribution
record; no redistribution of any third-party data.

---

## 8. LLM provider landscape (reasoning layer)

- **Z.ai / Zhipu AI (“BigModel” platform)** documents an **OpenAI-compatible** interface — clients
  change only `base_url` + key: domestic `https://open.bigmodel.cn/api/paas/v4`, international
  `https://api.z.ai/api/paas/v4` (Bearer key; the platform documents support for both OpenAI and
  Anthropic protocols).
- **GLM-5.3-Flash is verified as a real current model:** announced by Z.ai on 2026-08-26 (“Frontier
  Intelligence, Flash Cost”); open weights published as `zai-org/GLM-5.3-Flash` on Hugging Face
  (2026-08-27; natively multimodal MoE, ~320B total / ~18B active parameters, ~1M-token context);
  listed on docs.z.ai and OpenRouter (`z-ai/glm-5.3-flash`; listed promo pricing ≈ $0.075/M input,
  $0.25/M output — **third-party listing figures; official Z.ai price page NOT VERIFIED this session**).
- **Design consequence (locked decision):** the reasoning layer sits behind a **provider-agnostic LLM
  abstraction** (a small interface + adapters returning LangChain chat models). GLM-5.3-Flash is the
  **temporary development default** via the OpenAI-compatible adapter; OpenAI, Gemini, Anthropic, and
  local (Ollama) adapters are drop-in replacements. No agent or engine code may depend on the provider.
  Deterministic calculations never touch any LLM.

---

## 9. Synthesized research gap

Grounded strictly in the verified findings above (§3–§5), the specific gap this project addresses:

- **G1 — Domain mismatch of financial agent research.** Open financial agent platforms (FinRobot,
  FinGPT) target markets, trading, and analyst reporting tasks; whole-business, multi-dimensional risk
  analysis with **deterministic stress propagation through the firm's own financials** is not their
  focus (§3.6).
- **G2 — Qualitative GRC vs quantitative simulation.** Commercial ERM/GRC platforms excel at registers,
  workflows, and compliance but do not quantify and propagate shocks through a company's financial
  statements (§3.1); financial analytics terminals provide data and ratios but not autonomous,
  auditable analysis at accessible cost (§3.2).
- **G3 — Regulatory stress testing is bank-centric.** BCBS/DFAST/CCAR methodology is mature but built
  for bank capital; an analogous, explainable scenario-stress pipeline for a general business (SME or
  division) using its income statement/cash flow does not have an open reference implementation (§5).
- **G4 — Ungrounded LLM numerics.** LLMs cannot be trusted with arithmetic; the survey literature
  frames multi-agent reliability as an open challenge (§3.7), and no widely-adopted open system
  couples agents with **machine-checkable verification that every emitted number matches a
  deterministic engine** (§3.6, §3.7).
- **G5 — Fragmented explainability.** XAI research provides per-model attribution (SHAP/LIME/
  permutation/counterfactuals), but risk decision-support needs *layered* explanation: deterministic
  contributions, model attributions, and scenario counterfactuals, clearly separated from narrative
  (§4.3).

**Contribution (honest scope):** an integrated, open, reproducible architecture — supervisor–specialist
multi-agent orchestration (LangGraph) over a deterministic quantitative risk engine, a financial-layer
business digital twin, bounded scenario generation, guardrails with numeric-verification, and layered
explainability — evaluated with ablations against the four baselines defined in the specification. We
do **not** claim new financial theory, new ML methods, or regulatory-grade compliance.

---

## 10. References

All URLs accessed 2026-09-21.

1. ISO — ISO 31000:2018, Risk management — Guidelines. https://www.iso.org/standard/65694.html
   (iso.org catalog returned HTTP 403 to automated fetch; content verified via ISO search index and
   full-text secondary sources: finance.gov.au; metricstream.com/learn/iso-31000-framework.php)
2. COSO — Enterprise Risk Management — Integrating with Strategy and Performance (2017).
   https://www.coso.org/guidance-erm ; NC State ERM Initiative:
   https://erm.ncsu.edu/resource-center/cosos-erm-framework/
3. MetricStream. https://www.metricstream.com/
4. ServiceNow Integrated Risk Management. https://www.servicenow.com/products/integrated-risk-management.html
5. Archer (formerly RSA Archer). https://www.archerirm.com
6. LogicGate Risk Cloud. https://www.logicgate.com/resources/brochures/risk-cloud-platform-overview ; https://www.logicgate.ai
7. Bloomberg Terminal (pricing is third-party reported). https://en.wikipedia.org/wiki/Bloomberg_Terminal
8. FactSet. https://www.factset.com
9. S&P Capital IQ Pro. https://www.spglobal.com/market-intelligence/en/solutions/products/sp-capital-iq-pro
10. Moody's (CreditLens, Lending Suite). https://www.moodys.com
11. BCBS, Stress testing principles (17 Oct 2018), BIS d450. https://www.bis.org/bcbs/publ/d450.htm ;
    https://www.bis.org/press/p181017.htm
12. Federal Reserve — DFAST. https://www.federalreserve.gov/supervisionreg/dfa-stress-tests.htm ;
    Stress tests & capital planning: https://www.federalreserve.gov/supervisionreg/stress-tests-capital-planning.htm ;
    2025 scenarios press release (Feb 5, 2025): https://www.federalreserve.gov/newsevents/pressreleases/bcreg20250205a.htm
13. Microsoft Power BI. https://www.microsoft.com/en-us/power-platform/products/power-bi
14. Tableau Desktop. https://www.tableau.com/products/desktop
15. Google Cloud Looker. https://cloud.google.com/looker
16. LangGraph. https://pypi.org/project/langgraph/ ; https://github.com/langchain-ai/langgraph ;
    https://langchain-ai.github.io/langgraph/
17. AutoGen. https://arxiv.org/abs/2308.08155 ; v0.4 rewrite:
    https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness ;
    AG2: https://github.com/ag2ai/ag2
18. CAMEL. https://arxiv.org/abs/2303.17760 ; ChatDev (distinct paper): https://arxiv.org/abs/2307.07924
19. MetaGPT. https://arxiv.org/abs/2308.00352
20. Guo et al., LLM-based Multi-Agents survey. https://arxiv.org/abs/2402.01680 ; https://www.ijcai.org
21. FinRobot. https://arxiv.org/abs/2405.14767 ; https://github.com/AI4Finance-Foundation/FinRobot
22. FinGPT. https://arxiv.org/abs/2306.06031
23. BloombergGPT. https://arxiv.org/abs/2303.17564
24. SHAP. https://arxiv.org/abs/1705.07874 ; TreeSHAP:
    https://www.nature.com/articles/s42256-019-0138-9 (DOI 10.1038/s42256-019-0138-9)
25. LIME. https://arxiv.org/abs/1602.04938 ; https://dl.acm.org/doi/10.1145/2939672.2939778
26. Breiman, Random Forests (permutation importance). https://link.springer.com/article/10.1023/A:1010933404324
27. Wachter et al., Counterfactual Explanations. https://arxiv.org/abs/1711.00399
28. Isolation Forest (ICDM 2008); scikit-learn implementation:
    https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
29. Tao et al., Digital Twin in Industry: State-of-the-Art, IEEE TII 15(4), 2019.
    https://ieeexplore.ieee.org (IEEE Xplore record)
30. SDV — Synthetic Data Vault (DataCebo; BSL license). https://github.com/sdv-dev/SDV ; https://docs.sdv.dev/sdv
31. Langfuse (MIT except `ee/`). https://github.com/langfuse/langfuse ; https://langfuse.com/docs
32. SEC EDGAR — accessing data & fair-access policy. https://www.sec.gov/os/accessing-edgar-data ;
    XBRL API documentation: https://www.sec.gov/edgar/sec-api-documentation
33. FRED — API key. https://fred.stlouisfed.org/docs/api/api_key.html ; legal notices:
    https://fred.stlouisfed.org/legal ; series verified: https://fred.stlouisfed.org/series/FEDFUNDS ,
    /series/CPIAUCSL , /series/GDPC1 , /series/UNRATE , /series/DEXINUS
34. Stooq. https://stooq.com (footer terms sentence quoted verbatim in §7.3; full ToS not retrievable);
    third-party description: https://www.quantstart.com/articles/An-Introduction-to-Stooq-Pricing-Data/
35. yfinance (Apache-2.0, unofficial). https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md ;
    releases: https://github.com/ranaroussi/yfinance/releases ; Yahoo Terms of Use:
    https://guce.yahoo.com/terms?locale=en-US
36. World Bank Open Data — API. https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-structure ;
    licensing: https://datacatalog.worldbank.org/search/about ; https://data.worldbank.org/summary-of-terms-of-use
37. Z.ai / BigModel GLM API (OpenAI-compatible). https://docs.bigmodel.cn ; https://docs.z.ai/guides/llm/glm-5.3 ;
    https://z.ai/blog/glm-5 ; GLM-5.3-Flash weights: https://huggingface.co/zai-org/GLM-5.3-Flash ;
    OpenRouter listing: https://openrouter.ai/z-ai/glm-5.3-flash
38. Altman (1968) coefficients/zones via secondary sources:
    https://www.investopedia.com/terms/a/altman.asp ; https://www.wallstreetprep.com/knowledge/altman-z-score/
39. Merton (1974) formulation via secondary sources:
    https://mingze-gao.com/posts/merton-distance-to-default/ ; https://metricgate.com/calculators/merton-model/

### Verified-live observations (2026-09-21)

- FRED: FEDFUNDS 3.63% (Aug 2026); CPIAUCSL 334.131 (Aug 2026); GDPC1 24,269.613 bn chained 2017 $
  (Q2 2026, SAAR); UNRATE 4.1% (Aug 2026); DEXINUS 95.55 INR per USD (2026-09-11).
- LangGraph on PyPI: v1.2.11 (2026-08-11), MIT license.

### Outstanding items to re-verify in later phases

- FRED `DCOILWTTI` (WTI) series existence, or choose a Stooq commodity symbol (Phase 3).
- Stooq full Terms of Service text and per-symbol historical depth (Phase 3).
- FRED numeric rate limit (no official figure found; Phase 3 throttle conservatively regardless).
- Official Z.ai pricing page for GLM-5.3-Flash (Phase 2, when the API key is configured).
- Bloomberg Terminal official pricing (never published; third-party figures only — do not cite as fact).
- BCBS d450 principle count (commonly “17”; not confirmed from the BIS document itself — cite the
  document by title/date without the count).

