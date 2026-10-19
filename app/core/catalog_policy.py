"""Validated operating defaults; provider entitlements are not inferred from these limits."""
import os
from dataclasses import dataclass


def _integer(name, default, minimum=1):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class CatalogPolicy:
    kr_interval: int
    us_interval: int
    max_source_age_days: int
    max_fetch_age_hours: int
    kr_requests: int
    us_requests: int
    snapshot_days: int
    attempt_days: int

    @classmethod
    def load(cls):
        return cls(_integer("CATALOG_KR_INTERVAL_MINUTES", 60, 60),
                   _integer("CATALOG_US_INTERVAL_MINUTES", 360, 360),
                   _integer("CATALOG_MAX_SOURCE_AGE_DAYS", 7),
                   _integer("CATALOG_MAX_FETCH_AGE_HOURS", 48),
                   _integer("CATALOG_KR_REQUESTS_PER_24H", 96, 2),
                   _integer("CATALOG_US_REQUESTS_PER_24H", 20, 2),
                   _integer("CATALOG_SNAPSHOT_RETENTION_DAYS", 90, 90),
                   _integer("CATALOG_ATTEMPT_RETENTION_DAYS", 365, 365))

    def interval(self, country):
        return self.kr_interval if country == "KR" else self.us_interval

    def request_budget(self, country):
        return self.kr_requests if country == "KR" else self.us_requests
