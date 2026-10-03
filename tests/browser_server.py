"""Isolated browser-test server. Never imported by the production application."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# `load_environment` normally uses override=True. Replace it before importing
# any module that can call it, so the developer's .env cannot replace this
# server's isolated settings.
from app.core import settings

settings.load_environment = lambda: None
database_path = Path(os.environ["STOCK_AGENT_E2E_DATABASE"]).resolve()
temporary_root = Path(tempfile.gettempdir()).resolve()
if database_path.parent.parent != temporary_root or not database_path.parent.name.startswith("stock-agent-e2e-"):
    raise RuntimeError("browser test database must be in its own temporary stock-agent-e2e directory")
os.environ.update(
    DATABASE_URL=f"sqlite:///{database_path.as_posix()}",
    SCHEDULER_ENABLED="false",
    ADMIN_ACCOUNT_ID="browser-test-operator",
    WEB_ORIGIN="http://127.0.0.1:8765",
    WEB_COOKIE_SECURE="false",
    KAKAO_REDIRECT_URI="http://127.0.0.1:8765/auth/kakao/callback",
)

from fastapi import Depends, Request
from sqlalchemy.orm import Session
import uvicorn

from app.api.deps import get_analysis_service, get_authorization_url, get_login_service
from app.application.login import LoginService
from app.core.database import SessionLocal, get_db, init_db
from app.domain.auth import ExternalLoginCredential, LoginIdentity, UserAccount
from app.domain.models import AnalysisResult
from app.main import create_app
from app.repositories.auth import SqlAlchemyUserAccountRepository
from app.repositories.repositories import AnalysisRepository


TEST_IDENTITIES = {
    "operator": ("browser-test-code-operator", "browser-test-subject", "browser-test-operator"),
    "member": ("browser-test-code-member", "browser-test-member-subject", "browser-test-member"),
    "second-member": (
        "browser-test-code-second-member",
        "browser-test-second-member-subject",
        "browser-test-second-member",
    ),
    "unregistered-member": (
        "browser-test-code-unregistered-member",
        "browser-test-unregistered-member-subject",
        "browser-test-unregistered-member",
    ),
}


class BrowserTestExternalLogin:
    def login(self, credential: ExternalLoginCredential) -> LoginIdentity:
        for code, subject, _account_id in TEST_IDENTITIES.values():
            if credential.authorization_code == code:
                return LoginIdentity("kakao", subject)
        raise ValueError("unexpected browser test credential")


class BrowserTestAnalysisService:
    """Read seeded analysis only; browser tests must never invoke live analysis."""

    def __init__(self, db: Session) -> None:
        self.repository = AnalysisRepository(db)

    def list_analysis_history(self, symbol: str, *, limit: int, offset: int):
        return self.repository.list_by_symbol(symbol, limit=limit, offset=offset)

    def get_analysis_by_id(self, symbol: str, result_id: int):
        result = self.repository.get_by_id(symbol, result_id)
        if result is None:
            raise LookupError("analysis result not found")
        return result

    def get_latest_analysis(self, symbol: str):
        result = self.repository.get_latest(symbol)
        if result is None:
            raise LookupError("analysis result not found")
        return result


def fake_login_service(db: Session = Depends(get_db)) -> LoginService:
    return LoginService(BrowserTestExternalLogin(), SqlAlchemyUserAccountRepository(db))


def fake_analysis_service(db: Session = Depends(get_db)) -> BrowserTestAnalysisService:
    return BrowserTestAnalysisService(db)


def fake_authorization_url(request: Request):
    identity = request.cookies.get("stock_agent_e2e_login_as", "operator")
    code = TEST_IDENTITIES.get(identity, TEST_IDENTITIES["operator"])[0]
    return lambda state: "/auth/kakao/callback?" + urlencode(
        {"code": code, "state": state}
    )


if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        accounts = SqlAlchemyUserAccountRepository(db)
        for _code, subject, account_id in TEST_IDENTITIES.values():
            accounts.save_or_get_existing(
                UserAccount(account_id, LoginIdentity("kakao", subject))
            )
        db.add_all([
            AnalysisResult(
                symbol="AAPL.KS",
                analyzed_at=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc),
                data_timestamp=datetime(2026, 9, 27, 11, 55, tzinfo=timezone.utc),
                overall_judgment="관망",
                summary="브라우저 테스트용 최근 공용 분석입니다.",
                key_reasons=["현금 흐름이 안정적입니다.", "단기 변동성이 높습니다."],
                risk_factors=["시장 변동성"],
                support_levels={"latest_close": 230, "change_percent": 1.5, "volume_ratio_20": 1.2, "low_20": 220, "high_20": 240},
                should_alert=False,
                triggered_alerts=[],
                alert_reason=None,
                raw_result=None,
                shared_safe=True,
            ),
            AnalysisResult(
                symbol="AAPL.KS",
                analyzed_at=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
                data_timestamp=datetime(2026, 9, 26, 11, 55, tzinfo=timezone.utc),
                overall_judgment="매수 관심",
                summary="브라우저 테스트용 이전 공용 분석입니다.",
                key_reasons=["지지선 부근입니다."],
                risk_factors=["거래량 둔화"],
                support_levels={"support": 220, "resistance": 238},
                should_alert=True,
                triggered_alerts=["가격 지지선 접근"],
                alert_reason="관심 가격대에 진입했습니다.",
                raw_result=None,
                shared_safe=True,
            ),
        ])
        db.commit()
    app = create_app()
    app.dependency_overrides[get_login_service] = fake_login_service
    app.dependency_overrides[get_authorization_url] = fake_authorization_url
    app.dependency_overrides[get_analysis_service] = fake_analysis_service
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
