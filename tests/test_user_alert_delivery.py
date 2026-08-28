from __future__ import annotations

from cryptography.fernet import Fernet

from app.application.user_alerts import UserAlertDispatcher
from app.application.user_alert_evaluator import AlertEvaluationDecision
from app.domain.alert_conditions import RuleValidationResult
from app.domain.auth import LoginIdentity, UserAccount
from app.domain.notifications import NotificationCredentials
from app.domain.symbols import StockSymbol
from app.repositories.auth import SqlAlchemyUserAccountRepository
from app.repositories.notifications import (
    SqlAlchemyAlertEvaluationRepository,
    SqlAlchemyNotificationConnectionRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyUserAlertEvaluationTargetQuery,
)
from app.repositories.repositories import AlertConditionRepository, AnalysisRepository, WatchlistRepository


class FixedEvaluator:
    def __init__(self, decision: AlertEvaluationDecision) -> None:
        self.decision = decision
        self.calls = []

    def evaluate(self, *, analysis, condition) -> AlertEvaluationDecision:
        self.calls.append((analysis, condition))
        return self.decision


class RecordingSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages = []
        self.error = error

    def send(self, *, connection, message: str) -> None:
        self.messages.append((connection, message))
        if self.error:
            raise self.error


def _scenario(db_session):
    owner = SqlAlchemyUserAccountRepository(db_session).save_or_get_existing(
        UserAccount.register(LoginIdentity("kakao", "custom-alert-owner"))
    )
    subscription = WatchlistRepository(db_session).add(owner.id, StockSymbol.of("005930.KS"))
    condition = AlertConditionRepository(db_session).save_validated(
        owner_id=owner.id,
        symbol="005930.KS",
        user_rule="5% 이상 상승하면 알려줘",
        validation=RuleValidationResult(
            is_valid=True,
            normalized_name="5% rise",
            normalized_rule="Alert when the price rises by at least 5 percent.",
            target_symbol="005930.KS",
            validation_summary="measurable",
        ),
    )
    analysis = AnalysisRepository(db_session).save(
        symbol="005930.KS",
        overall_judgment="상승",
        summary="주가가 6.2% 상승했습니다.",
        support_levels={"change_percent": 6.2},
    )
    connections = SqlAlchemyNotificationConnectionRepository(db_session, Fernet(Fernet.generate_key()))
    connection = connections.create(
        owner_id=owner.id,
        channel="kakao",
        credentials=NotificationCredentials(
            access_token="token",
            refresh_token=None,
            access_token_expires_at=None,
        ),
    )
    return owner, subscription, condition, analysis, connections, connection


def test_matched_user_condition_is_recorded_and_sent_to_its_owner(db_session):
    owner, _, condition, analysis, connections, connection = _scenario(db_session)
    evaluator = FixedEvaluator(
        AlertEvaluationDecision(
            outcome="matched",
            reason="6.2% 상승해 5% 기준을 넘었습니다.",
            notification_message="삼성전자가 5% 상승 조건을 충족했습니다.",
            evidence=["analysis.support_levels.change_percent=6.2"],
        )
    )
    sender = RecordingSender()
    evaluations = SqlAlchemyAlertEvaluationRepository(db_session)
    deliveries = SqlAlchemyNotificationDeliveryRepository(db_session)
    dispatcher = UserAlertDispatcher(
        target_query=SqlAlchemyUserAlertEvaluationTargetQuery(db_session),
        evaluation_repository=evaluations,
        evaluator=evaluator,
        connection_repository=connections,
        delivery_repository=deliveries,
        sender=sender,
    )

    result = dispatcher.dispatch(analysis)

    stored = evaluations.get_for_analysis_and_condition(analysis.id, condition.id)
    assert result.evaluated == 1
    assert result.sent == 1
    assert stored.status == "completed"
    assert stored.matched is True
    assert stored.reason == "6.2% 상승해 5% 기준을 넘었습니다."
    assert sender.messages == [(connection, "삼성전자가 5% 상승 조건을 충족했습니다.")]
    assert deliveries.list_for_analysis(analysis.id)[0].evaluation_id == stored.id
    assert evaluator.calls[0][1].id == f"custom.{condition.id}"


def _dispatcher(db_session, *, evaluator, connections, sender):
    return UserAlertDispatcher(
        target_query=SqlAlchemyUserAlertEvaluationTargetQuery(db_session),
        evaluation_repository=SqlAlchemyAlertEvaluationRepository(db_session),
        evaluator=evaluator,
        connection_repository=connections,
        delivery_repository=SqlAlchemyNotificationDeliveryRepository(db_session),
        sender=sender,
    )


def test_not_matched_and_indeterminate_conditions_are_not_sent(db_session):
    _, _, condition, analysis, connections, _ = _scenario(db_session)
    sender = RecordingSender()
    evaluations = SqlAlchemyAlertEvaluationRepository(db_session)

    not_matched = _dispatcher(
        db_session,
        evaluator=FixedEvaluator(
            AlertEvaluationDecision(outcome="not_matched", reason="기준 미달")
        ),
        connections=connections,
        sender=sender,
    ).dispatch(analysis)

    assert not_matched.evaluated == 1
    assert not_matched.sent == 0
    assert evaluations.get_for_analysis_and_condition(analysis.id, condition.id).matched is False

    second_analysis = AnalysisRepository(db_session).save(
        symbol="005930.KS", overall_judgment="관망", summary="자료 부족"
    )
    indeterminate = _dispatcher(
        db_session,
        evaluator=FixedEvaluator(
            AlertEvaluationDecision(outcome="indeterminate", reason="자료 부족")
        ),
        connections=connections,
        sender=sender,
    ).dispatch(second_analysis)

    failed = evaluations.get_for_analysis_and_condition(second_analysis.id, condition.id)
    assert indeterminate.failed == 1
    assert failed.status == "failed"
    assert failed.matched is None
    assert sender.messages == []


def test_same_analysis_and_condition_is_evaluated_and_delivered_only_once(db_session):
    _, _, _, analysis, connections, _ = _scenario(db_session)
    evaluator = FixedEvaluator(
        AlertEvaluationDecision(
            outcome="matched", reason="충족", notification_message="조건 충족"
        )
    )
    sender = RecordingSender()
    dispatcher = _dispatcher(
        db_session, evaluator=evaluator, connections=connections, sender=sender
    )

    first = dispatcher.dispatch(analysis)
    duplicate = dispatcher.dispatch(analysis)

    assert first.sent == 1
    assert duplicate.skipped_duplicate == 1
    assert len(evaluator.calls) == 1
    assert len(sender.messages) == 1


def test_matched_evaluation_is_kept_when_delivery_is_unavailable(db_session):
    _, _, condition, analysis, connections, _ = _scenario(db_session)
    active = connections.get_active(
        owner_id=SqlAlchemyUserAlertEvaluationTargetQuery(db_session).list_active_for_symbol("005930.KS")[0].owner_id,
        channel="kakao",
    )
    connections.disconnect(active.id)
    decision = AlertEvaluationDecision(
        outcome="matched", reason="충족", notification_message="조건 충족"
    )

    no_connection = _dispatcher(
        db_session,
        evaluator=FixedEvaluator(decision),
        connections=connections,
        sender=RecordingSender(),
    ).dispatch(analysis)

    stored = SqlAlchemyAlertEvaluationRepository(db_session).get_for_analysis_and_condition(
        analysis.id, condition.id
    )
    assert no_connection.skipped_no_connection == 1
    assert stored.status == "completed" and stored.matched is True

    configured_connection = connections.create(
        owner_id=SqlAlchemyUserAlertEvaluationTargetQuery(db_session).list_active_for_symbol("005930.KS")[0].owner_id,
        channel="kakao",
        credentials=NotificationCredentials(
            access_token="new-token", refresh_token=None, access_token_expires_at=None
        ),
    )
    assert configured_connection is not None
    next_analysis = AnalysisRepository(db_session).save(
        symbol="005930.KS", overall_judgment="상승", summary="다음 분석"
    )
    no_sender = _dispatcher(
        db_session,
        evaluator=FixedEvaluator(decision),
        connections=connections,
        sender=None,
    ).dispatch(next_analysis)
    assert no_sender.skipped_delivery_unavailable == 1


def test_delivery_failure_does_not_change_completed_evaluation(db_session):
    _, _, condition, analysis, connections, _ = _scenario(db_session)
    dispatcher = _dispatcher(
        db_session,
        evaluator=FixedEvaluator(
            AlertEvaluationDecision(
                outcome="matched", reason="충족", notification_message="조건 충족"
            )
        ),
        connections=connections,
        sender=RecordingSender(RuntimeError("kakao unavailable")),
    )

    result = dispatcher.dispatch(analysis)

    evaluation = SqlAlchemyAlertEvaluationRepository(db_session).get_for_analysis_and_condition(
        analysis.id, condition.id
    )
    delivery = SqlAlchemyNotificationDeliveryRepository(db_session).list_for_analysis(analysis.id)[0]
    assert result.delivery_failed == 1
    assert evaluation.status == "completed" and evaluation.matched is True
    assert delivery.status == "failed"
