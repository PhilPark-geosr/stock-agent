"""Determine collection phase once, with the exact analysis input."""

import logging
from datetime import datetime, timezone

from app.domain.analysis_time import CalendarUnavailable, ChartBasis, SessionCalendar

logger = logging.getLogger(__name__)


class AnalysisTimeResolver:
    def __init__(self, calendar: SessionCalendar):
        self.calendar = calendar

    def resolve(self, basis: ChartBasis, metadata: dict, started_at: datetime, collected_at: datetime) -> ChartBasis:
        if started_at.utcoffset() is None or collected_at.utcoffset() is None:
            return basis.model_copy(update={"phase_reason": "collection_time_unknown"})
        fields = dict(collection_started_at=started_at.astimezone(timezone.utc), collected_at=collected_at.astimezone(timezone.utc))

        def result(reason, phase="unknown", **extra):
            return ChartBasis.model_validate({**basis.model_dump(), **fields, **extra,
                                             "collection_phase": phase, "phase_reason": reason})

        if basis.interval != "1d" or basis.session_date is None:
            return result("daily_session_unknown")
        if collected_at < started_at:
            return result("invalid_collection_window")
        if metadata.get("instrumentType") not in ("EQUITY", "ETF"):
            return result("unsupported_or_missing_market")
        # Explicit provider exchange codes, not suffix-free ticker guessing.
        markets = {
            "KSC": ("XKRX", "Asia/Seoul"), "KOE": ("XKRX", "Asia/Seoul"),
            "NYQ": ("XNYS", "America/New_York"), "NMS": ("XNAS", "America/New_York"),
            "NGM": ("XNAS", "America/New_York"), "NCM": ("XNAS", "America/New_York"),
            "ASE": ("XASE", "America/New_York"), "PCX": ("ARCX", "America/New_York"),
        }
        exchange_code = metadata.get("exchangeName")
        market = markets.get(exchange_code) if isinstance(exchange_code, str) else None
        if market is None:
            return result("unsupported_or_missing_market")
        exchange, zone = market
        fields["exchange"] = exchange
        if metadata.get("exchangeTimezoneName") != zone or basis.source_timezone != zone:
            return result("market_timezone_mismatch", session_date=None)
        try:
            session = self.calendar.session(exchange, basis.session_date)
        except CalendarUnavailable as exc:
            return result(str(exc))
        except Exception:
            logger.warning("Analysis session calendar unavailable exchange=%s", exchange, exc_info=True)
            return result("calendar_unavailable")
        if session is None:
            return result("not_a_trading_session")
        fields.update(session_open_at=session.opens_at.astimezone(timezone.utc),
                      session_close_at=session.closes_at.astimezone(timezone.utc), calendar_source=session.source)
        if started_at < session.opens_at:
            return result("before_session_open")
        if started_at >= session.closes_at:
            return result("request_started_after_close", "after_session")
        if collected_at < session.closes_at:
            return result("request_within_session", "during_session")
        return result("request_crossed_close", "boundary")
