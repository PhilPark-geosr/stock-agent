from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agent import AnalysisAgent, GeminiAnalysisAgent
from app.alert_conditions import DEFAULT_SYSTEM_ALERT_CONDITIONS
from app.analysis_graph import MainAnalysisAgent
from app.custom_rule_agent import (
    CustomRuleAgent,
    LangGraphCustomRuleAgent,
)
from app.database import get_db
from app.kakao_notify import AlertNotifier, KakaoNotifyError, get_default_alert_notifier
from app.market_data import MarketDataProvider, YFinanceMarketDataProvider
from app.models import AnalysisResult as StoredAnalysisResult
from app.repositories import AlertConditionRepository, AnalysisRepository, WatchlistRepository, normalize_symbol
from app.scheduler_config import scheduler_settings
from app.schemas import model_to_dict
from app.trading_window import is_alert_window


@dataclass
class ScheduledBatchResult:
    ran: bool
    symbols_analyzed: list[str] = field(default_factory=list)
    symbols_failed: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


class AnalysisProvider(Protocol):
    def get_latest_analysis(self, symbol: str) -> StoredAnalysisResult:
        """Return the latest stored analysis, creating one when none exists."""


class AnalysisService:
    def __init__(
        self,
        *,
        analysis_repository: AnalysisRepository,
        alert_condition_repository: AlertConditionRepository,
        watchlist_repository: WatchlistRepository,
        market_data_provider: MarketDataProvider,
        agent: AnalysisAgent,
        alert_notifier: AlertNotifier | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.analysis_repository = analysis_repository
        self.alert_condition_repository = alert_condition_repository
        self.watchlist_repository = watchlist_repository
        self.market_data_provider = market_data_provider
        self.agent = agent
        self.alert_notifier = alert_notifier or get_default_alert_notifier()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def get_latest_analysis(self, symbol: str) -> StoredAnalysisResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise ValueError("symbol is required")

        latest = self.analysis_repository.get_latest(normalized_symbol)
        if latest is not None:
            self._try_send_pending_alert(latest)
            return latest

        stored = self.analyze_and_store(normalized_symbol)
        self._try_send_pending_alert(stored)
        return stored

    def analyze_and_store(self, symbol: str) -> StoredAnalysisResult:
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
            symbol=agent_result.symbol,
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

        settings = scheduler_settings()
        current = now or self.now_provider()
        if not is_alert_window(
            current,
            start_hour=int(settings["market_start_hour"]),
            end_hour=int(settings["market_end_hour"]),
            tz_name=str(settings["timezone"]),
        ):
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
        except KakaoNotifyError:
            raise
        except Exception as exc:
            logger.exception("Kakao alert failed for %s", stored.symbol)
            raise KakaoNotifyError(str(exc)) from exc
        self.analysis_repository.mark_alert_sent(stored)


def build_analysis_service(
    db: Session,
    *,
    market_data_provider: MarketDataProvider | None = None,
    agent: AnalysisAgent | None = None,
    alert_notifier: AlertNotifier | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> AnalysisService:
    return AnalysisService(
        analysis_repository=AnalysisRepository(db),
        alert_condition_repository=AlertConditionRepository(db),
        watchlist_repository=WatchlistRepository(db),
        market_data_provider=market_data_provider or YFinanceMarketDataProvider(),
        agent=agent
        or MainAnalysisAgent(
            main_model=GeminiAnalysisAgent(),
            custom_rule_agent=get_default_custom_rule_agent(),
        ),
        alert_notifier=alert_notifier or get_default_alert_notifier(),
        now_provider=now_provider,
    )


def get_market_data_provider() -> MarketDataProvider:
    return YFinanceMarketDataProvider()


def get_default_custom_rule_agent() -> CustomRuleAgent:
    return LangGraphCustomRuleAgent()


def get_analysis_agent() -> AnalysisAgent:
    return MainAnalysisAgent(
        main_model=GeminiAnalysisAgent(),
        custom_rule_agent=get_default_custom_rule_agent(),
    )


def get_alert_notifier() -> AlertNotifier:
    return get_default_alert_notifier()


def get_analysis_service(
    db: Session = Depends(get_db),
    market_data_provider: MarketDataProvider = Depends(get_market_data_provider),
    agent: AnalysisAgent = Depends(get_analysis_agent),
    alert_notifier: AlertNotifier = Depends(get_alert_notifier),
) -> AnalysisProvider:
    return build_analysis_service(
        db,
        market_data_provider=market_data_provider,
        agent=agent,
        alert_notifier=alert_notifier,
    )
