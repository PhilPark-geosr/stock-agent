import json

from pydantic import ValidationError

from app.domain.briefings import BriefingError, BriefingItem, BriefingResult, ModelOutputError


class BriefingAnalyzer:
    def __init__(self, model):
        self.model = model

    def analyze(self, context, snapshot, prompt, *, previous, prompt_id):
        eligible = snapshot.eligible_symbols
        if not eligible:
            return BriefingResult(summary="판단 가능한 최신 근거가 없어 브리핑을 보류합니다.",
                items=[self.unavailable(symbol) for symbol in context.symbols])
        previous_result = previous["result"] if previous else None
        payload = {"context": context.model_dump(mode="json"), "analyze_symbols": eligible,
            "evidence": snapshot.model_dump(mode="json"), "previous": previous_result,
            "previous_context": previous["context"] if previous else None}
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 600000:
            raise BriefingError("입력 용량 600KB 초과: 차트 기간을 임의로 줄이지 않았습니다.")
        errors = None
        for attempt in range(2):
            try:
                raw = self.model.generate(prompt=prompt, payload=payload, validation_errors=errors)
                result = BriefingResult.model_validate(raw)
                if not result.summary.strip():
                    raise ValueError("전체 요약이 비어 있습니다.")
                if sorted(i.symbol for i in result.items) != sorted(eligible):
                    raise ValueError("분석 결과는 요청한 분석 가능 종목을 각각 한 번씩 포함해야 합니다.")
                facts = {e.id: e for e in snapshot.evidence}
                for item in result.items:
                    if not item.evidence_ids or any(k not in facts or facts[k].symbol != item.symbol for k in item.evidence_ids):
                        raise ValueError("종목별 근거는 제공된 해당 종목의 근거를 참조해야 합니다.")
                break
            except (ValidationError, ValueError, ModelOutputError) as exc:
                errors = [str(exc)[:1500]]
                if attempt:
                    raise ModelOutputError("브리핑 출력 검증에 두 번 실패했습니다.") from exc
        old_items = {i["symbol"]: i for i in (previous_result or {}).get("items", [])}
        old_eligible = set((previous or {}).get("eligible_symbols", []))
        changed_basis = previous and (previous["prompt_id"] != prompt_id or previous["context"]["n"] != context.n)
        for item in result.items:
            old = old_items.get(item.symbol)
            if old is None or item.symbol not in old_eligible:
                item.comparison = "비교 불가"
                item.comparison_reason = "이전의 비교 가능한 종목 판단이 없습니다."
            else:
                item.comparison = "유지" if item.verdict == old["verdict"] else "변경"
                item.comparison_reason = f"{previous['context']['trade_date']} 브리핑 대비 {item.comparison}. " + item.comparison_reason
            if changed_basis:
                item.limitations.append("분석 지침 또는 관찰기간이 달라졌습니다. 판단 차이를 시장 변화로만 해석하지 마세요.")
            if context.purpose == "post_market" and (not previous or previous["context"]["trade_date"] != str(context.trade_date)
                                                      or previous["context"]["purpose"] != "pre_market"):
                item.limitations.append("오늘 장전 브리핑이 없어 당일 아침 전망과 비교할 수 없습니다.")
            for source in snapshot.sources:
                if source.symbol == item.symbol and source.status not in ("ok", "empty"):
                    item.limitations.append(f"{source.source}: {source.detail or source.status}")
        by_symbol = {i.symbol: i for i in result.items}
        result.items = [by_symbol.get(s) or self.unavailable(s) for s in context.symbols]
        return result

    @staticmethod
    def unavailable(symbol):
        return BriefingItem(symbol=symbol, verdict="보류", reason="판단에 필요한 최신 자료가 부족합니다.",
            evidence_ids=[], comparison="비교 불가", comparison_reason="현재 판단 근거가 부족합니다.",
            limitations=["필수 자료 부족 또는 마감 자료 지연"], next_observation="자료가 확인된 뒤 다시 분석하세요.")
