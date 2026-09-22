"""FastAPI dependencies (frozen: docs/01_architecture/architecture.md §2).

Phase 2: re-export the DB session dependency. Auth dependencies are added
in Phase 12.
"""

from __future__ import annotations

from backend.database.session import get_db

__all__ = ["get_db"]
