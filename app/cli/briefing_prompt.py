"""python -m app.cli.briefing_prompt preview|activate HASH|rollback HASH|status"""
import argparse
import difflib
import json
from datetime import date, datetime, timezone

from app.application.briefing_analysis import BriefingAnalyzer
from app.application.briefing_prompts import PromptPolicy
from app.core.database import SessionLocal, init_db
from app.domain.briefing_records import PromptVersionRecord
from app.domain.briefings import BriefingContext, BriefingError, Evidence, EvidenceSnapshot, SourceStatus
from app.integrations.llm.gemini_briefing_model import GeminiBriefingModel


def preview_fixture():
    moment = datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc)
    context = BriefingContext(market="KR", purpose="pre_market", trade_date=date(2026, 9, 2),
        previous_trade_date=date(2026, 9, 1), cutoff_at=moment, started_at=moment, n=1,
        sessions=[date(2026, 9, 1)], symbols=["005930.KS"])
    snapshot = EvidenceSnapshot(eligible_symbols=context.symbols, evidence=[Evidence(
        id="chart:preview", symbol="005930.KS", kind="chart", source="미리보기용 가상 자료",
        published_at=datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc), collected_at=moment,
        text="실제 시장 자료가 아닌 고정 미리보기 예제입니다.",
        data={"candles": [{"date": "2026-09-01", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1000}]})],
        sources=[SourceStatus(symbol="005930.KS", kind="chart", source="미리보기용 가상 자료", status="ok")])
    return context, snapshot


def main():
    parser = argparse.ArgumentParser(description="분석 지침 미리보기·적용·롤백 (카카오 발송 없음)")
    parser.add_argument("command", choices=["preview", "activate", "rollback", "status"])
    parser.add_argument("version", nargs="?")
    parser.add_argument("--file", default="prompt.md")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        policy = PromptPolicy(db, args.file)
        try:
            if args.command == "preview":
                try:
                    before = policy.active().content
                except BriefingError:
                    before = ""
                version, result = policy.preview(BriefingAnalyzer(GeminiBriefingModel()), *preview_fixture())
                content = db.get(PromptVersionRecord, version).content
                difference = "\n".join(difflib.unified_diff(before.splitlines(), content.splitlines(),
                    fromfile="적용 중 지침", tofile="수정안", lineterm=""))
                print(json.dumps({"version": version, "preview": result.model_dump(),
                    "difference": difference,
                    "notice": "가상 자료 미리보기. 외부 알림은 발송하지 않았습니다."}, ensure_ascii=False, indent=2))
            elif args.command == "status":
                row = policy.active()
                try:
                    notice = "수정안 미적용" if policy.read_candidate()[0] != row.id else "파일과 적용 판본이 같습니다."
                except BriefingError as exc:
                    notice = str(exc) + " 저장된 적용 판본을 계속 사용합니다."
                print(json.dumps({"version": row.id, "created_at": str(row.created_at), "notice": notice}, ensure_ascii=False))
            else:
                if not args.version:
                    parser.error("미리보기에서 확인한 지침 버전이 필요합니다.")
                row = policy.activate(args.version, rollback=args.command == "rollback")
                print(f"적용 지침: {row.id}")
        except (BriefingError, RuntimeError) as exc:
            parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
