"""Documented HTTP providers; no quote failure/missing row implies delisting."""
import csv
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from app.domain.catalog import CatalogBatch, CatalogEntry
from app.integrations.briefing_calendar import calendar


class _RedactProviderKey(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(value.copy_set_param("apikey", "REDACTED")
                if isinstance(value, httpx.URL) and "apikey" in value.params else value
                for value in record.args)
        return True


# httpx emits successful request URLs at INFO; LISTING_STATUS puts its key in the URL.
logging.getLogger("httpx").addFilter(_RedactProviderKey())


class CatalogSourceError(ValueError):
    pass


def completed_session(country, now):
    cal = calendar(country)
    zone = ZoneInfo("Asia/Seoul" if country == "KR" else "America/New_York")
    day = cal.date_to_session(pd.Timestamp(now.astimezone(zone).date()), direction="previous")
    if cal.session_close(day).to_pydatetime() + timedelta(hours=2) > now:
        day = cal.previous_session(day)
    return day.date()


class KrxCatalogSource:
    country = "KR"

    def __init__(self, key, client=None):
        self.key, self.client = key, client

    def fetch(self, now):
        if not self.key:
            raise CatalogSourceError("provider_unconfigured")
        day = completed_session("KR", now)
        with httpx.Client(timeout=30) if self.client is None else _borrow(self.client) as client:
            entries = []
            for market, suffix, endpoint in (("KOSPI", ".KS", "stk_isu_base_info"), ("KOSDAQ", ".KQ", "ksq_isu_base_info")):
                response = client.get(f"https://data-dbg.krx.co.kr/svc/apis/sto/{endpoint}",
                                      headers={"AUTH_KEY": self.key}, params={"basDd": day.strftime("%Y%m%d")})
                if response.status_code == 429:
                    raise CatalogSourceError("provider_rate_limit")
                response.raise_for_status()
                rows = response.json().get("OutBlock_1")
                if not isinstance(rows, list) or not rows:
                    raise CatalogSourceError("provider_incomplete")
                required = {"KIND_STKCERT_TP_NM", "ISU_SRT_CD", "ISU_CD", "ISU_ABBRV", "LIST_DD"}
                for row in rows:
                    if not isinstance(row, dict) or not required <= row.keys():
                        raise CatalogSourceError("provider_invalid_schema")
                    if row.get("BAS_DD") and row["BAS_DD"].replace("/", "").replace("-", "") != day.strftime("%Y%m%d"):
                        raise CatalogSourceError("provider_source_date_mismatch")
                    kind = {"보통주": "common", "우선주": "preferred"}.get(row["KIND_STKCERT_TP_NM"])
                    if not kind:
                        continue
                    code = row["ISU_SRT_CD"]
                    if not re.fullmatch(r"[0-9A-Z]{6}", code) or not row["ISU_CD"]:
                        raise CatalogSourceError("provider_invalid_identity")
                    entries.append(CatalogEntry(identity=row["ISU_CD"], symbol=code + suffix,
                        name=row["ISU_ABBRV"], exchange=market, kind=kind,
                        listed_on=datetime.strptime(row["LIST_DD"].replace("/", "").replace("-", ""), "%Y%m%d").date(),
                        aliases=[v for v in (row.get("ISU_NM"), row.get("ISU_ENG_NM")) if v]))
        return CatalogBatch(country="KR", source="KRX", source_date=day, fetched_at=now, entries=entries,
                            evidence="KRX stk_isu_base_info + ksq_isu_base_info; basDd=" + day.isoformat())


class AlphaVantageCatalogSource:
    country = "US"

    def __init__(self, key, client=None):
        self.key, self.client = key, client

    def fetch(self, now):
        if not self.key:
            raise CatalogSourceError("provider_unconfigured")
        day = completed_session("US", now)
        entries = []
        with httpx.Client(timeout=45) if self.client is None else _borrow(self.client) as client:
            for state in ("active", "delisted"):
                response = client.get("https://www.alphavantage.co/query", params={
                    "function": "LISTING_STATUS", "state": state, "date": day.isoformat(), "apikey": self.key})
                if response.status_code == 429:
                    raise CatalogSourceError("provider_rate_limit")
                response.raise_for_status()
                if response.text.lstrip().startswith("{"):
                    raise CatalogSourceError("provider_rate_limit" if "Information" in response.json() or "Note" in response.json() else "provider_rejected")
                reader = csv.DictReader(io.StringIO(response.text))
                required = {"symbol", "name", "exchange", "assetType", "ipoDate", "delistingDate", "status"}
                if not required <= set(reader.fieldnames or []):
                    raise CatalogSourceError("provider_invalid_schema")
                count = 0
                for row in reader:
                    count += 1
                    if row["assetType"] != "Stock" or re.search(r"\b(warrants?|rights?|units?|notes?|ETN|preferred|preference|depositary shares)\b", row["name"], re.I):
                        continue
                    if row["exchange"] not in {"NASDAQ", "NYSE", "AMEX"}:
                        continue
                    # Do not manufacture a durable identity from a ticker with no listing date.
                    if row["ipoDate"] in ("", "null", "None"):
                        continue
                    listed = datetime.strptime(row["ipoDate"], "%Y-%m-%d").date()
                    removed = None
                    if state == "delisted":
                        removed = datetime.strptime(row["delistingDate"], "%Y-%m-%d").date()
                    if row["status"].lower() != state:
                        raise CatalogSourceError("provider_invalid_status")
                    if not re.fullmatch(r"[A-Z]{1,6}(?:[.-][A-Z])?", row["symbol"]):
                        continue
                    symbol = row["symbol"].replace(".", "-")
                    entries.append(CatalogEntry(identity=f"{row['symbol']}:{listed}:{row['exchange']}",
                        symbol=symbol, name=row["name"], exchange=row["exchange"], listed_on=listed,
                        delisted_on=removed, kind="common", aliases=[row["symbol"]] if symbol != row["symbol"] else []))
                if not count:
                    raise CatalogSourceError("provider_incomplete")
        return CatalogBatch(country="US", source="ALPHA_VANTAGE", source_date=day, fetched_at=now,
                            entries=entries, evidence="Alpha Vantage LISTING_STATUS active + delisted; date=" + day.isoformat())


class _borrow:
    def __init__(self, client): self.client = client
    def __enter__(self): return self.client
    def __exit__(self, *args): return False
