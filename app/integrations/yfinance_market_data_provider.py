"""yfinance market-data provider for analysis system v1."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.interfaces.market_data import ClosingDataNotReadyError, MarketDataError, MarketDataProvider
from app.schemas import MarketDataSnapshot, MarketIndicators, OHLCVRecord


class YFinanceMarketDataProvider(MarketDataProvider):
    """Fetch recent OHLCV candles and indicators from yfinance."""

    def __init__(
        self,
        *,
        period: str = "3mo",
        interval: str = "1d",
        max_records: int = 60,
    ) -> None:
        self.period = period
        self.interval = interval
        self.max_records = max_records

    def fetch(self, symbol: str) -> MarketDataSnapshot:
        history = self._fetch_history(
            symbol,
            period=self.period,
            interval=self.interval,
        )
        return self._build_snapshot(symbol, history)

    def fetch_close(self, symbol: str, trading_date: date) -> MarketDataSnapshot:
        history = self._fetch_history(
            symbol,
            start=(trading_date - timedelta(days=90)).isoformat(),
            end=(trading_date + timedelta(days=1)).isoformat(),
            interval="1d",
        )
        clean_history = history.dropna(subset=["Open", "High", "Low", "Close"])
        if clean_history.empty or clean_history.index[-1].date() != trading_date:
            raise ClosingDataNotReadyError(
                f"closing data for {symbol} on {trading_date.isoformat()} is not ready"
            )
        return self._build_snapshot(symbol, clean_history)

    @staticmethod
    def _fetch_history(symbol: str, **history_options: Any):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise MarketDataError("yfinance is required to fetch market data") from exc

        ticker = yf.Ticker(symbol)
        try:
            history = ticker.history(
                auto_adjust=False,
                actions=False,
                **history_options,
            )
        except Exception as exc:
            raise MarketDataError(f"failed to fetch yfinance history for {symbol}") from exc

        if history is None or history.empty:
            raise MarketDataError(f"no market data returned for {symbol}")

        required_columns = {"Open", "High", "Low", "Close", "Volume"}
        missing_columns = required_columns.difference(set(history.columns))
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise MarketDataError(f"market data for {symbol} is missing columns: {missing}")

        return history

    def _build_snapshot(self, symbol: str, history: Any) -> MarketDataSnapshot:
        clean_history = history.dropna(subset=["Open", "High", "Low", "Close"])
        if clean_history.empty:
            raise MarketDataError(f"market data for {symbol} has no usable OHLC rows")

        records = [
            OHLCVRecord(
                time=_coerce_datetime(index_value),
                open=_finite_float(row["Open"]),
                high=_finite_float(row["High"]),
                low=_finite_float(row["Low"]),
                close=_finite_float(row["Close"]),
                volume=_finite_int(row["Volume"]),
            )
            for index_value, row in clean_history.tail(self.max_records).iterrows()
        ]

        if not records:
            raise MarketDataError(f"market data for {symbol} has no recent records")

        data_time = records[-1].time
        return MarketDataSnapshot(
            symbol=symbol,
            data_time=data_time,
            records=records,
            indicators=_build_indicators(clean_history),
        )


def _build_indicators(history: Any) -> MarketIndicators:
    close = history["Close"].dropna()
    volume = history["Volume"].dropna()

    latest_close = _last_float(close)
    previous_close = _nth_from_end_float(close, 2)
    change = _optional_subtract(latest_close, previous_close)
    change_percent = _optional_percent(change, previous_close)
    latest_volume = _last_int(volume)
    average_volume_20 = _mean_float(volume.tail(20))
    volume_ratio_20 = _optional_divide(latest_volume, average_volume_20)

    daily_returns = close.pct_change().dropna()
    volatility_20 = _std_float(daily_returns.tail(20))
    if volatility_20 is not None:
        volatility_20 *= math.sqrt(252) * 100

    return MarketIndicators(
        latest_close=latest_close,
        previous_close=previous_close,
        change=change,
        change_percent=change_percent,
        latest_volume=latest_volume,
        average_volume_20=average_volume_20,
        volume_ratio_20=volume_ratio_20,
        sma_5=_mean_float(close.tail(5)),
        sma_20=_mean_float(close.tail(20)),
        high_20=_max_float(history["High"].dropna().tail(20)),
        low_20=_min_float(history["Low"].dropna().tail(20)),
        volatility_20=volatility_20,
    )


def _coerce_datetime(value: Any) -> datetime:
    if hasattr(value, "to_pydatetime"):
        result = value.to_pydatetime()
    elif isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value))

    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _finite_float(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise MarketDataError("non-finite numeric value in market data")
    return result


def _finite_int(value: Any) -> int:
    result = _finite_float(value)
    return int(result)


def _last_float(values: Any) -> float | None:
    if len(values) == 0:
        return None
    return _nullable_float(values.iloc[-1])


def _last_int(values: Any) -> int | None:
    if len(values) == 0:
        return None
    result = _nullable_float(values.iloc[-1])
    return int(result) if result is not None else None


def _nth_from_end_float(values: Any, n: int) -> float | None:
    if len(values) < n:
        return None
    return _nullable_float(values.iloc[-n])


def _mean_float(values: Any) -> float | None:
    if len(values) == 0:
        return None
    return _nullable_float(values.mean())


def _std_float(values: Any) -> float | None:
    if len(values) == 0:
        return None
    return _nullable_float(values.std())


def _max_float(values: Any) -> float | None:
    if len(values) == 0:
        return None
    return _nullable_float(values.max())


def _min_float(values: Any) -> float | None:
    if len(values) == 0:
        return None
    return _nullable_float(values.min())


def _nullable_float(value: Any) -> float | None:
    result = float(value)
    if not math.isfinite(result):
        return None
    return result


def _optional_subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _optional_divide(left: float | int | None, right: float | int | None) -> float | None:
    if left is None or right in (None, 0):
        return None
    return float(left) / float(right)


def _optional_percent(numerator: float | None, denominator: float | None) -> float | None:
    ratio = _optional_divide(numerator, denominator)
    return ratio * 100 if ratio is not None else None
