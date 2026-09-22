# API Specification — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. REST under `/api/v1`, FastAPI (OpenAPI auto-docs at `/docs`).
Auth arrives in Phase 12; every endpoint below already reserves the header contract.

## 1. Conventions (frozen)

- **Versioning:** path-prefixed `/api/v1`. Breaking changes ⇒ `/api/v2` (v1 kept for the project's life).
- **Errors:** always the envelope below; `code` values are stable and documented.

```json
{ "error": { "code": "SCENARIO_OUT_OF_BOUNDS", "message": "human-readable", "details": { "...": "..." } } }
```

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | request/schema validation failure (Pydantic details in `details`) |
| `NOT_FOUND` | 404 | unknown resource |
| `DATA_COVERAGE_LOW` | 409 | required-concept coverage < 70% |
| `SCENARIO_OUT_OF_BOUNDS` | 422 | scenario rejected (beyond clamp tolerance) |
| `SCENARIO_PENDING_CONFIRM` | 409 | AI-translated scenario awaiting `/confirm` |
| `RUN_STATE_INVALID` | 409 | operation not valid for the run's current state |
| `GUARDRAIL_BLOCKED` | 422 | guardrail `block` severity (details name the rule) |
| `UNAUTHORIZED` / `FORBIDDEN` | 401 / 403 | Phase 12 |
| `RATE_LIMITED` | 429 | throttled (Phase 12) |
| `INTERNAL_ERROR` | 500 | unexpected (correlation id in details) |

- **IDs:** UUID strings. **Timestamps:** ISO-8601 UTC.
- **Pagination:** `?limit=` (default 50, max 200) + `?offset=`; responses carry `total`.
- **Auth (Phase 12):** `Authorization: Bearer <JWT>`; roles `analyst`, `admin` (admin manages weights
  defaults and users). All docs/examples carry the header from Phase 12.

## 2. Endpoints (frozen)

### Companies

`POST /api/v1/companies`
```json
// request — one of:
{ "origin": "synthetic", "generator": { "sector": "manufacturing", "size": "medium", "health": "stable",
  "currency": "INR", "periods": 24, "frequency": "monthly", "concentration": "moderate",
  "inject_anomalies": [], "seed": 1001 } }
{ "origin": "manual", "financials": [ { "period_end": "2026-06-30", "revenue": 0, "...": 0 } ] }
// response 201
{ "id": "uuid", "name": "string", "sector": "manufacturing", "currency": "INR",
  "data_origin": "synthetic", "coverage_report": { "required_pct": 100.0, "optional_pct": 92.0,
  "missing_required": [], "warnings": [] } }
```

`GET /api/v1/companies` → `{ "total": int, "items": [CompanySummary] }`
`GET /api/v1/companies/{id}` → company + periods list + latest coverage report.
`POST /api/v1/companies/{id}/edgar-import` *(Phase 3, feature-flagged)* `{ "cik": "0000320193" }` → 202 import job.

### Analyses

`POST /api/v1/companies/{id}/analyses`
```json
{ "include_ml": true, "weights_id": "uuid|null", "seed": 42,
  "scenario": { "mode": "none" }   // or {"mode":"text","text":"..."} | {"mode":"params","params":{...}} | {"mode":"preset","preset_id":"rate_shock"} }
// 202
{ "analysis_id": "uuid", "status": "pending", "scenario_confirmation_required": false }
```
`scenario_confirmation_required = true` iff mode `text` (AI-translated). Params/preset run directly (FD-3).

`GET /api/v1/analyses/{id}` → `{ "id", "company_id", "status": "pending|running|completed|failed|needs_review|cancelled", "composite_score": float|null, "severity": str|null, "engine_version", "registry_version", "graph_version", "started_at", "finished_at", "error": {...}|null }`

`GET /api/v1/analyses/{id}/risks`
→ `{ "dimensions": { "<name>": { "score", "severity", "metrics": [{ "formula_id", "value", "score", "band_source" }] } }, "composite": { "score", "weights_used", "weights_version", "contributions", "sensitivity": { "per_weight": [{ "dimension", "minus20", "plus20" }] } }, "factors": [RiskFactor] }`

`GET /api/v1/analyses/{id}/explanations`
→ `{ "layers": [ { "layer": "deterministic|shap|counterfactual|narrative", "payload": {...}, "caveats": [str] } ] }`

`GET /api/v1/analyses/{id}/mitigations`
→ `{ "items": [ { "id", "risk_addressed", "library_id", "action", "expected_effect", "assumptions": [], "trade_offs": [], "confidence", "verified_numbers": true } ] }`

`GET /api/v1/analyses/{id}/trace`
→ `{ "run": { "id", "graph_version", "started_at", "ended_at" },
     "steps": [ { "seq", "node", "agent", "status", "input_summary", "output_summary", "tool_calls": [ { "name", "args_sha", "latency_ms", "ok" } ], "latency_ms" } ],
     "llm_calls": [ { "provider", "model", "purpose", "tokens_in", "tokens_out", "latency_ms" } ],
     "guardrail_events": [ { "seq", "rule", "severity", "action", "detail" } ] }`

### Scenarios & stress

`GET /api/v1/scenarios/presets` → `[ { "preset_id", "name", "params", "description" } ]`

`POST /api/v1/analyses/{id}/scenarios` — body `{ "mode": "text", "text": "..." }` or `{ "mode": "params", "params": {...} }`
→ params: `201 { "scenario_id", "validated_params", "clamped": [str] }` (runs per FD-3)
→ text: `201 { "scenario_id", "translated_params", "mapping_notes": [...], "status": "awaiting_confirmation" }` then:

`POST /api/v1/scenarios/{id}/confirm` → `200 { "scenario_id", "validated_params", "clamped": [] }` ·
`POST /api/v1/scenarios/{id}/cancel` → `200`.

`POST /api/v1/scenarios/{id}/simulate` → `202 { "simulation_id" }` (twin run for that scenario alone)
→ `GET /api/v1/simulations/{id}` → trajectories + KPIs.

`POST /api/v1/analyses/{id}/stress-tests` `{ "scenario_id": "uuid" }` → `202 { "stress_test_id" }`
`GET /api/v1/stress-tests/{id}` → baseline/stressed trajectories, KPI comparison, breaches, waterfall,
dimension deltas.

### Weights, audit, health

`GET /api/v1/weights` → list · `POST /api/v1/weights` `{ "name", "weights": {"<dimension>": float} }`
(Σ=1 validated) · `PUT /api/v1/weights/{id}` (new version row).
`GET /api/v1/audit?object_type=&object_id=&limit=&offset=` → audit entries.
`GET /api/v1/health` → `{ "status": "ok", "db": true, "llm": "configured|not_configured", "version" }`.
`GET /metrics` — Prometheus (Phase 12), unauthenticated, internal network only.

## 3. SSE progress stream (frozen)

`GET /api/v1/analyses/{id}/events` — `text/event-stream`; heartbeat comment every 15 s; client
disconnect tolerant; replay from `Last-Event-ID` (events persisted with monotonic `seq`).

```text
event: run_started      data: {"analysis_id","seq","ts"}
event: node_started     data: {"analysis_id","seq","node","agent"}
event: node_completed   data: {"analysis_id","seq","node","status":"ok|degraded","latency_ms","summary"}
event: guardrail_event  data: {"analysis_id","seq","rule","severity","action","detail"}
event: llm_call         data: {"analysis_id","seq","purpose","model","tokens_in","tokens_out"}
event: completed        data: {"analysis_id","seq","status","composite_score"}
event: failed           data: {"analysis_id","seq","error":{"code","message"}}
```

## 4. Job lifecycle (frozen)

`pending → running → completed | failed | needs_review` (+ `cancelled` via `POST /api/v1/analyses/{id}/cancel`,
allowed while `pending|running` — cooperative cancel at the next node boundary). Transitions are
persisted; every terminal state is reachable only through `finalize` (guardrail-checked).
