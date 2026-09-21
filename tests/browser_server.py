"""Isolated browser-test server. Never imported by the production application."""

from __future__ import annotations

import os
import sys
import tempfile
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

from fastapi import Depends
from sqlalchemy.orm import Session
import uvicorn

from app.api.deps import get_authorization_url, get_login_service
from app.application.login import LoginService
from app.core.database import SessionLocal, get_db, init_db
from app.domain.auth import ExternalLoginCredential, LoginIdentity, UserAccount
from app.main import create_app
from app.repositories.auth import SqlAlchemyUserAccountRepository


class BrowserTestExternalLogin:
    def login(self, credential: ExternalLoginCredential) -> LoginIdentity:
        if credential.authorization_code != "browser-test-code":
            raise ValueError("unexpected browser test credential")
        return LoginIdentity("kakao", "browser-test-subject")


def fake_login_service(db: Session = Depends(get_db)) -> LoginService:
    return LoginService(BrowserTestExternalLogin(), SqlAlchemyUserAccountRepository(db))


def fake_authorization_url():
    return lambda state: "/auth/kakao/callback?" + urlencode(
        {"code": "browser-test-code", "state": state}
    )


if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        SqlAlchemyUserAccountRepository(db).save_or_get_existing(
            UserAccount("browser-test-operator", LoginIdentity("kakao", "browser-test-subject"))
        )
        SqlAlchemyUserAccountRepository(db).save_or_get_existing(
            UserAccount("browser-test-member", LoginIdentity("kakao", "browser-test-member-subject"))
        )
    app = create_app()
    app.dependency_overrides[get_login_service] = fake_login_service
    app.dependency_overrides[get_authorization_url] = fake_authorization_url
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
