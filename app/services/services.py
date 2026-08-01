from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

from app.domain.alert_conditions import DEFAULT_SYSTEM_ALERT_CONDITIONS
from app.domain.models import AnalysisResult as StoredAnalysisResult
from app.domain.briefings import normalize_judgment
from app.domain.symbols import normalize_symbol
from app.interfaces.analysis import AnalysisAgent
from app.interfaces.market_data import MarketDataProvider
from app.interfaces.notifications import AlertNotifier, AlertNotifyError
from app.interfaces.repositories import AlertConditionRepository, AnalysisRepository, WatchlistRepository
from app.schemas import model_to_dict


@dataclass
class ScheduledBatchResult:
    ran: bool
    symbols_analyzed: list[str] = field(default_factory=list)
    symbols_failed: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


class AnalysisProvider(Protocol):
    def get_latest_analysis(self, symbol: str, user_id: str = "default") -> StoredAnalysisResult:
        """Return the latest stored analysis, creating one when none exists."""

    def run_manual_analysis(self, symbol: str, user_id: str = "default") -> StoredAnalysisResult:
        """Create and store a fresh analysis for one symbol."""

    def list_analysis_history(
        self,
        symbol: str,
        *,
        user_id: str = "default",
        limit: int = 20,
        offset: int = 0,
    ) -> list[StoredAnalysisResult]:
        """Return stored analysis rows newest first."""

    def get_analysis_by_id(
        self, symbol: str, result_id: int, user_id: str = "default"
    ) -> StoredAnalysisResult:
        """Return one stored analysis row by id."""

    def run_scheduled_batch(self, *, now: datetime | None = None) -> ScheduledBatchResult:
        """Analyze all scheduled symbols."""


class AnalysisService:
    def __init__(
        self,
        *,
        analysis_repository: AnalysisRepository,
        alert_condition_repository: AlertConditionRepository,
        watchlist_repository: WatchlistRepository,
        market_data_provider: MarketDataProvider,
        agent: AnalysisAgent,
        alert_notifier: AlertNotifier,
        alert_window_checker: Callable[[datetime], bool],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.analysis_repository = analysis_repository
        self.alert_condition_repository = alert_condition_repository
        self.watchlist_repository = watchlist_repository
        self.market_data_provider = market_data_provider
        self.agent = agent
        self.alert_notifier = alert_notifier
        self.alert_window_checker = alert_window_checker
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def get_latest_analysis(self, symbol: str, user_id: str = "default") -> StoredAnalysisResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")

        latest = self.analysis_repository.get_latest(normalized_symbol, user_id)
        if latest is not None:
            self._try_send_pending_alert(latest)
            return latest

        stored = self.analyze_and_store(normalized_symbol, user_id=user_id)
        self._try_send_pending_alert(stored)
        return stored

    def run_manual_analysis(self, symbol: str, user_id: str = "default") -> StoredAnalysisResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")

        stored = self.analyze_and_store(normalized_symbol, user_id=user_id)
        self._try_send_pending_alert(stored)
        return stored

    def list_analysis_history(
        self,
        symbol: str,
        *,
        user_id: str = "default",
        limit: int = 20,
        offset: int = 0,
    ) -> list[StoredAnalysisResult]:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        return self.analysis_repository.list_by_symbol(
            normalized_symbol,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    def get_analysis_by_id(
        self, symbol: str, result_id: int, user_id: str = "default"
    ) -> StoredAnalysisResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")
        stored = self.analysis_repository.get_by_id(normalized_symbol, result_id, user_id)
        if stored is None:
            raise LookupError("analysis result not found")
        return stored

    def analyze_and_store(
        self,
        symbol: str,
        *,
        user_id: str = "default",
        briefing_type: str | None = None,
        trading_date: date | None = None,
    ) -> StoredAnalysisResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")

        market_data = self.market_data_provider.fetch(normalized_symbol)
        custom_conditions = self.alert_condition_repository.list_enabled_for_symbol(normalized_symbol)
        alert_conditions = [*DEFAULT_SYSTEM_ALERT_CONDITIONS, *custom_conditions]
        logger.info(
            "AnalysisService prepared analysis symbol=%s system_conditions=%d custom_conditions=%d",
            normalized_symbol,
            len(DEFAULT_SYSTEM_ALERT_CONDITIONS),
            len(custom_conditions),
        )
        agent_result = self.agent.analyze(market_data, alert_conditions)
        agent_result = self._validate_alert_decision(agent_result, alert_conditions)
        raw_result = model_to_dict(agent_result)

        return self.analysis_repository.save(
            user_id=user_id,
            symbol=agent_result.symbol,
            normalized_judgment=normalize_judgment(agent_result.verdict).value,
            briefing_type=briefing_type,
            trading_date=trading_date,
            data_timestamp=agent_result.data_time,
            overall_judgment=agent_result.verdict,
            summary=agent_result.summary,
            key_reasons=agent_result.key_reasons,
            risk_factors=agent_result.risk_factors,
            support_levels=agent_result.indicators,
            should_alert=agent_result.alert_triggered,
            triggered_alerts=agent_result.matched_alert_conditions,
            alert_reason=agent_result.alert_reason,
            raw_result=raw_result,
        )

    @staticmethod
    def _validate_alert_decision(agent_result, alert_conditions):
        allowed_ids = {condition.id for condition in alert_conditions}
        matched_ids = [
            condition_id
            for condition_id in agent_result.matched_alert_conditions
            if condition_id in allowed_ids
        ]
        should_alert = bool(agent_result.alert_triggered and matched_ids and agent_result.alert_reason)
        logger.info(
            "AnalysisService validated alert decision symbol=%s alert_triggered=%s matched=%s",
            agent_result.symbol,
            should_alert,
            matched_ids,
        )
        return agent_result.model_copy(
            update={
                "alert_triggered": should_alert,
                "matched_alert_conditions": matched_ids,
                "alert_reason": agent_result.alert_reason if should_alert else "",
            }
        )

    def run_scheduled_batch(self, *, now: datetime | None = None) -> ScheduledBatchResult:
        items = self.watchlist_repository.list()
        if not items:
            return ScheduledBatchResult(ran=True, skipped_reason="empty_watchlist")

        analyzed: list[str] = []
        failed: list[str] = []
        for item in items:
            try:
                stored = self.analyze_and_store(item.symbol)
                self._try_send_pending_alert(stored, now=now)
                analyzed.append(item.symbol)
            except Exception:
                logger.exception("Scheduled analysis failed for %s", item.symbol)
                failed.append(item.symbol)

        return ScheduledBatchResult(
            ran=True,
            symbols_analyzed=analyzed,
            symbols_failed=failed,
        )

    def _should_send_alert(self, stored: StoredAnalysisResult, *, now: datetime | None = None) -> bool:
        if not stored.should_alert or not stored.alert_reason:
            return False

        current = now or self.now_provider()
        if not self.alert_window_checker(current):
            return False

        if self.analysis_repository.has_sent_alert_for_conditions(
            stored.symbol,
            stored.triggered_alerts or [],
        ):
            return False

        return True

    def _try_send_pending_alert(
        self,
        stored: StoredAnalysisResult,
        *,
        now: datetime | None = None,
    ) -> None:
        if not self._should_send_alert(stored, now=now):
            return
        try:
            self.alert_notifier.send_alert(stored.alert_reason)
        except AlertNotifyError:
            raise
        except Exception as exc:
            logger.exception("Alert notification failed for %s", stored.symbol)
            raise AlertNotifyError(str(exc)) from exc
        self.analysis_repository.mark_alert_sent(stored)
