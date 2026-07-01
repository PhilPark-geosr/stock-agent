"""Market-data tools for custom alert rules."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from app.market_data import YFinanceMarketDataProvider
from app.schemas import model_to_dict

logger = logging.getLogger(__name__)


@tool
def fetch_related_symbol_snapshot(symbol: str) -> dict[str, Any]:
    """Fetch recent market-data indicators for a stock symbol."""

    logger.info("CustomRuleTool fetch_related_symbol_snapshot start symbol=%s", symbol)
    snapshot = YFinanceMarketDataProvider().fetch(symbol)
    logger.info(
        "CustomRuleTool fetch_related_symbol_snapshot end symbol=%s data_time=%s",
        snapshot.symbol,
        snapshot.data_time,
    )
    return model_to_dict(snapshot)
