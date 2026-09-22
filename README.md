# AI Business Risk

**Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform**

AI Business Risk combines LLM-based multi-agent reasoning, machine learning, deterministic quantitative
finance, scenario simulation, and a simplified business digital twin to analyze business risk and run
explainable stress tests. Every numerical result is produced by deterministic, auditable engines —
never by an LLM. The LLM layer only interprets, structures requests, and narrates.

> **Status: Phase 2 — Foundation.** Phase 0 (specification) and Phase 1 (architecture freeze) are
> **approved**; the repository foundation is implemented (config, logging, database + migrations,
> app factory, tests — 23 passing). Engine/agent/API features arrive in later phases (see roadmap).

## Documentation

| Document | Contents |
|---|---|
| [docs/00_research/phase-0-research.md](docs/00_research/phase-0-research.md) | Source-verified research: ERM practice, existing platforms, literature, data sources & licensing, LLM providers |
| [docs/master-project-specification.md](docs/master-project-specification.md) | Full 41-section master project specification (problem, architecture, agents, engines, roadmap, evaluation) |
| [docs/development-log.md](docs/development-log.md) | Phase-by-phase development log |

## Development Roadmap (approved numbering)

| Phase | Name | Status |
|---|---|---|
| 0 | Research + Master Specification | **Approved** |
| 1 | Architecture Freeze | **Approved** |
| 2 | Foundation | **Complete — awaiting approval** |
| 3 | Data Engineering | — |
| 4 | Quantitative Risk Engine | — |
| 5 | ML Engine | — |
| 6 | Business Digital Twin | — |
| 7 | Scenario Engine | — |
| 8 | Stress Testing | — |
| 9 | Multi-Agent LangGraph | — |
| 10 | Backend/API | — |
| 11 | Frontend | — |
| 12 | Testing / Observability / Security | — |
| 13 | Evaluation / Benchmarking | — |
| 14 | Final Documentation / Viva | — |

Phases are executed strictly one at a time. Each phase ends with a report and an explicit
approval gate before the next phase starts.

## License

MIT — see [LICENSE](LICENSE) (decided in Phase 2).
