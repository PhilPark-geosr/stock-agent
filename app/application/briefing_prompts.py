from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.briefing_records import PromptActivationRecord, PromptVersionRecord
from app.domain.briefings import BriefingConflict, BriefingError


class PromptPolicy:
    def __init__(self, db, path=None):
        self.db = db
        self.path = Path(path) if path else Path(__file__).resolve().parents[2] / "prompt.md"

    def read_candidate(self):
        try:
            content = self.path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise BriefingError("prompt.md를 UTF-8로 읽을 수 없습니다.") from exc
        if not content or len(content.encode("utf-8")) > 32000:
            raise BriefingError("분석 지침은 비어 있지 않은 32KB 이하 UTF-8 문서여야 합니다.")
        return sha256(content.encode("utf-8")).hexdigest(), content

    def active(self):
        activation = self.db.scalar(select(PromptActivationRecord).order_by(PromptActivationRecord.id.desc()).limit(1))
        if activation is None:
            raise BriefingError("적용된 지침이 없습니다. 운영자가 지침 미리보기와 적용을 먼저 실행해야 합니다.")
        return self.db.get(PromptVersionRecord, activation.version_id)

    def preview(self, analyzer, context, snapshot):
        version, content = self.read_candidate()
        # Successful schema/semantic preview is required before a version can activate.
        result = analyzer.analyze(context, snapshot, content, previous=None, prompt_id=version)
        if self.db.get(PromptVersionRecord, version) is None:
            self.db.add(PromptVersionRecord(id=version, content=content, created_at=datetime.now(timezone.utc)))
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                if self.db.get(PromptVersionRecord, version) is None:
                    raise
        return version, result

    def activate(self, expected_version, *, rollback=False):
        row = self.db.get(PromptVersionRecord, expected_version)
        if row is None:
            raise BriefingError("검증된 지침 버전이 없습니다. 먼저 미리보기를 실행하세요.")
        if not rollback and self.read_candidate()[0] != expected_version:
            raise BriefingConflict("미리보기 이후 지침이 변경됐습니다. 다시 미리보기를 실행하세요.")
        self.db.add(PromptActivationRecord(version_id=expected_version, activated_at=datetime.now(timezone.utc)))
        self.db.commit()
        return row
