from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.domain.briefings import EvidenceSnapshot, SourceStatus, utc


class EvidenceBuilder:
    def __init__(self, sources):
        self.sources = sources

    def build(self, context, heartbeat=lambda: None):
        snapshot = EvidenceSnapshot()
        zone = ZoneInfo("Asia/Seoul" if context.market == "KR" else "America/New_York")
        start = utc(datetime.combine(context.sessions[0], time.min, zone))
        seen = set()
        for symbol in context.symbols:
            for source in self.sources:
                try:
                    evidence, statuses = source.fetch(symbol, context)
                except Exception:
                    evidence, statuses = [], [SourceStatus(symbol=symbol, source=type(source).__name__,
                        kind="public", status="failed", detail="자료 수집 실패")]
                snapshot.sources.extend(statuses)
                for item in evidence:
                    if item.symbol != symbol or not (start <= utc(item.published_at) <= context.cutoff_at):
                        snapshot.excluded.append(f"{item.id}: 대상 또는 자료 기준 시각 밖")
                        continue
                    if item.id not in seen:
                        snapshot.evidence.append(item)
                        seen.add(item.id)
                heartbeat()
            current = [e for e in snapshot.evidence if e.symbol == symbol]
            charts = [e for e in current if e.kind == "chart"]
            has_current_chart = any(e.data.get("candles") and e.data["candles"][-1]["date"] == str(context.sessions[-1])
                                    for e in charts)
            eligible = has_current_chart if context.purpose == "post_market" else (
                has_current_chart or any(e.kind != "chart" for e in current))
            if eligible:
                snapshot.eligible_symbols.append(symbol)
            if charts and not has_current_chart:
                snapshot.sources.append(SourceStatus(symbol=symbol, source="일봉 확정 확인", kind="chart",
                    status="delayed", detail="요청한 마지막 거래일의 일봉이 없습니다."))
        # Limit public evidence without altering chart periods. Keep omissions visible.
        charts = [e for e in snapshot.evidence if e.kind == "chart"]
        public = sorted((e for e in snapshot.evidence if e.kind != "chart"), key=lambda e: e.published_at, reverse=True)
        selected = []
        for symbol in context.symbols:
            items = [e for e in public if e.symbol == symbol]
            # A flood of news must not crowd all official disclosures out of the input.
            reserved = [e for kind in ("news", "disclosure") for e in [x for x in items if x.kind == kind][:10]]
            ids = {e.id for e in reserved}
            reserved.extend([e for e in items if e.id not in ids][:20 - len(reserved)])
            selected.extend(reserved)
            ids = {e.id for e in reserved}
            snapshot.excluded.extend(f"{e.id}: 종목별 공개자료 20건 초과" for e in items if e.id not in ids)
        snapshot.evidence = charts + selected
        return snapshot
