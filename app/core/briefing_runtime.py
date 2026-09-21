"""Independent, exchange-session-aware briefing scheduler and outbox recovery."""
import asyncio
from datetime import datetime, timezone
import logging

from sqlalchemy import select

from app.core.briefings import build_briefing_coordinator
from app.domain.briefing_records import BriefingDeliveryRecord, BriefingPreferenceRecord, BriefingRunRecord
from app.domain.briefings import BriefingRequest

logger = logging.getLogger(__name__)


def run_briefing_tick(session_factory, *, now=None, builder=build_briefing_coordinator):
    now = now or datetime.now(timezone.utc)
    with session_factory() as db:
        # Snapshot identifiers only; each user's work has its own transaction/session.
        targets = [(r.owner_id, r.market) for r in db.scalars(select(BriefingPreferenceRecord))]
        abandoned = [(r.owner_id, r.id) for r in db.scalars(select(BriefingRunRecord).where(
            BriefingRunRecord.status == "preparing", BriefingRunRecord.lease_until <= now))]
        deliveries = [(r.owner_id, r.run_id) for r in db.scalars(select(BriefingDeliveryRecord).where(
            BriefingDeliveryRecord.status.in_(["pending", "sending"]))) ]
    for owner, run_id in abandoned:
        try:
            with session_factory() as db:
                service = builder(db)
                service.recover(service.history.get(owner, run_id))
        except Exception:
            logger.error("Briefing recovery failed for run %s", run_id)
    for owner, run_id in deliveries:
        try:
            with session_factory() as db:
                builder(db).delivery.deliver(owner, run_id)
        except Exception:
            logger.error("Briefing outbox failed for run %s", run_id)
    for owner, market in targets:
        for purpose in ("pre_market", "post_market"):
            try:
                with session_factory() as db:
                    service = builder(db)
                    settings = service.history.settings(owner, market)
                    if not getattr(settings, purpose + "_enabled") or not service.context_source.due(market, purpose, now):
                        continue
                    from zoneinfo import ZoneInfo
                    day = now.astimezone(ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")).date()
                    key = f"scheduled:{market}:{day}:{purpose}"
                    # Existing reservation wins even if settings were edited after generation.
                    if service.history.by_request(owner, key):
                        continue
                    request = BriefingRequest(request_id=f"scheduled-{market}-{day}-{purpose}", market=market, purpose=purpose)
                    service.generate(owner, request, scheduled_key=key)
            except Exception:
                logger.error("Scheduled briefing failed for owner %s market %s", owner, market)


async def briefing_loop(session_factory):
    while True:
        try:
            await asyncio.to_thread(run_briefing_tick, session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Briefing scheduler tick failed")
        await asyncio.sleep(30)
