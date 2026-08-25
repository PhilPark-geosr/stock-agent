"""Domain value object and helpers for stock symbols."""

from dataclasses import dataclass


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


@dataclass(frozen=True, order=True)
class StockSymbol:
    value: str

    def __post_init__(self) -> None:
        normalized = normalize_symbol(self.value)
        if not normalized:
            raise ValueError("symbol is required")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def of(cls, raw: str) -> "StockSymbol":
        return cls(raw)
