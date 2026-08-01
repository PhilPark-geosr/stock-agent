from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.domain.briefings import BriefingType
from app.interfaces.repositories import WatchlistRepository
from app.interfaces.trading_calendar import TradingCalendar
from app.services.briefing_delivery import BriefingDeliveryService
from app.services.briefings import BriefingService, EmptyWatchlistError


@dataclass
class BriefingScheduleResult:
    generated_ids: list[int] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class BriefingScheduleService:
    def __init__(
        self,
        *,
        briefing_service: BriefingService,
        delivery_service: BriefingDeliveryService,
        watchlist_repository: WatchlistRepository,
        trading_calendar: TradingCalendar,
        exchanges: tuple[str, ...] = ("KRX", "US"),
        pre_market_lead_minutes: int = 60,
        post_market_grace_minutes: int = 90,
    ) -> None:
        self.briefing_service = briefing_service
        self.delivery_service = delivery_service
        self.watchlist_repository = watchlist_repository
        self.trading_calendar = trading_calendar
        self.exchanges = exchanges
        self.pre_market_lead = timedelta(minutes=pre_market_lead_minutes)
        self.post_market_grace = timedelta(minutes=post_market_grace_minutes)

    def run_due(self, now: datetime | None = None) -> BriefingScheduleResult:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        result = BriefingScheduleResult()
        user_ids = self.watchlist_repository.list_user_ids()
        for exchange in self.exchanges:
            trading_date = self.trading_calendar.local_date(exchange, current)
            session = self.trading_calendar.session_on(exchange, trading_date)
            if session is None:
                result.skipped.append(f"{exchange}:NON_TRADING_DAY")
                continue
            briefing_type = self._due_type(current, session.opens_at, session.closes_at)
            if briefing_type is None:
                result.skipped.append(f"{exchange}:NOT_DUE")
                continue

            for user_id in user_ids:
                try:
                    briefing = self.briefing_service.generate(
                        user_id=user_id,
                        exchange=exchange,
                        briefing_type=briefing_type,
                        trading_date=session.trading_date,
                    )
                except EmptyWatchlistError:
                    continue
                if briefing.status in {"COMPLETED", "PARTIAL"}:
                    self.delivery_service.deliver(briefing)
                    if briefing.id not in result.generated_ids:
                        result.generated_ids.append(briefing.id)
        return result

    def _due_type(
        self, current: datetime, opens_at: datetime, closes_at: datetime
    ) -> BriefingType | None:
        if opens_at - self.pre_market_lead <= current < opens_at:
            return BriefingType.PRE_MARKET
        if closes_at <= current < closes_at + self.post_market_grace:
            return BriefingType.POST_MARKET
        return None
