from datetime import datetime, timezone

from app.api.deps import get_current_account
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.models import AnalysisResult
from app.repositories import AnalysisRepository
from app.repositories.auth import SqlAlchemyUserAccountRepository


def test_active_subscription_is_required_to_read_or_run_analysis(
    client, db_session, market_data
):
    stranger = SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", "stranger"))
    )
    client.app.dependency_overrides[get_current_account] = lambda: stranger

    assert client.get("/stocks/005930.KS/analysis/latest").status_code == 404
    assert client.get("/stocks/005930.KS/analysis").status_code == 404
    assert client.post("/stocks/005930.KS/analysis").status_code == 404
    assert market_data.calls == []


def test_legacy_unsafe_analysis_is_not_returned(db_session):
    legacy = AnalysisResult(
        symbol="AAPL",
        analyzed_at=datetime.now(timezone.utc),
        overall_judgment="neutral",
        summary="possibly user-specific legacy result",
        key_reasons=[],
        risk_factors=[],
        support_levels={},
        should_alert=False,
        triggered_alerts=[],
        shared_safe=False,
    )
    db_session.add(legacy)
    db_session.commit()

    assert AnalysisRepository(db_session).get_latest("AAPL") is None


def test_new_analysis_is_explicitly_shared_safe(db_session):
    stored = AnalysisRepository(db_session).save(
        symbol="AAPL",
        overall_judgment="neutral",
        summary="system conditions only",
    )

    assert stored.shared_safe is True
