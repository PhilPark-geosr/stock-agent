from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from app.domain.briefings import BriefingType, compare_judgments, infer_exchange
from app.domain.models import AnalysisResult, InvestmentBriefing, WatchlistItem
from app.interfaces.market_data import ClosingDataNotReadyError, MarketDataError, MarketDataProvider
from app.interfaces.repositories import AnalysisRepository, BriefingRepository, WatchlistRepository
from app.interfaces.trading_calendar import TradingCalendar
from app.schemas import MarketDataSnapshot

logger = logging.getLogger(__name__)


class BriefingAnalysisProvider(Protocol):
    def analyze_and_store(
        self,
        symbol: str,
        *,
        user_id: str = "default",
        briefing_type: str | None = None,
        trading_date: date | None = None,
        market_data: MarketDataSnapshot | None = None,
    ) -> AnalysisResult:
        ...


class NonTradingDayError(ValueError):
    pass


class EmptyWatchlistError(ValueError):
    pass


class BriefingService:
    def __init__(
        self,
        *,
        briefing_repository: BriefingRepository,
        analysis_repository: AnalysisRepository,
        watchlist_repository: WatchlistRepository,
        analysis_provider: BriefingAnalysisProvider,
        market_data_provider: MarketDataProvider,
        trading_calendar: TradingCalendar,
    ) -> None:
        self.briefing_repository = briefing_repository
        self.analysis_repository = analysis_repository
        self.watchlist_repository = watchlist_repository
        self.analysis_provider = analysis_provider
        self.market_data_provider = market_data_provider
        self.trading_calendar = trading_calendar

    def generate(
        self,
        *,
        user_id: str,
        exchange: str,
        briefing_type: BriefingType,
        trading_date: date,
        force: bool = False,
    ) -> InvestmentBriefing:
        normalized_exchange = exchange.strip().upper()
        if self.trading_calendar.session_on(normalized_exchange, trading_date) is None:
            raise NonTradingDayError("SKIPPED_NON_TRADING_DAY")

        watchlist = self._watchlist_for_exchange(user_id, normalized_exchange)
        if not watchlist:
            raise EmptyWatchlistError("SKIPPED_EMPTY_WATCHLIST")

        briefing, acquired = self.briefing_repository.acquire_generation(
            user_id=user_id,
            exchange=normalized_exchange,
            briefing_type=briefing_type.value,
            trading_date=trading_date,
            force=force,
        )
        if not acquired:
            return briefing

        resolved_symbols = [item.symbol for item in watchlist]
        self.briefing_repository.replace_scope(
            briefing.id,
            source_type="WATCHLIST",
            source_value=normalized_exchange,
            resolved_symbols=resolved_symbols,
        )

        prepared_items: list[dict] = []
        failures: list[dict] = []
        for item in watchlist:
            try:
                prepared_items.append(
                    self._analyze_item(
                        item=item,
                        user_id=user_id,
                        briefing_type=briefing_type,
                        trading_date=trading_date,
                    )
                )
            except Exception as exc:
                failures.append(self._failure(item.symbol, exc))
                logger.exception("Briefing analysis failed user=%s symbol=%s", user_id, item.symbol)

        ranked = self._rank(prepared_items)

        if not ranked:
            status = "FAILED"
        elif failures:
            status = "PARTIAL"
        else:
            status = "COMPLETED"
        summary = self._render_summary(briefing_type, ranked, len(failures))
        briefing = self.briefing_repository.complete_generation(
            briefing,
            items=ranked,
            failures=failures,
            status=status,
            summary=summary,
            resolved_symbols=resolved_symbols,
        )
        return briefing

    def list_for_user(
        self, user_id: str, *, limit: int = 20, offset: int = 0
    ) -> list[InvestmentBriefing]:
        return self.briefing_repository.list_for_user(user_id, limit=limit, offset=offset)

    def get_for_user(self, briefing_id: int, user_id: str) -> InvestmentBriefing:
        briefing = self.briefing_repository.get_for_user(briefing_id, user_id)
        if briefing is None:
            raise LookupError("briefing not found")
        return briefing

    def get_items(self, briefing_id: int):
        return self.briefing_repository.list_items(briefing_id)

    def get_deliveries(self, briefing_id: int):
        return self.briefing_repository.list_deliveries(briefing_id)

    def get_scopes(self, briefing_id: int):
        return self.briefing_repository.list_scopes(briefing_id)

    def get_failures(self, briefing_id: int):
        return self.briefing_repository.list_failures(briefing_id)

    def _analyze_item(
        self,
        *,
        item: WatchlistItem,
        user_id: str,
        briefing_type: BriefingType,
        trading_date: date,
    ) -> dict:
        market_data = None
        if briefing_type is BriefingType.POST_MARKET:
            market_data = self.market_data_provider.fetch_close(item.symbol, trading_date)
        current = self.analysis_provider.analyze_and_store(
            item.symbol,
            user_id=user_id,
            briefing_type=briefing_type.value,
            trading_date=trading_date,
            market_data=market_data,
        )
        previous = None
        if briefing_type is BriefingType.POST_MARKET:
            previous = self.analysis_repository.get_previous_comparable(
                user_id=user_id,
                symbol=item.symbol,
                before_id=current.id,
                briefing_type=BriefingType.PRE_MARKET.value,
                trading_date=trading_date,
            )
        if previous is None:
            previous = self.analysis_repository.get_previous_comparable(
                user_id=user_id,
                symbol=item.symbol,
                before_id=current.id,
            )

        comparison_status, changed, distance = compare_judgments(
            current.normalized_judgment,
            previous.normalized_judgment if previous else None,
        )
        confidence = self._confidence(current)
        reason = None
        if changed:
            reason = ", ".join(current.key_reasons[:2]) or current.summary
        return {
            "symbol": item.symbol,
            "current_analysis_id": current.id,
            "previous_analysis_id": previous.id if previous else None,
            "rank": 0,
            "current_judgment": current.normalized_judgment,
            "previous_judgment": previous.normalized_judgment if previous else None,
            "judgment_changed": changed,
            "comparison_status": comparison_status,
            "judgment_distance": distance,
            "confidence": confidence,
            "data_timestamp": current.data_timestamp,
            "summary": current.summary,
            "change_reason": reason,
        }

    def _watchlist_for_exchange(self, user_id: str, exchange: str) -> list[WatchlistItem]:
        aliases = {"NASDAQ": "US", "NYSE": "US"}
        target = aliases.get(exchange, exchange)
        return [
            item
            for item in self.watchlist_repository.list(user_id)
            if infer_exchange(item.symbol) == target
        ]

    @staticmethod
    def _confidence(result: AnalysisResult) -> float | None:
        raw = result.raw_result or {}
        value = raw.get("confidence")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _rank(items: list[dict]) -> list[dict]:
        def key(item: dict):
            timestamp = item["data_timestamp"]
            timestamp_value = timestamp.timestamp() if timestamp is not None else 0.0
            return (
                -int(item["judgment_changed"]),
                -item["judgment_distance"],
                -(item["confidence"] if item["confidence"] is not None else -1.0),
                -timestamp_value,
                item["symbol"],
            )

        ranked = sorted(items, key=key)
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked

    @staticmethod
    def _render_summary(briefing_type: BriefingType, items: list[dict], failures: int) -> str:
        label = "장 시작 전 브리핑" if briefing_type is BriefingType.PRE_MARKET else "장 마감 후 요약"
        changed = sum(1 for item in items if item["judgment_changed"])
        return f"{label}: {len(items)}개 종목 분석, 판단 변경 {changed}개, 실패 {failures}개"

    @staticmethod
    def _failure(symbol: str, exc: Exception) -> dict:
        return {
            "symbol": symbol,
            "error_code": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
            "retryable": isinstance(exc, (ClosingDataNotReadyError, MarketDataError)),
            "attempt_count": 1,
        }
