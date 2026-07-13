"""Domain helpers for stock symbols."""


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()
