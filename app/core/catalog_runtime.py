"""Catalog maintenance is independent of analysis, briefing and notification jobs."""
import asyncio
import logging
import os

from app.domain.catalog import utcnow
from app.integrations.catalog_sources import AlphaVantageCatalogSource, CatalogSourceError, KrxCatalogSource
from app.repositories.catalog import SecurityCatalogWriter

logger = logging.getLogger(__name__)


def run_catalog_tick(session_factory, sources=None, clock=utcnow):
    sources = sources if sources is not None else [KrxCatalogSource(os.getenv("KRX_API_KEY")),
        AlphaVantageCatalogSource(os.getenv("ALPHA_VANTAGE_API_KEY"))]
    results = {}
    for source in sources:
        with session_factory() as db:
            writer = SecurityCatalogWriter(db, clock)
            token = writer.claim(source.country)
            if not token:
                results[source.country] = "not_due"
                continue
            try:
                batch = source.fetch(clock())
                # Free Alpha Vantage: two requests per batch; avoid 48 requests/day.
                minimum = 360 if source.country == "US" else 60
                interval = max(minimum, int(os.getenv(f"CATALOG_{source.country}_INTERVAL_MINUTES", str(minimum))))
                results[source.country] = writer.publish(batch, token, interval)
            except Exception as exc:
                reason = str(exc) if isinstance(exc, CatalogSourceError) else "refresh_failed"
                writer.fail(source.country, token, reason)
                results[source.country] = reason
                # Never log request URLs: a provider key can be in query parameters.
                logger.warning("Catalog refresh failed: country=%s reason=%s", source.country, reason)
    return results


async def catalog_loop(session_factory):
    while True:
        try:
            await asyncio.to_thread(run_catalog_tick, session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Catalog scheduler tick failed")
        await asyncio.sleep(60)
