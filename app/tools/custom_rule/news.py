"""News tools for custom alert rules."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def fetch_symbol_news(symbol: str) -> list[dict[str, Any]]:
    """Fetch recent news for a stock symbol."""

    logger.info("CustomRuleTool fetch_symbol_news start symbol=%s", symbol)
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required to fetch symbol news") from exc

    try:
        raw_items = yf.Ticker(symbol).news or []
    except Exception as exc:
        raise RuntimeError(f"failed to fetch news for {symbol}") from exc

    items = [_normalize_news_item(item) for item in raw_items[:10]]
    logger.info("CustomRuleTool fetch_symbol_news end symbol=%s items=%d", symbol, len(items))
    return items


def _normalize_news_item(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    return {
        "title": item.get("title") or content.get("title"),
        "publisher": item.get("publisher") or content.get("provider", {}).get("displayName"),
        "link": item.get("link") or content.get("canonicalUrl", {}).get("url"),
        "published_at": item.get("providerPublishTime") or content.get("pubDate"),
    }
