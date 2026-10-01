"""Phase 3 source adapters.

Synthetic data is local and deterministic. External adapters return typed
series/dataset objects with source metadata and explicit degraded status.
"""

from backend.data_engine.ingest.edgar import EdgarAdapter
from backend.data_engine.ingest.fred import FredAdapter
from backend.data_engine.ingest.stooq import StooqAdapter
from backend.data_engine.ingest.world_bank import WorldBankAdapter
from backend.data_engine.ingest.yahoo import MarketSeriesProvider, YahooAdapter

__all__ = [
    "EdgarAdapter",
    "FredAdapter",
    "MarketSeriesProvider",
    "StooqAdapter",
    "WorldBankAdapter",
    "YahooAdapter",
]
