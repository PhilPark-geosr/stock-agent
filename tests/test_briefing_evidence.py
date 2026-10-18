from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile
from types import SimpleNamespace

import httpx
import pytest

from app.application.briefing_evidence import EvidenceBuilder
from app.cli.briefing_prompt import preview_fixture
from app.domain.briefings import Evidence, SourceStatus
from app.integrations.briefing_calendar import BriefingContextSource
from app.integrations.briefing_sources import DisclosureSource, yahoo_news, YFinanceEvidenceSource


def zipped(name, text):
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(name, text)
    return data.getvalue()


def test_dart_receipt_date_cutoff_original_excerpt_and_key_redaction():
    context, _ = preview_fixture()
    body_calls = []
    def respond(request):
        if request.url.path.endswith("corpCode.xml"):
            return httpx.Response(200, content=zipped("CORPCODE.xml", "<result><list><stock_code>005930</stock_code><corp_code>00126380</corp_code></list></result>"))
        if request.url.path.endswith("document.xml"):
            body_calls.append(request.url.params["rcept_no"])
            return httpx.Response(200, content=zipped("report.xml", "<DOCUMENT><TITLE>공식 실적</TITLE><P>매출 증가</P></DOCUMENT>"))
        return httpx.Response(200, json={"status": "000", "total_page": 1, "list": [
            {"rcept_dt": "20260901", "rcept_no": "202609010001", "report_nm": "실적 발표"},
            {"rcept_dt": "20260902", "rcept_no": "202609020001", "report_nm": "당일 공시"}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source = DisclosureSource(client=client, dart_key="SECRET")
        snapshot = EvidenceBuilder([source]).build(context)
    assert len(snapshot.evidence) == 1
    assert snapshot.evidence[0].published_precision == "day"
    assert "매출 증가" in snapshot.evidence[0].text
    assert body_calls == ["202609010001"]  # Do not retrieve future/uncertain same-day bodies.
    assert len(snapshot.excluded) == 1
    assert snapshot.sources[0].status == "partial"
    assert "SECRET" not in snapshot.model_dump_json()


def test_disclosures_distinguish_unconfigured_empty_failed():
    context, _ = preview_fixture()
    assert DisclosureSource(dart_key="").fetch("005930.KS", context)[1][0].status == "unconfigured"
    def response(request):
        return httpx.Response(200, json={"status": "013"})
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        source = DisclosureSource(client=client, dart_key="SECRET")
        source._dart_codes = {"005930": "00126380"}
        assert source.fetch("005930.KS", context)[1][0].status == "empty"
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        source = DisclosureSource(client=client, dart_key="SECRET")
        assert source.fetch("005930.KS", context)[1][0].status == "failed"
        assert "SECRET" not in source.fetch("005930.KS", context)[1][0].model_dump_json()


def test_sec_maps_company_and_reads_dated_original_with_declared_agent():
    context, _ = preview_fixture()
    context = context.model_copy(update={"market": "US", "symbols": ["AAPL"]})
    calls = []
    def respond(request):
        calls.append(request)
        assert request.headers["User-Agent"] == "Example test@example.com"
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"ticker": "AAPL", "cik_str": 320193}})
        if request.url.host == "data.sec.gov":
            return httpx.Response(200, json={"filings": {"recent": {
                "accessionNumber": ["0000320193-26-000001"], "acceptanceDateTime": ["2026-09-01T20:00:00Z"],
                "primaryDocument": ["aapl.htm"], "form": ["8-K"], "primaryDocDescription": ["Current report"]}}})
        return httpx.Response(200, text="<html><style>hidden</style><body>Revenue grew<script>BAD</script></body></html>")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        snapshot = EvidenceBuilder([DisclosureSource(client=client, sec_user_agent="Example test@example.com")]).build(context)
    assert len(calls) == 3
    assert len(snapshot.evidence) == 1
    item = snapshot.evidence[0]
    assert item.published_at.hour == 20 and item.published_precision == "instant"
    assert "Revenue grew" in item.text and "BAD" not in item.text
    assert item.url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl.htm"


def test_public_capacity_preserves_both_kinds_and_excludes_future_data():
    context, _ = preview_fixture()
    class Source:
        def fetch(self, symbol, ctx):
            rows = [Evidence(id=f"item:{i}", symbol=symbol, kind="news" if i < 25 else "disclosure",
                source="fixture", published_at=ctx.cutoff_at - timedelta(minutes=i),
                collected_at=ctx.cutoff_at, text="test") for i in range(35)]
            rows.append(rows[0].model_copy(update={"id": "future", "published_at": ctx.cutoff_at + timedelta(seconds=1)}))
            return rows, [SourceStatus(symbol=symbol, source="fixture", kind="public", status="ok")]
    snapshot = EvidenceBuilder([Source()]).build(context)
    assert len(snapshot.evidence) == 20
    assert sum(e.kind == "disclosure" for e in snapshot.evidence) == 10
    assert len(snapshot.excluded) == 16
    assert snapshot.eligible_symbols == context.symbols


def test_exchange_windows_observe_us_holidays_and_early_closes():
    # Thanksgiving is closed; Friday after Thanksgiving closes at 18:00 UTC.
    utc = timezone.utc
    assert not BriefingContextSource.due("US", "post_market", datetime(2026, 11, 26, 21, 30, tzinfo=utc))
    assert not BriefingContextSource.due("US", "post_market", datetime(2026, 11, 27, 18, 10, tzinfo=utc))
    assert BriefingContextSource.due("US", "post_market", datetime(2026, 11, 27, 18, 15, tzinfo=utc))
    assert not BriefingContextSource.due("US", "post_market", datetime(2026, 11, 27, 20, 0, tzinfo=utc))


@pytest.mark.parametrize("payload", [{}, {"data": {"tickerStream": {"stream": None}}}])
def test_malformed_yahoo_response_is_not_reported_as_no_news(payload):
    request = httpx.Request("POST", "https://finance.yahoo.com/xhr/ncp")
    ticker = SimpleNamespace(_data=SimpleNamespace(post=lambda *a, **kw: httpx.Response(200, request=request, json=payload)))
    with pytest.raises((KeyError, ValueError)):
        yahoo_news(ticker, "AAPL")
    ticker._data.post = lambda *a, **kw: httpx.Response(200, request=request, json={"data": {"tickerStream": {"stream": []}}})
    assert yahoo_news(ticker, "AAPL") == []


def test_yahoo_chart_and_news_failures_remain_visible(monkeypatch):
    import yfinance
    class BrokenTicker:
        def history(self, **kwargs):
            assert kwargs["raise_errors"] is True
            raise RuntimeError("network unavailable")
        _data = SimpleNamespace(post=lambda *a, **kw: httpx.Response(200, request=httpx.Request("POST", "https://finance.yahoo.com"), json={}))
    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: BrokenTicker())
    evidence, statuses = YFinanceEvidenceSource().fetch("005930.KS", preview_fixture()[0])
    assert not evidence
    assert [s.status for s in statuses] == ["failed", "failed"]
