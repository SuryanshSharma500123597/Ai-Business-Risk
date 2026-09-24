"""AI Business Risk — data engineering package (Phase 3).

Layout frozen in docs/01_architecture/architecture.md §2 and the approved
Phase 3 file distribution:

    contracts.py   canonical Pydantic schemas shared by every source
    ingest/        source adapters (synthetic primary; edgar/fred/stooq/yahoo)
    validate/      coverage matrix, identities, schema checks
    normalize/     period calendarization + currency handling
    cache.py       data/raw file cache with index.json provenance
    provenance.py  source_fetch_log writers
    storage.py     canonical -> ORM persistence
    features.py    model-ready frames (skeleton; fleshed out in Phase 5)

R3: this package must never import from agents/llm/app/services
(enforced by backend/tests/unit/test_architecture_imports.py).
"""
