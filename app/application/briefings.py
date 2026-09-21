from __future__ import annotations

from app.domain.briefing_records import PromptVersionRecord
from app.domain.briefings import BriefingConflict, BriefingContext, EvidenceSnapshot, LostClaim


class BriefingCoordinator:
    def __init__(self, *, history, context_source, prompts, evidence, analyzer, delivery, clock):
        self.history, self.context_source, self.prompts = history, context_source, prompts
        self.evidence, self.analyzer, self.delivery, self.clock = evidence, analyzer, delivery, clock

    def generate(self, owner, request, *, scheduled_key=None):
        key = scheduled_key or f"manual:{request.request_id}"
        request_data = request.model_dump(mode="json")
        existing = self.history.by_request(owner, key)
        if existing:
            if existing.request_data != request_data:
                raise BriefingConflict("같은 요청 번호에 다른 분석 조건을 사용할 수 없습니다.")
            return existing
        context = self.context_source.build(owner, request, self.clock())
        prompt = self.prompts.active()
        previous = self.history.previous(owner, context)
        if request.original_id:
            self.history.get(owner, request.original_id)
        row, created = self.history.reserve(owner, key, request_data, context, prompt.id,
            previous.id if previous else None, request.original_id)
        if not created:
            if row.request_data != request_data:
                raise BriefingConflict("같은 요청 번호에 다른 분석 조건을 사용할 수 없습니다.")
            return row
        return self.execute(row, row.claim_token)

    def execute(self, row, token):
        run_id, owner = row.id, row.owner_id
        try:
            context = BriefingContext.model_validate(row.context)
            prompt = self.history.db.get(PromptVersionRecord, row.prompt_id)
            previous = self.history.get(owner, row.previous_id) if row.previous_id else None
            snapshot = EvidenceSnapshot.model_validate(row.snapshot) if row.snapshot is not None else self.evidence.build(
                context, heartbeat=lambda: self.history.renew(run_id, token))
            self.history.snapshot(run_id, token, snapshot)
            prev_input = None if previous is None else {"result": previous.result, "context": previous.context,
                "prompt_id": previous.prompt_id, "eligible_symbols": previous.snapshot["eligible_symbols"]}
            self.history.renew(run_id, token)
            result = self.analyzer.analyze(context, snapshot, prompt.content, previous=prev_input, prompt_id=prompt.id)
            status = "completed"
            if not snapshot.eligible_symbols:
                status = "deferred"
            elif len(snapshot.eligible_symbols) != len(context.symbols) or snapshot.excluded or any(
                source.status not in ("ok", "empty") for source in snapshot.sources):
                status = "partial"
            prefix = "[부분 브리핑]" if status == "partial" else "[브리핑]"
            message = f"{prefix} {context.trade_date} {'장전' if context.purpose == 'pre_market' else '장후'}\n"
            message += result.summary[:180] + "\n" + " / ".join(f"{i.symbol} {i.verdict}" for i in result.items)
            message += f"\n기준 {context.cutoff_at.isoformat()}\nStock Agent > 브리핑에서 근거·원문 확인"
            row = self.history.finish(row, token, status=status, result=result.model_dump(mode="json"), message=message[:900])
        except LostClaim:
            self.history.db.rollback()
            return self.history.get(owner, run_id)
        except Exception as exc:
            self.history.db.rollback()
            # Known domain errors are safe; external/DB exceptions may contain credentials.
            from app.domain.briefings import BriefingError
            reason = str(exc)[:1000] if isinstance(exc, BriefingError) else "브리핑 생성 실패: 공급자·모델·저장 설정을 확인하세요."
            try:
                return self.history.finish(self.history.get(owner, run_id), token, status="failed", failure_reason=reason)
            except LostClaim:
                self.history.db.rollback()
                return self.history.get(owner, run_id)
        if status in ("completed", "partial"):
            # An outbox row already exists; transient delivery/DB errors cannot undo the result.
            try:
                self.delivery.deliver(owner, run_id)
            except Exception:
                self.history.db.rollback()
        return self.history.get(owner, run_id)

    def recover(self, row):
        token = self.history.reclaim(row)
        if token is None:
            return row
        row = self.history.get(row.owner_id, row.id)
        if row.snapshot is None:
            return self.history.finish(row, token, status="failed",
                failure_reason="입력 확정 전에 실행이 중단됐습니다. 새 분석을 요청하세요.")
        return self.execute(row, token)
