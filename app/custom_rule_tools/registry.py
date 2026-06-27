"""Tool registry for custom-rule agents."""

from __future__ import annotations

from app.custom_rule_tools.market import fetch_related_symbol_snapshot
from app.custom_rule_tools.news import fetch_symbol_news


def get_custom_rule_tools():
    return [
        fetch_symbol_news,
        fetch_related_symbol_snapshot,
    ]
