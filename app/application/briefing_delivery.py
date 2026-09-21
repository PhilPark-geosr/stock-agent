from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import update

from app.domain.briefing_records import BriefingDeliveryRecord
from app.domain.briefings import BriefingConflict, utc
from app.integrations.kakao_notify import KakaoNotifyError


class BriefingDelivery:
    def __init__(self, history, connections, sender, clock):
        self.history, self.connections, self.sender, self.clock = history, connections, sender, clock
        self.db = history.db

    def deliver(self, owner, run_id, *, retry_id=None, acknowledge_unknown=False):
        run = self.history.get(owner, run_id)
        row = self.history.delivery(run_id)
        if row is None or run.status not in ("completed", "partial"):
            return row
        now = self.clock()
        if row.status == "sending" and utc(row.lease_until) <= now:
            expired_attempts = [dict(a) for a in row.attempts]
            if expired_attempts:
                expired_attempts[-1].update(status="unknown", finished_at=now.isoformat())
            self.db.execute(update(BriefingDeliveryRecord).where(
                BriefingDeliveryRecord.id == row.id, BriefingDeliveryRecord.status == "sending",
                BriefingDeliveryRecord.lease_until <= now).values(status="unknown", claim_token=None,
                    lease_until=None, attempts=expired_attempts,
                    reason="전송 도중 실행이 중단돼 카카오 접수 여부를 확인할 수 없습니다.", updated_at=now),
                execution_options={"synchronize_session": False})
            self.db.commit()
            self.db.expire_all()
            row = self.history.delivery(run_id)
        attempt_key = retry_id or "initial"
        if row.status in ("sent", "sending") or any(a["request_id"] == attempt_key for a in row.attempts):
            return row
        if not retry_id and row.status != "pending":
            return row
        if row.status == "unknown" and not acknowledge_unknown:
            raise BriefingConflict("이전 전송 결과를 알 수 없습니다. 중복 도착 가능성을 확인한 후 재전달하세요.")
        token = str(uuid4())
        attempts = [*row.attempts, {"request_id": attempt_key, "started_at": now.isoformat(), "status": "sending"}]
        count = self.db.execute(update(BriefingDeliveryRecord).where(
            BriefingDeliveryRecord.id == row.id, BriefingDeliveryRecord.status == row.status,
            BriefingDeliveryRecord.revision == row.revision,
            BriefingDeliveryRecord.status != "sending",
        ).values(status="sending", claim_token=token, lease_until=now + timedelta(minutes=5),
            attempts=attempts, revision=row.revision + 1, updated_at=now), execution_options={"synchronize_session": False}).rowcount
        self.db.commit()
        if count != 1:
            self.db.expire_all()
            return self.history.delivery(run_id)
        self.db.expire_all()
        status, reason, connection_id = "unknown", "전송 결과 확인 불가", None
        try:
            if not self.history.settings(owner, run.market).kakao_enabled:
                status, reason = "cancelled", "카카오 브리핑 수신이 꺼져 있습니다."
            else:
                connection = self.connections.get_active(owner_id=owner, channel="kakao")
                if connection is None:
                    status, reason = "not_connected", "카카오 수신 연결이 없습니다."
                elif self.sender is None:
                    status, reason = "failed", "카카오 발송 설정이 준비되지 않았습니다."
                else:
                    connection_id = connection.id
                    # Fresh connection/settings immediately before the external side effect.
                    self.db.expire_all()
                    active = self.connections.get_active(owner_id=owner, channel="kakao")
                    if not self.history.settings(owner, run.market).kakao_enabled or active is None or active.id != connection_id:
                        status, reason = "cancelled", "발송 직전 수신 설정 또는 연결이 변경됐습니다."
                    else:
                        message = row.message
                        self.db.rollback()  # Release read transaction before remote I/O.
                        self.sender.send(connection=active, message=message)
                        status, reason = "sent", None
        except (KakaoNotifyError, httpx.ConnectError, httpx.ConnectTimeout):
            status, reason = "failed", "카카오 발송에 실패했습니다. 연결 상태를 확인하세요."
        except Exception:
            status, reason = "unknown", "카카오 접수 여부를 확인할 수 없습니다. 자동으로 다시 보내지 않습니다."
        attempts[-1].update(status=status, finished_at=self.clock().isoformat())
        self.db.execute(update(BriefingDeliveryRecord).where(
            BriefingDeliveryRecord.id == row.id, BriefingDeliveryRecord.status == "sending",
            BriefingDeliveryRecord.claim_token == token,
        ).values(status=status, reason=reason, connection_id=connection_id, attempts=attempts,
            claim_token=None, lease_until=None, updated_at=self.clock()),
            execution_options={"synchronize_session": False})
        self.db.commit()
        self.db.expire_all()
        return self.history.delivery(run_id)
