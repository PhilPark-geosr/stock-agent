from dataclasses import dataclass


@dataclass(frozen=True)
class SystemAlertDispatchResult:
    eligible: int = 0
    sent: int = 0
    skipped_no_connection: int = 0
    skipped_duplicate: int = 0
    failed: int = 0


class SystemAlertDispatcher:
    def __init__(
        self,
        *,
        watchlist_repository,
        connection_repository,
        delivery_repository,
        sender,
    ) -> None:
        self.watchlists = watchlist_repository
        self.connections = connection_repository
        self.deliveries = delivery_repository
        self.sender = sender

    def dispatch(self, analysis) -> SystemAlertDispatchResult:
        if not analysis.should_alert or not (analysis.alert_reason or "").strip():
            return SystemAlertDispatchResult()

        eligible = 0
        sent = 0
        no_connection = 0
        duplicate = 0
        failed = 0

        subscriptions = self.watchlists.list_active_for_symbol(analysis.symbol)
        for subscription in subscriptions:
            eligible += 1
            connection = self.connections.get_active(
                owner_id=subscription.owner_id,
                channel="kakao",
            )
            if connection is None:
                no_connection += 1
                continue

            reservation = self.deliveries.reserve_default_alert(
                recipient_id=subscription.owner_id,
                analysis_id=analysis.id,
                connection_id=connection.id,
                message=analysis.alert_reason,
            )
            if not reservation.created:
                duplicate += 1
                continue

            try:
                self.sender.send(
                    connection=connection,
                    message=analysis.alert_reason,
                )
            except Exception as exc:
                self.deliveries.mark_failed(
                    reservation.delivery.id,
                    reason=str(exc),
                )
                failed += 1
            else:
                self.deliveries.mark_sent(reservation.delivery.id)
                sent += 1

        return SystemAlertDispatchResult(
            eligible=eligible,
            sent=sent,
            skipped_no_connection=no_connection,
            skipped_duplicate=duplicate,
            failed=failed,
        )


class NoOpSystemAlertDispatcher:
    def dispatch(self, analysis) -> SystemAlertDispatchResult:
        return SystemAlertDispatchResult()
