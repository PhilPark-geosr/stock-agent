from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_analysis_service
from app.api.web_auth import COOKIE_NAME
from app.application.auth_sessions import SessionService
from app.application.invitations import (
    InvalidInvitation,
    InvitationCodeValidator,
    InvitationIssuer,
    InvitationRedeemer,
)
from app.core.database import Base, get_db
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.models import BetaAccessGrantRecord, InvitationRecord
from app.main import create_app
from app.repositories.auth import SqlAlchemyAuthSessionRepository, SqlAlchemyUserAccountRepository
from app.repositories.invitations import SqlAlchemyInvitationRepository
from app.repositories import AnalysisRepository


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
ORIGIN = "https://service.test"


def _account(db: Session, subject: str) -> UserAccount:
    return SqlAlchemyUserAccountRepository(db).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", subject))
    )


def _issue(db: Session, *, now=NOW):
    return InvitationIssuer(SqlAlchemyInvitationRepository(db), now=lambda: now).issue_invitation()


def test_validator_delegates_validity_to_found_invitation_can_use():
    class FoundInvitation:
        id = "invitation"

        def __init__(self):
            self.checked_at = None

        def can_use(self, now):
            self.checked_at = now
            return False

    found = FoundInvitation()

    class Repository:
        def find_by_code(self, code):
            assert code == "submitted"
            return found

    with pytest.raises(InvalidInvitation):
        InvitationCodeValidator(Repository()).validate("submitted", NOW)
    assert found.checked_at == NOW


def test_redeemer_delegates_code_validation_to_validator():
    invitation = object()

    class Validator:
        def validate(self, code, now):
            assert (code, now) == ("submitted", NOW)
            return invitation

    class Repository:
        def has_beta_access(self, account_id):
            return False

        def redeem(self, found, account_id, used_at):
            assert (found, account_id, used_at) == (invitation, "account", NOW)
            return True

    account = UserAccount("account", LoginIdentity("kakao", "subject"))
    result = InvitationRedeemer(
        Repository(), validator=Validator(), now=lambda: NOW
    ).redeem(account, "submitted")
    assert result.has_beta_access is True


def test_redeem_persists_grant_and_consumes_invitation_together(db_session):
    account = _account(db_session, "member")
    issued = _issue(db_session)

    granted = InvitationRedeemer(SqlAlchemyInvitationRepository(db_session), now=lambda: NOW).redeem(
        account, issued.code
    )

    assert granted.has_beta_access is True
    assert SqlAlchemyInvitationRepository(db_session).find_by_code(issued.code).used_at == NOW
    grant = db_session.get(BetaAccessGrantRecord, account.id)
    assert grant is not None
    assert grant.invitation_id == db_session.scalar(select(InvitationRecord.id))


def test_existing_grant_does_not_consume_or_validate_another_code(db_session):
    account = _account(db_session, "member")
    first = _issue(db_session)
    second = _issue(db_session)
    redeemer = InvitationRedeemer(SqlAlchemyInvitationRepository(db_session), now=lambda: NOW)
    granted = redeemer.redeem(account, first.code)

    repeated = redeemer.redeem(granted, "not-even-a-real-code")

    assert repeated.has_beta_access is True
    assert SqlAlchemyInvitationRepository(db_session).find_by_code(second.code).used_at is None


def test_grant_failure_rolls_back_invitation_consumption(db_session, monkeypatch):
    account = _account(db_session, "member")
    issued = _issue(db_session)
    repository = SqlAlchemyInvitationRepository(db_session)

    def fail_grant(*args, **kwargs):
        raise RuntimeError("grant storage unavailable")

    monkeypatch.setattr(repository, "_add_grant", fail_grant)
    with pytest.raises(RuntimeError, match="grant storage unavailable"):
        InvitationRedeemer(repository, now=lambda: NOW).redeem(account, issued.code)

    assert SqlAlchemyInvitationRepository(db_session).find_by_code(issued.code).used_at is None
    assert db_session.get(BetaAccessGrantRecord, account.id) is None


def test_one_invitation_cannot_grant_two_accounts_concurrently(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'concurrency.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as setup:
        first = _account(setup, "first")
        second = _account(setup, "second")
        code = _issue(setup).code

    barrier = Barrier(2)

    def redeem(account):
        with sessions() as db:
            repository = SqlAlchemyInvitationRepository(db)
            original = repository.find_by_code

            def synchronized_find(value):
                invitation = original(value)
                barrier.wait(timeout=5)
                return invitation

            repository.find_by_code = synchronized_find
            try:
                InvitationRedeemer(repository, now=lambda: NOW).redeem(account, code)
                return "granted"
            except InvalidInvitation:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(redeem, (first, second)))

    assert sorted(outcomes) == ["granted", "rejected"]
    with sessions() as db:
        assert len(db.scalars(select(BetaAccessGrantRecord)).all()) == 1
        assert _utc(db.scalar(select(InvitationRecord)).used_at) == NOW
    engine.dispose()


def test_same_account_concurrent_codes_consume_only_one_invitation(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'same-account.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as setup:
        account = _account(setup, "member")
        codes = (_issue(setup).code, _issue(setup).code)
    barrier = Barrier(2)

    def redeem(code):
        with sessions() as db:
            repository = SqlAlchemyInvitationRepository(db)
            original = repository.find_by_code

            def synchronized_find(value):
                invitation = original(value)
                barrier.wait(timeout=5)
                return invitation

            repository.find_by_code = synchronized_find
            return InvitationRedeemer(repository, now=lambda: NOW).redeem(account, code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, codes))

    assert all(result.has_beta_access for result in results)
    with sessions() as db:
        invitations = db.scalars(select(InvitationRecord)).all()
        assert sum(row.used_at is not None for row in invitations) == 1
        assert len(db.scalars(select(BetaAccessGrantRecord)).all()) == 1
    engine.dispose()


@pytest.fixture
def beta_web_client(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_ORIGIN", ORIGIN)
    monkeypatch.setenv("WEB_COOKIE_SECURE", "false")
    (tmp_path / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    app = create_app(web_dist=tmp_path)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url=ORIGIN) as client:
        # Startup configuration reloads .env; keep this client's origin isolated.
        monkeypatch.setenv("WEB_ORIGIN", ORIGIN)
        yield client


def _login(client, db, account):
    token = SessionService(SqlAlchemyAuthSessionRepository(db)).issue(account).token
    client.cookies.set(COOKIE_NAME, token)


def test_web_redeem_contract_and_invalid_code(beta_web_client, db_session):
    account = _account(db_session, "member")
    issued = _issue(db_session, now=datetime.now(timezone.utc))
    _login(beta_web_client, db_session, account)

    invalid = beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": "wrong"}, headers={"Origin": ORIGIN}
    )
    assert invalid.status_code == 400
    redeemed = beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": issued.code}, headers={"Origin": ORIGIN}
    )
    assert redeemed.status_code == 200
    assert redeemed.headers["cache-control"] == "no-store"
    assert redeemed.json() == {
        "id": account.id,
        "login_provider": "kakao",
        "is_operator": False,
        "has_beta_access": True,
    }
    assert beta_web_client.get("/auth/web/session").json()["has_beta_access"] is True


def test_web_redeem_requires_login_and_trusted_origin(beta_web_client, db_session):
    issued = _issue(db_session, now=datetime.now(timezone.utc))
    assert beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": issued.code}, headers={"Origin": ORIGIN}
    ).status_code == 401
    account = _account(db_session, "member")
    _login(beta_web_client, db_session, account)
    assert beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": issued.code}, headers={"Origin": "https://evil.test"}
    ).status_code == 403
    assert SqlAlchemyInvitationRepository(db_session).find_by_code(issued.code).used_at is None


def test_web_redeem_rejects_expired_and_used_codes(beta_web_client, db_session):
    account = _account(db_session, "member")
    _login(beta_web_client, db_session, account)
    expired = _issue(db_session, now=datetime.now(timezone.utc) - timedelta(days=8))
    assert beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": expired.code}, headers={"Origin": ORIGIN}
    ).status_code == 400

    used = _issue(db_session, now=datetime.now(timezone.utc))
    other = _account(db_session, "other")
    InvitationRedeemer(SqlAlchemyInvitationRepository(db_session)).redeem(other, used.code)
    assert beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": used.code}, headers={"Origin": ORIGIN}
    ).status_code == 400


def test_web_redeem_storage_failure_is_sanitized_and_rolls_back(
    beta_web_client, db_session, monkeypatch
):
    account = _account(db_session, "member")
    issued = _issue(db_session, now=datetime.now(timezone.utc))
    _login(beta_web_client, db_session, account)

    def fail_grant(self, *args, **kwargs):
        raise RuntimeError("private database details")

    monkeypatch.setattr(SqlAlchemyInvitationRepository, "_add_grant", fail_grant)
    response = beta_web_client.post(
        "/auth/web/invitations/redeem",
        json={"code": issued.code},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Invitation could not be redeemed"}
    assert issued.code not in response.text
    assert "private database" not in response.text
    assert SqlAlchemyInvitationRepository(db_session).find_by_code(issued.code).used_at is None


def test_service_routes_accept_cookie_but_require_beta_and_origin_on_mutation(
    beta_web_client, db_session
):
    class NeverLatest:
        calls = 0

        def get_latest_analysis(self, symbol):
            self.calls += 1
            raise AssertionError("untrusted cookie GET must not start analysis")

    account = _account(db_session, "member")
    _login(beta_web_client, db_session, account)
    assert beta_web_client.get("/watchlist").status_code == 403
    issued = _issue(db_session, now=datetime.now(timezone.utc))
    beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": issued.code}, headers={"Origin": ORIGIN}
    )

    assert beta_web_client.get("/watchlist").status_code == 200
    assert beta_web_client.post("/watchlist", json={"symbol": "AAPL"}).status_code == 403
    assert beta_web_client.post(
        "/watchlist", json={"symbol": "AAPL"}, headers={"Origin": ORIGIN}
    ).status_code == 201
    service = NeverLatest()
    beta_web_client.app.dependency_overrides[get_analysis_service] = lambda: service
    assert beta_web_client.get("/stocks/AAPL/analysis/latest").status_code == 403
    assert beta_web_client.get(
        "/stocks/AAPL/analysis/latest", headers={"Origin": "https://evil.test"}
    ).status_code == 403
    assert service.calls == 0


def test_invite_and_app_navigation_follow_session_and_beta_state(beta_web_client, db_session):
    assert beta_web_client.get("/invite", follow_redirects=False).headers["location"] == "/login"
    assert beta_web_client.get("/app", follow_redirects=False).headers["location"] == "/login"
    account = _account(db_session, "member")
    _login(beta_web_client, db_session, account)
    assert beta_web_client.get("/invite", follow_redirects=False).status_code == 200
    assert beta_web_client.get("/app", follow_redirects=False).headers["location"] == "/invite"
    issued = _issue(db_session, now=datetime.now(timezone.utc))
    beta_web_client.post(
        "/auth/web/invitations/redeem", json={"code": issued.code}, headers={"Origin": ORIGIN}
    )
    assert beta_web_client.get("/invite", follow_redirects=False).headers["location"] == "/app"
    assert beta_web_client.get("/app", follow_redirects=False).status_code == 200


def test_bearer_service_reads_require_grant_and_preserve_subscription_ownership(
    beta_web_client, db_session
):
    class ReadService:
        def __init__(self, db):
            self.repository = AnalysisRepository(db)

        def list_analysis_history(self, symbol, *, limit=20, offset=0):
            return self.repository.list_by_symbol(symbol, limit=limit, offset=offset)

        def get_analysis_by_id(self, symbol, result_id):
            result = self.repository.get_by_id(symbol, result_id)
            if result is None:
                raise LookupError("analysis result not found")
            return result

        def get_latest_analysis(self, symbol):
            result = self.repository.get_latest(symbol)
            if result is None:
                raise AssertionError("test expected a stored result")
            return result

    beta_web_client.app.dependency_overrides[get_analysis_service] = lambda: ReadService(db_session)
    account = _account(db_session, "bearer-member")
    token = SessionService(SqlAlchemyAuthSessionRepository(db_session)).issue(account).token
    headers = {"Authorization": f"Bearer {token}"}
    assert beta_web_client.get("/watchlist", headers=headers).status_code == 403

    issued = _issue(db_session, now=datetime.now(timezone.utc))
    InvitationRedeemer(SqlAlchemyInvitationRepository(db_session)).redeem(account, issued.code)
    assert beta_web_client.post(
        "/watchlist", json={"symbol": "AAPL"}, headers=headers
    ).status_code == 201
    stored = AnalysisRepository(db_session).save(
        symbol="AAPL", overall_judgment="neutral", summary="stored common analysis"
    )
    history = beta_web_client.get("/stocks/AAPL/analysis", headers=headers)
    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [stored.id]
    detail = beta_web_client.get(f"/stocks/AAPL/analysis/{stored.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["summary"] == "stored common analysis"
    assert beta_web_client.get(
        "/stocks/AAPL/analysis/latest", headers=headers
    ).status_code == 200

    stranger = _account(db_session, "bearer-stranger")
    stranger_code = _issue(db_session, now=datetime.now(timezone.utc))
    InvitationRedeemer(SqlAlchemyInvitationRepository(db_session)).redeem(stranger, stranger_code.code)
    stranger_token = SessionService(SqlAlchemyAuthSessionRepository(db_session)).issue(stranger).token
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}
    assert beta_web_client.get("/stocks/AAPL/analysis", headers=stranger_headers).status_code == 404
    assert beta_web_client.get(
        f"/stocks/AAPL/analysis/{stored.id}", headers=stranger_headers
    ).status_code == 404


def test_scheduler_endpoint_requires_operator(beta_web_client, db_session, monkeypatch):
    account = _account(db_session, "ordinary-member")
    token = SessionService(SqlAlchemyAuthSessionRepository(db_session)).issue(account).token
    headers = {"Authorization": f"Bearer {token}"}

    assert beta_web_client.post("/scheduler/run?force=true").status_code == 401
    assert beta_web_client.post(
        "/scheduler/run?force=true", headers=headers
    ).status_code == 403

    monkeypatch.setenv("ADMIN_ACCOUNT_ID", account.id)
    beta_web_client.cookies.set(COOKIE_NAME, token)
    assert beta_web_client.post("/scheduler/run?force=true").status_code == 403
