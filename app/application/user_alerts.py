from __future__ import annotations

from dataclasses import dataclass

from app.domain.alert_conditions import CustomAlertCondition


@dataclass(frozen=True)
class UserAlertEvaluationTarget:
    owner_id: str
    subscription_id: int
    condition_record_id: int
    condition: CustomAlertCondition


@dataclass(frozen=True)
class UserAlertDispatchResult:
    eligible: int = 0
    evaluated: int = 0
    matched: int = 0
    sent: int = 0
    skipped_duplicate: int = 0
    skipped_no_connection: int = 0
    skipped_inactive: int = 0
    skipped_delivery_unavailable: int = 0
    failed: int = 0
    delivery_failed: int = 0


class UserAlertDispatcher:
    def __init__(
        self,
        *,
        target_query,
        evaluation_repository,
        evaluator,
        connection_repository,
        delivery_repository,
        sender,
    ) -> None:
        self.targets = target_query
        self.evaluations = evaluation_repository
        self.evaluator = evaluator
        self.connections = connection_repository
        self.deliveries = delivery_repository
        self.sender = sender

    def dispatch(self, analysis) -> UserAlertDispatchResult:
        counts = {
            "eligible": 0,
            "evaluated": 0,
            "matched": 0,
            "sent": 0,
            "skipped_duplicate": 0,
            "skipped_no_connection": 0,
            "skipped_inactive": 0,
            "skipped_delivery_unavailable": 0,
            "failed": 0,
            "delivery_failed": 0,
        }
        for target in self.targets.list_active_for_symbol(analysis.symbol):
            counts["eligible"] += 1
            reservation = self.evaluations.reserve(
                analysis_id=analysis.id,
                condition_id=target.condition_record_id,
            )
            if not reservation.created:
                counts["skipped_duplicate"] += 1
                continue
            try:
                decision = self.evaluator.evaluate(analysis=analysis, condition=target.condition)
                if decision.outcome == "indeterminate":
                    self.evaluations.mark_failed(reservation.evaluation.id, reason=decision.reason)
                    counts["failed"] += 1
                    continue
                evaluation = self.evaluations.complete(
                    reservation.evaluation.id,
                    matched=decision.outcome == "matched",
                    reason=decision.reason,
                    notification_message=decision.notification_message,
                    evidence=decision.evidence,
                )
                counts["evaluated"] += 1
            except Exception as exc:
                self.evaluations.mark_failed(reservation.evaluation.id, reason=str(exc))
                counts["failed"] += 1
                continue
            if not evaluation.matched:
                continue
            counts["matched"] += 1
            if not self.targets.is_still_active(
                subscription_id=target.subscription_id,
                condition_record_id=target.condition_record_id,
            ):
                counts["skipped_inactive"] += 1
                continue
            connection = self.connections.get_active(owner_id=target.owner_id, channel="kakao")
            if connection is None:
                counts["skipped_no_connection"] += 1
                continue
            if self.sender is None:
                counts["skipped_delivery_unavailable"] += 1
                continue
            delivery = self.deliveries.reserve_user_alert(
                evaluation_id=evaluation.id,
                recipient_id=target.owner_id,
                analysis_id=analysis.id,
                connection_id=connection.id,
                message=evaluation.notification_message,
            )
            if not delivery.created:
                counts["skipped_duplicate"] += 1
                continue
            try:
                self.sender.send(connection=connection, message=evaluation.notification_message)
            except Exception as exc:
                self.deliveries.mark_failed(delivery.delivery.id, reason=str(exc))
                counts["delivery_failed"] += 1
            else:
                self.deliveries.mark_sent(delivery.delivery.id)
                counts["sent"] += 1
        return UserAlertDispatchResult(**counts)


class NoOpUserAlertDispatcher:
    def dispatch(self, analysis) -> UserAlertDispatchResult:
        return UserAlertDispatchResult()
