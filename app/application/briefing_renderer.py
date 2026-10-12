from __future__ import annotations

from typing import Sequence

from app.domain.models import BriefingFailure, BriefingItem, InvestmentBriefing
from app.interfaces.briefings import BriefingRenderer


JUDGMENT_LABELS = {
    "STRONG_BUY": "적극 매수",
    "BUY": "매수",
    "HOLD": "관망",
    "SELL": "매도",
    "STRONG_SELL": "적극 매도",
    "UNKNOWN": "판단 불가",
}


class KoreanBriefingRenderer(BriefingRenderer):
    def render(
        self,
        briefing: InvestmentBriefing,
        items: Sequence[BriefingItem],
        failures: Sequence[BriefingFailure],
    ) -> str:
        type_label = "장 시작 전 브리핑" if briefing.briefing_type == "PRE_MARKET" else "장 마감 후 요약"
        lines = [
            f"[{type_label}] {briefing.exchange} · {briefing.trading_date.isoformat()}",
            briefing.summary,
        ]
        for item in items:
            marker = "[판단 변경] " if item.judgment_changed else ""
            current = JUDGMENT_LABELS.get(item.current_judgment, item.current_judgment)
            if item.comparison_status == "COMPARABLE" and item.previous_judgment:
                previous = JUDGMENT_LABELS.get(item.previous_judgment, item.previous_judgment)
                judgment_line = f"{previous} → {current}" if item.judgment_changed else f"{current} 유지"
            else:
                judgment_line = f"현재 판단: {current} (비교 기준 없음)"
            lines.extend(["", f"{marker}{item.symbol}", judgment_line, item.summary])
            if item.change_reason:
                lines.append(f"변경 이유: {item.change_reason}")

        if failures:
            lines.extend(["", f"분석 실패 {len(failures)}개"])
            lines.extend(f"- {failure.symbol}: {failure.message}" for failure in failures)
        return "\n".join(lines)
