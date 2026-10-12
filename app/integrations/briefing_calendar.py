from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from app.domain.briefings import BriefingContext, BriefingError, market_for_symbol, utc


@lru_cache(maxsize=8)
def calendar(market):
    return xcals.get_calendar({"KR": "XKRX", "US": "XNYS"}[market])


class BriefingContextSource:
    def __init__(self, watchlist, history):
        self.watchlist = watchlist
        self.history = history

    def build(self, owner, request, now):
        now = utc(now)
        settings = self.history.settings(owner, request.market)
        n = request.n or settings.n
        if not n:
            raise BriefingError("차트 관찰기간 n을 지정하거나 제공 설정에 저장하세요.")
        symbols = [r.symbol for r in self.watchlist.list(owner) if market_for_symbol(r.symbol) == request.market]
        if request.symbols is not None:
            if set(request.symbols) - set(symbols):
                raise BriefingError("선택한 종목이 현재 시장의 관심종목에 없습니다. 목록을 새로고침한 뒤 다시 선택하세요.")
            symbols = [s for s in symbols if s in request.symbols]
        elif settings.symbols is not None:
            symbols = [s for s in symbols if s in settings.symbols]
        if not symbols:
            raise BriefingError("분석할 관심종목이 없습니다. 관심종목을 등록하고 브리핑 대상을 선택하세요.")
        if len(symbols) > 30:
            raise BriefingError("시장별 브리핑은 한 번에 30종목까지 지원합니다.")
        cal = calendar(request.market)
        today = now.astimezone(ZoneInfo("Asia/Seoul" if request.market == "KR" else "America/New_York")).date()
        day = pd.Timestamp(today)
        if not cal.is_session(day):
            raise BriefingError("선택한 시장의 거래일에 브리핑을 생성할 수 있습니다.")
        opening, closing = cal.session_open(day).to_pydatetime(), cal.session_close(day).to_pydatetime()
        if request.purpose == "pre_market" and now >= opening:
            raise BriefingError("장전 브리핑은 해당 시장의 장 시작 전에 생성합니다.")
        if request.purpose == "post_market" and now < closing + timedelta(minutes=15):
            raise BriefingError("장후 브리핑은 종가 확인을 위해 장 마감 15분 후부터 생성합니다.")
        previous = cal.previous_session(day)
        end = previous if request.purpose == "pre_market" else day
        end_idx = cal.sessions.get_loc(end)
        if end_idx + 1 < n:
            raise BriefingError("거래일 달력 범위를 벗어났습니다.")
        sessions = [s.date() for s in cal.sessions[end_idx - n + 1:end_idx + 1]]
        return BriefingContext(market=request.market, purpose=request.purpose, trade_date=today,
            previous_trade_date=previous.date(), cutoff_at=now, started_at=now, n=n,
            sessions=sessions, symbols=symbols)

    def options(self, owner, market, now):
        """Readiness for the UI uses the same clock/calendar policy as generation."""
        now = utc(now)
        cal = calendar(market)
        zone = ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")
        day = pd.Timestamp(now.astimezone(zone).date())
        symbols = [r.symbol for r in self.watchlist.list(owner) if market_for_symbol(r.symbol) == market]
        result = {"symbols": symbols, "as_of": now, "timezone": str(zone), "purposes": {}}
        if not cal.is_session(day):
            result["purposes"] = {p: {"available": False, "reason": "오늘은 이 시장의 휴장일입니다. 다음 거래일에 생성할 수 있습니다."}
                for p in ("pre_market", "post_market")}
            return result
        opening = cal.session_open(day).to_pydatetime()
        ready = cal.session_close(day).to_pydatetime() + timedelta(minutes=15)
        result["purposes"] = {
            "pre_market": {"available": now < opening, "reason": f"현지 시각 {opening.astimezone(zone):%H:%M} 개장 전까지 생성할 수 있습니다."},
            "post_market": {"available": now >= ready, "reason": f"현지 시각 {ready.astimezone(zone):%H:%M}부터 생성할 수 있습니다."},
        }
        return result

    @staticmethod
    def due(market, purpose, now):
        cal = calendar(market)
        local = utc(now).astimezone(ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York"))
        day = pd.Timestamp(local.date())
        if not cal.is_session(day):
            return False
        opening, closing = cal.session_open(day).to_pydatetime(), cal.session_close(day).to_pydatetime()
        return (opening - timedelta(minutes=30) <= now < opening) if purpose == "pre_market" else (
            closing + timedelta(minutes=15) <= now < closing + timedelta(hours=2))
