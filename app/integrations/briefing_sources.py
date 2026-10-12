"""Public evidence adapters. Provider failures never masquerade as an empty search."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import math
import os
import threading
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import httpx

from app.domain.briefings import Evidence, SourceStatus, utc
from app.integrations.briefing_calendar import calendar


_sec_lock = threading.Lock()
_sec_last_request = 0.0


def sec_get(client, url, **kwargs):
    # One process-wide throttle across manual and scheduled runs.
    global _sec_last_request
    with _sec_lock:
        time.sleep(max(0, 0.2 - (time.monotonic() - _sec_last_request)))
        _sec_last_request = time.monotonic()
    return client.get(url, **kwargs)


class FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "ix:hidden"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "ix:hidden"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def filing_excerpt(content):
    parser = FilingText()
    parser.feed(content)
    return " ".join(parser.parts)[:6000]


def evidence_id(kind, symbol, key):
    return f"{kind}:" + sha256(f"{symbol}:{key}".encode()).hexdigest()[:24]


def yahoo_news(ticker, symbol):
    # get_news() silently maps malformed JSON/missing stream to []. Keep its
    # cookie-aware transport, but validate the actual response before claiming 0.
    response = ticker._data.post("https://finance.yahoo.com/xhr/ncp?queryRef=latestNews&serviceKey=ncp_fin",
        body={"serviceConfig": {"snippetCount": 50, "s": [symbol]}}, timeout=20)
    response.raise_for_status()
    stream = response.json()["data"]["tickerStream"]["stream"]
    if not isinstance(stream, list):
        raise ValueError("invalid news stream")
    return [article for article in stream if not article.get("ad")]


class YFinanceEvidenceSource:
    def fetch(self, symbol, context):
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        evidence, statuses = [], []
        collected = datetime.now(timezone.utc)
        try:
            history = ticker.history(start=str(context.sessions[0]),
                end=str(context.sessions[-1] + timedelta(days=1)), interval="1d",
                auto_adjust=False, actions=False, timeout=20, raise_errors=True)
            candles = []
            allowed = set(context.sessions)
            for index, row in history.iterrows():
                day = index.date()
                if day not in allowed:
                    continue
                values = {k.lower(): float(row[k]) for k in ("Open", "High", "Low", "Close", "Volume")}
                if not all(math.isfinite(v) for v in values.values()):
                    continue
                candles.append({"date": str(day), **values})
            if candles:
                published = calendar(context.market).session_close(candles[-1]["date"]).to_pydatetime()
                evidence.append(Evidence(id=evidence_id("chart", symbol, str(context.sessions)), symbol=symbol,
                    kind="chart", source="Yahoo Finance OHLCV", url=f"https://finance.yahoo.com/quote/{symbol}/history/",
                    published_at=published, collected_at=collected,
                    text=f"일봉 {len(candles)}개 / 요청 {context.n}거래일. 배당·분할 조정 전 가격.",
                    data={"candles": candles, "adjusted": False}))
            complete = len(candles) == context.n
            statuses.append(SourceStatus(symbol=symbol, source="Yahoo Finance OHLCV", kind="chart",
                status="ok" if complete else "partial" if candles else "empty",
                detail=f"요청 {context.n}거래일, 관측 {len(candles)}개"))
        except Exception:
            statuses.append(SourceStatus(symbol=symbol, source="Yahoo Finance OHLCV", kind="chart",
                status="failed", detail="차트 공급자 조회 실패"))
        try:
            articles = yahoo_news(ticker, symbol)
            for article in articles:
                content = article.get("content") or article
                raw_time = content.get("pubDate") or article.get("providerPublishTime")
                if not raw_time:
                    continue
                published = (datetime.fromtimestamp(raw_time, timezone.utc) if isinstance(raw_time, (int, float))
                             else utc(datetime.fromisoformat(raw_time.replace("Z", "+00:00"))))
                url = (content.get("canonicalUrl") or {}).get("url") or article.get("link")
                if not url or not url.startswith(("https://", "http://")):
                    continue
                title = content.get("title") or ""
                evidence.append(Evidence(id=evidence_id("news", symbol, url), symbol=symbol, kind="news",
                    source=(content.get("provider") or {}).get("displayName") or "Yahoo Finance News",
                    url=url, published_at=published, collected_at=collected,
                    text=(title + "\n" + (content.get("summary") or ""))[:5000]))
            statuses.append(SourceStatus(symbol=symbol, source="Yahoo Finance News", kind="news",
                status="partial" if articles else "empty",
                detail="최근 최대 50건 조회. 기간 내 전체 뉴스의 완전한 수집을 보장하지 않음."))
        except Exception:
            statuses.append(SourceStatus(symbol=symbol, source="Yahoo Finance News", kind="news",
                status="failed", detail="뉴스 공급자 조회 실패"))
        return evidence, statuses


class DisclosureSource:
    """DART for Korean listings, SEC submissions for US listings; optional credentials."""
    def __init__(self, client=None, dart_key=None, sec_user_agent=None):
        self.client = client
        self.dart_key = dart_key if dart_key is not None else os.getenv("DART_API_KEY")
        self.sec_user_agent = sec_user_agent if sec_user_agent is not None else os.getenv("SEC_USER_AGENT")
        self._dart_codes = None
        self._sec_companies = None

    def fetch(self, symbol, context):
        provider = "DART" if context.market == "KR" else "SEC"
        configured = self.dart_key if context.market == "KR" else self.sec_user_agent
        if not configured:
            return [], [SourceStatus(symbol=symbol, source=provider, kind="disclosure",
                status="unconfigured", detail=f"{provider} 공시 조회 설정 없음")]
        try:
            if self.client is not None:
                return self._fetch(self.client, provider, symbol, context)
            with httpx.Client(timeout=20) as client:
                return self._fetch(client, provider, symbol, context)
        except Exception:
            # Do not persist exception URLs containing DART credentials.
            return [], [SourceStatus(symbol=symbol, source=provider, kind="disclosure",
                status="failed", detail=f"{provider} 공시 조회 실패")]

    def _fetch(self, client, provider, symbol, context):
        records, limited = (self._dart(client, symbol, context) if provider == "DART"
                            else self._sec(client, symbol))
        # Only retrieve bodies that can actually be included at the fixed cutoff.
        from datetime import time as day_time
        zone = ZoneInfo("Asia/Seoul" if provider == "DART" else "America/New_York")
        start = utc(datetime.combine(context.sessions[0], day_time.min, zone))
        eligible = sorted((r for r in records if start <= r.published_at <= context.cutoff_at),
                          key=lambda r: r.published_at, reverse=True)
        for record in eligible[:5]:
            try:
                if provider == "DART":
                    response = client.get("https://opendart.fss.or.kr/api/document.xml",
                        params={"crtfc_key": self.dart_key, "rcept_no": record.data["receipt_no"]})
                    response.raise_for_status()
                    with ZipFile(BytesIO(response.content)) as archive:
                        members = [m for m in archive.infolist() if m.filename.lower().endswith((".xml", ".html"))]
                        if not members or sum(m.file_size for m in members) > 20000000:
                            raise ValueError("filing size limit")
                        content = archive.read(members[0])
                    try:
                        decoded = content.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        decoded = content.decode("euc-kr", errors="replace")
                else:
                    response = sec_get(client, record.url, headers={"User-Agent": self.sec_user_agent})
                    response.raise_for_status()
                    if len(response.content) > 20000000:
                        raise ValueError("filing size limit")
                    decoded = response.text
                excerpt = filing_excerpt(decoded)
                if not excerpt:
                    raise ValueError("empty filing text")
                record.text += "\n[원문 앞부분 발췌, 전체 보고서가 아님]\n" + excerpt
                record.data["body_status"] = "excerpt"
            except Exception:
                record.data["body_status"] = "failed"
                record.text += "\n[원문 수집 실패: 제목만 제공됨]"
        for record in eligible[5:]:
            record.data["body_status"] = "limit"
        return records, [SourceStatus(symbol=symbol, source=provider, kind="disclosure",
            status="partial" if limited else "ok" if records else "empty",
            detail=("공시 목록과 최근 최대 5건의 원문 앞부분 6,000자 발췌. 전체 보고서 분석이 아님. " +
                ("일부 원문 수집 실패. " if any(r.data.get("body_status") == "failed" for r in eligible) else "") +
                ("접수 시각 없는 DART 당일 자료는 제외, 과거 자료는 접수일 종료를 확인 가능 시점으로 사용."
                 if provider == "DART" else "SEC recent 목록 범위만 조회.")))]

    def _dart(self, client, symbol, context):
        if self._dart_codes is None:
            response = client.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": self.dart_key})
            response.raise_for_status()
            with ZipFile(BytesIO(response.content)) as archive:
                member = archive.getinfo("CORPCODE.xml")
                if member.file_size > 50000000:
                    raise ValueError("corporation directory too large")
                root = ET.fromstring(archive.read(member))
            self._dart_codes = {(x.findtext("stock_code") or "").strip(): x.findtext("corp_code") for x in root.findall("list")}
        code = self._dart_codes.get(symbol.split(".")[0])
        if not code:
            raise ValueError("no corporation mapping")
        records, total = [], 1
        for page in range(1, 6):
            response = client.get("https://opendart.fss.or.kr/api/list.json", params={
                "crtfc_key": self.dart_key, "corp_code": code,
                "bgn_de": context.sessions[0].strftime("%Y%m%d"),
                "end_de": context.trade_date.strftime("%Y%m%d"), "page_count": 100, "page_no": page})
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "013":
                return [], False
            if payload.get("status") != "000":
                raise ValueError("DART rejected search")
            total = int(payload.get("total_page", 1))
            for row in payload.get("list", []):
                # Date precision only: use conservative upper bound, never fabricate intraday time.
                day = datetime.strptime(row["rcept_dt"], "%Y%m%d").replace(tzinfo=ZoneInfo("Asia/Seoul"))
                receipt = row["rcept_no"]
                if not receipt.isdigit():
                    continue
                records.append(Evidence(id=evidence_id("disclosure", symbol, receipt), symbol=symbol,
                    kind="disclosure", source="DART", url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                    published_at=utc(day + timedelta(days=1)), published_precision="day",
                    collected_at=datetime.now(timezone.utc), text=row["report_nm"],
                    data={"receipt_no": receipt, "receipt_date": str(day.date()), "precision_note": "접수일 종료 상한"}))
            if page >= total:
                break
        return records, True  # Date-only / title-only coverage is explicitly partial.

    def _sec(self, client, symbol):
        headers = {"User-Agent": self.sec_user_agent, "Accept-Encoding": "gzip, deflate"}
        if self._sec_companies is None:
            response = sec_get(client, "https://www.sec.gov/files/company_tickers.json", headers=headers)
            response.raise_for_status()
            self._sec_companies = {r["ticker"]: r for r in response.json().values()}
        company = self._sec_companies.get(symbol)
        if company is None:
            raise ValueError("no SEC company mapping")
        cik = str(company["cik_str"])
        response = sec_get(client, f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", headers=headers)
        response.raise_for_status()
        recent = response.json().get("filings", {}).get("recent", {})
        records = []
        for index, accession in enumerate(recent.get("accessionNumber", [])):
            accepted = recent.get("acceptanceDateTime", [])[index]
            published = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
            if published.tzinfo is None or not accession.replace("-", "").isdigit():
                continue
            published = utc(published)
            document = recent["primaryDocument"][index]
            if not all(c.isalnum() or c in "-_." for c in document):
                continue
            records.append(Evidence(id=evidence_id("disclosure", symbol, accession), symbol=symbol,
                kind="disclosure", source="SEC", published_at=published, collected_at=datetime.now(timezone.utc),
                url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}",
                text=f"{recent['form'][index]} {recent.get('primaryDocDescription', [''] * len(recent['form']))[index]}"))
        return records, True
