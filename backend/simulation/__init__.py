"""Business Digital Twin — deterministic monthly simulation engine (Phase 6).

A transparent, auditable monthly financial recursion for a single company
(frozen spec §19; docs/01_architecture/simulation.md §1-§2). Every number is
produced by deterministic Python: this package performs no I/O, no network
access, no LLM calls and no database writes (architecture rule R1/R3).

Scope boundaries (deliberate, enforced by this module's contents):
- This package runs the twin. It does not validate or clamp *scenarios*; that
  bounded schema, its presets and its clamp/reject policy are Phase 7
  (simulation.md §3-§4). It accepts already-structured, typed parameter deltas.
- It does not compare runs, rank scenarios, emit breach policy or build an
  EBITDA waterfall. Those are Phase 8 (simulation.md §5).
- It does not persist, serve or orchestrate. Persistence and API are Phase 10.

A simulation result is an *assumption-based intervention on a model*, not
discovered causal truth, and never professional financial advice.
"""

from __future__ import annotations

from backend.simulation.assumptions import InsufficientHistoryError, derive_assumptions
from backend.simulation.contracts import (  # noqa: E402
    CAUSALITY_DISCLAIMER,
    DEFAULT_HORIZON_MONTHS,
    MAX_HORIZON_MONTHS,
    NOT_ADVICE_DISCLAIMER,
    TWIN_VERSION,
    AssumptionRecord,
    MonthLedger,
    ParameterTag,
    Provenance,
    SimulationAssumptions,
    SimulationDiagnostics,
    SimulationInitialState,
    SimulationInput,
    SimulationInvariantResult,
    SimulationMonth,
    SimulationOverrides,
    SimulationRatio,
    SimulationRunResult,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
)
from backend.simulation.twin import (
    build_initial_state,
    check_invariants,
    run_twin,
    simulate,
    step_month,
)

__all__ = [
    "CAUSALITY_DISCLAIMER",
    "DEFAULT_HORIZON_MONTHS",
    "MAX_HORIZON_MONTHS",
    "NOT_ADVICE_DISCLAIMER",
    "TWIN_VERSION",
    "AssumptionRecord",
    "InsufficientHistoryError",
    "MonthLedger",
    "ParameterTag",
    "Provenance",
    "SimulationAssumptions",
    "SimulationDiagnostics",
    "SimulationInitialState",
    "SimulationInput",
    "SimulationInvariantResult",
    "SimulationMonth",
    "SimulationOverrides",
    "SimulationRatio",
    "SimulationRunResult",
    "SimulationState",
    "SimulationStatus",
    "SimulationSummary",
    "build_initial_state",
    "check_invariants",
    "derive_assumptions",
    "run_twin",
    "simulate",
    "step_month",
]
