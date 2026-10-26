"""Catalog maintenance is independent of analysis, briefing and notification jobs."""
import asyncio
import logging
import os

from app.domain.catalog import utcnow
from app.core.catalog_policy import CatalogPolicy
from app.repositories.catalog_operations import CatalogMaintenance
from app.integrations.catalog_sources import AlphaVantageCatalogSource, CatalogSourceError, KrxCatalogSource
from app.repositories.catalog import SecurityCatalogWriter

logger = logging.getLogger(__name__)


def run_catalog_tick(session_factory, sources=None, clock=utcnow, *, verify_only=False, country=None):
    policy = CatalogPolicy.load()
    sources = sources if sources is not None else [KrxCatalogSource(os.getenv("KRX_API_KEY")),
        AlphaVantageCatalogSource(os.getenv("ALPHA_VANTAGE_API_KEY"))]
    results = {}
    for source in sources:
        if country and country != source.country:
            continue
        if hasattr(source, "key") and not source.key:
            results[source.country] = "provider_unconfigured"
            continue
        with session_factory() as db:
            writer = SecurityCatalogWriter(db, clock)
            token = writer.claim(source.country)
            if not token:
                results[source.country] = "not_due"
                continue
            try:
                batch = source.fetch(clock())
                if batch.country != source.country:
                    raise CatalogSourceError("provider_wrong_country")
                interval = policy.interval(source.country)
                if verify_only:
                    report = {"response_contract": "passed", "country": batch.country,
                        "source": batch.source, "requested_source_date": batch.source_date.isoformat(),
                        "observed_at": clock().isoformat(), "accepted_rows": len(batch.entries),
                        "exchanges": sorted({entry.exchange for entry in batch.entries}),
                        "accepted_rows_have_listing_date": True, "publication_lag": "not_measured",
                        "account_request_limit": "not_measured", "published": False}
                    writer.verified(batch, token, report, interval)
                    results[source.country] = report
                else:
                    results[source.country] = writer.publish(batch, token, interval)
            except Exception as exc:
                reason = str(exc) if isinstance(exc, CatalogSourceError) else "refresh_failed"
                writer.fail(source.country, token, reason)
                results[source.country] = reason
                # Never log request URLs: a provider key can be in query parameters.
                logger.warning("Catalog refresh failed: country=%s reason=%s", source.country, reason)
    with session_factory() as db:
        CatalogMaintenance(db, clock).prune()
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
