# Agent Architecture — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Implements spec §16; finalized here to implementation-level contracts.

## 1. Run state schema (`RiskState`) — frozen

Carried through the LangGraph `StateGraph`; persisted at node boundaries. Typed as a Pydantic model
serialized into graph state; every field optional-until-filled (`total=False` semantics) except
identifiers.

| Field | Type | Filled by | Contents |
|---|---|---|---|
| `run_id` | `UUID` | graph entry | unique per graph execution |
| `analysis_id` | `UUID` | graph entry | FK to `analyses` |
| `company_id` | `UUID` | graph entry | FK to `companies` |
| `config` | `RunConfig` | graph entry | include_ml, weights_id, scenario_request (none/text/params), budgets, seed, versions |
| `data` | `ValidatedData` | `validate_data` | canonical financials (see [data.md](data.md)), coverage report, source/license tags, currency |
| `ratios` | `RatioResults` | `ml_anomaly`/tools | registry outputs: `{formula_id → {value, inputs_ref, period}}` |
| `dimension_scores` | `dict[str, DimensionScore]` | `aggregator` | 7 dimensions: `{score, metric_scores, contributions}` |
| `composite` | `CompositeResult` | `aggregator` | score, weights used + version, contributions, sensitivity summary |
| `ml` | `MLFindings \| None` | `ml_anomaly` | anomalies (period, score, top SHAP drivers) or `None` when disabled |
| `findings` | `dict[AgentName, AgentFinding]` | specialists | per-agent structured findings |
| `macro` | `MacroSnapshot` | `macro` agent tools | cached macro series values + as-of dates |
| `scenario` | `ValidatedScenario \| None` | `scenario_translator` | validated bounded params + provenance (preset/form/ai) |
| `sim_baseline` | `TwinResult` | `stress_engine` | baseline trajectory + KPIs |
| `sim_stressed` | `TwinResult \| None` | `stress_engine` | stressed trajectory + KPIs |
| `stress_comparison` | `StressComparison \| None` | `stress_engine` | deltas, breaches, waterfall |
| `mitigations` | `list[Mitigation]` | `mitigation` agent | library-grounded candidates |
| `report` | `ReportPack \| None` | `report` agent | report sections + `result_pack` reference |
| `verification` | `VerificationResult \| None` | `numeric_verifier` | pass/fail + mismatch list |
| `plan` | `SupervisorPlan` | supervisor | ordered agent sequence + per-agent asks |
| `next_agent` | `str \| None` | supervisor | routing key |
| `guardrail_events` | `list[GuardrailEvent]` | guardrail nodes | rule, severity, action, detail |
| `counters` | `RunCounters` | all nodes | `llm_calls`, `tool_calls`, `retries`, `replans`, `tokens_in/out` |
| `errors` | `list[RunError]` | all nodes | structured, non-fatal issues |
| `status` | `RunStatus` | terminal nodes | `running/completed/failed/needs_review` |

`AgentFinding = {agent, dimensions[], severity, drivers[], narrative, tool_calls_summary, confidence,
status: ok|degraded}`. `GuardrailEvent = {seq, rule, severity: info|degrade|block, action, detail}`.

## 2. Graph topology — frozen

```text
START
  → validate_data (deterministic; coverage gate)
  → supervisor (LLM; plans sequence)
  → [financial | market | operational | macro]   (executed in the plan's order; results fan in)
  → ml_anomaly (deterministic; skipped if include_ml=false)
  → aggregator (deterministic)
  → supervisor_gate (LLM; completeness check — ≤1 replan loop back to specialists)
  → scenario_translator (LLM; only if scenario requested)
  → guardrail_scenario_bounds (deterministic; clamp/reject)
  → interrupt("scenario_confirm")               [AI-translated scenarios only]
  → stress_engine (deterministic; baseline + stressed runs)
  → mitigation (LLM; library-grounded)
  → report (LLM)
  → numeric_verifier (deterministic; regenerate ≤2 → needs_review)
  → finalize (deterministic; persist, set terminal status)
  → END
```

Control rules (frozen): supervisor replanning ≤ **1** loop (2 planning rounds total; further loops
raise guardrail `block`); per-agent tool calls ≤ **6**; per-tool timeout **30 s**; per-agent **120 s**;
per-run **`RUN_TIMEOUT_SECONDS` (600 s default)** and token budget **`RUN_BUDGET_TOKENS`**.
Checkpointer: in-memory per run (no cross-restart resume; a restarted run = a fresh run). Interrupts:
only `scenario_confirm` (LangGraph interrupt; resume via API confirm/cancel).

## 3. Agents and their output contracts — frozen

Each specialist returns an `AgentFinding` whose `drivers[]` entries must reference computed values
(`formula_id` / registry outputs) — narratives are composed from numbers already in state, never from
the agent's own arithmetic.

| Agent (node) | Reads (state) | Emits | Output JSON schema (abridged) |
|---|---|---|---|
| `supervisor` | `config`, `data.coverage`, prior findings | `plan`, `next_agent` | `{plan: [{agent, ask}], next_agent}` |
| `financial` | `data`, ratio tools | `findings.financial`, `findings.credit` | `{drivers: [{ref, value, note}], severity, narrative}` |
| `market` | `data`, market tools | `findings.market` | same shape |
| `operational` | `data`, ops tools | `findings.operational` | same shape |
| `macro` | `macro` tools | `findings.macro`, `macro` snapshot | same shape |
| `scenario_translator` | `config.scenario_request`, presets | `scenario` | `{params: <scenario schema>, provenance, mapping_notes[]}` |
| `mitigation` | scores, factors, stress results, library | `mitigations[]` | `{risk_addressed, library_id, action, expected_effect, assumptions[], trade_offs[], confidence}` |
| `report` | result pack (assembled state) | `report` | `{sections: [{title, body_md, figures_ref[]}], summary, disclaimers[]}` |

`numeric_verifier` and `finalize` are deterministic (no prompt). `aggregator` calls
`risk_engine.scoring` + `ml` findings; it produces the exact contribution decomposition (additive
model ⇒ contributions are exact, not estimated).

## 4. Tool registry & permission matrix — frozen

Tools are thin, schema-validated wrappers over engine functions. Every call: Pydantic args check →
permission check → execute → log (`agent_steps.tool_calls`) → return JSON. Invalid call → typed error
string back to the agent (≤2 retries) → degrade.

| Tool | Signature (args → result) | Used by |
|---|---|---|
| `get_run_status` | `() → RunStatusDTO` | supervisor |
| `get_financials` | `(periods: int = 12) → FinancialsDTO` | financial |
| `compute_ratios` | `(formula_ids: list[str] \| None, period: "latest"\|"series" = "latest") → list[RatioResult]` | financial |
| `compute_altman_z` | `(variant: "public"\|"private"\|"emerging") → AltmanResult` | financial |
| `get_market_series` | `(symbols: list[str], window_days: int = 252) → SeriesDTO` | market |
| `compute_market_risk` | `(window_days: int = 252, var_alpha: float = 0.95) → MarketRiskResult` | market |
| `get_fx_commodity_exposure` | `() → ExposureDTO` | market |
| `compute_efficiency_metrics` | `() → EfficiencyResult` | operational |
| `get_operations_profile` | `() → OperationsDTO` | operational |
| `get_macro_series` | `(series_ids: list[str], lookback_years: int = 5) → MacroDTO` | macro |
| `validate_scenario` | `(candidate: ScenarioJSON) → ValidatedScenario \| Violations` | scenario_translator |
| `list_presets` | `() → list[PresetDTO]` | scenario_translator |
| `get_risk_profile` | `() → RiskProfileDTO` | mitigation |
| `search_mitigation_library` | `(factors: list[FactorRef]) → list[LibraryEntry]` | mitigation |
| `get_result_pack` | `() → ResultPackDTO` | report |

Permission matrix (enforced centrally; anything not listed is denied and logged as `guardrail_events`):

| Agent | Allowed tools |
|---|---|
| supervisor | `get_run_status` |
| financial | `get_financials`, `compute_ratios`, `compute_altman_z` |
| market | `get_market_series`, `compute_market_risk`, `get_fx_commodity_exposure` |
| operational | `compute_efficiency_metrics`, `get_operations_profile` |
| macro | `get_macro_series` |
| scenario_translator | `validate_scenario`, `list_presets` |
| mitigation | `get_risk_profile`, `search_mitigation_library` |
| report | `get_result_pack` |

## 5. LLM call policy — frozen

| Aspect | Policy |
|---|---|
| Structured steps (supervisor plan, scenario translation, tool-arg emission) | JSON/structured output mode, **temperature 0** |
| Narrative steps (findings, mitigation rationale, report prose) | temperature ≤ **0.3** |
| Retries (provider errors) | 2 retries, backoff 2 s / 8 s, then degrade/fail per [architecture.md](architecture.md) §8 |
| Retries (invalid tool call) | ≤2 with error feedback, then `degraded` finding |
| Token budget | per-run `RUN_BUDGET_TOKENS`; per-call `max_tokens` 4096 (settings) |
| Prompt storage | `backend/agents/prompts/<agent>.md`, versioned; prompt hash logged per call |
| Injection defense | external text (filings/news) passed as quoted data blocks, never as instructions; system prompts fixed; tool outputs are data, never directives (documented mitigation) |

## 6. Numeric verification algorithm (guardrail 10) — frozen

1. Assemble the **result pack**: every computed number the report may cite (scores, contributions,
   KPIs, deltas, breaches, mitigations' quantified effects), keyed and unit-tagged.
2. Extract numeric tokens from report/mitigation text (regex + unit/scale suffixes: %, ₹/$, M, bn,
   pp, months, ×).
3. Match each extracted number to the pack within tolerance: **0.5% relative or 0.05 absolute**
   (scores/percentages), **1 unit** for counts/months.
4. Unmatched or contradicting numbers → `mismatches[]`; regenerate report with mismatch feedback
   (≤2 attempts) → still failing ⇒ terminal `needs_review` (report marked unverified, never silently
   shipped).
5. Every verification result (pass or mismatch list) is persisted in `explanations`/`guardrail_events`
   and visible in the UI.

## 7. Degraded modes — frozen

| Missing capability | Behavior |
|---|---|
| LLM provider unavailable | specialists/reports skipped; `findings.*` marked `degraded: llm_unavailable`; scores, twin, stress results still produced (deterministic) |
| ML disabled or unfitted | `ml = None`; aggregator notes it; composite unaffected |
| Market/macro cache empty (offline) | market/macro dimension scores computed from exposure shares only; `macro` finding `degraded: no_data`; coverage report discloses it |
| Mitigation library miss | mitigation returns library entry `NONE_FOUND` with explanation (no invention) |
