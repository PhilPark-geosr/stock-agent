from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.models import (
    AlertEvaluationRecord,
    CustomAlertConditionRecord,
    NotificationConnectionRecord,
    NotificationDeliveryRecord,
    WatchlistSubscription,
)
from app.domain.alert_conditions import CustomAlertCondition
from app.application.user_alerts import UserAlertEvaluationTarget
from app.domain.notifications import (
    NotificationConnection,
    NotificationCredentials,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


class NotificationCredentialError(RuntimeError):
    pass


class SqlAlchemyNotificationConnectionRepository:
    def __init__(self, db, cipher: Fernet | None) -> None:
        self.db = db
        self.cipher = cipher

    @staticmethod
    def _to_domain(record: NotificationConnectionRecord) -> NotificationConnection:
        return NotificationConnection(
            id=record.id,
            owner_id=record.owner_id,
            channel=record.channel,
            connected_at=record.connected_at,
            disconnected_at=record.disconnected_at,
        )

    def get_record(self, connection_id: str) -> NotificationConnectionRecord | None:
        return self.db.get(NotificationConnectionRecord, connection_id)

    def get_active(
        self,
        *,
        owner_id: str,
        channel: str,
    ) -> NotificationConnection | None:
        record = self.db.scalar(
            select(NotificationConnectionRecord).where(
                NotificationConnectionRecord.owner_id == owner_id,
                NotificationConnectionRecord.channel == channel,
                NotificationConnectionRecord.disconnected_at.is_(None),
            )
        )
        return self._to_domain(record) if record else None

    def create(
        self,
        *,
        owner_id: str,
        channel: str,
        credentials: NotificationCredentials,
    ) -> NotificationConnection:
        active = self.get_active(owner_id=owner_id, channel=channel)
        if active is not None:
            return active

        record = NotificationConnectionRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            channel=channel,
            encrypted_access_token=self._encrypt(credentials.access_token),
            encrypted_refresh_token=self._encrypt(credentials.refresh_token),
            access_token_expires_at=credentials.access_token_expires_at,
            refresh_token_expires_at=credentials.refresh_token_expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return self._to_domain(record)

    def get_credentials(self, connection_id: str) -> NotificationCredentials:
        record = self.get_record(connection_id)
        if (
            record is None
            or record.disconnected_at is not None
            or not record.encrypted_access_token
        ):
            raise NotificationCredentialError(
                "active notification credentials not found"
            )
        return NotificationCredentials(
            access_token=self._decrypt(record.encrypted_access_token),
            refresh_token=self._decrypt(record.encrypted_refresh_token),
            access_token_expires_at=_utc(record.access_token_expires_at),
            refresh_token_expires_at=_utc(record.refresh_token_expires_at),
        )

    def update_credentials(
        self,
        connection_id: str,
        credentials: NotificationCredentials,
    ) -> None:
        record = self.get_record(connection_id)
        if record is None or record.disconnected_at is not None:
            raise NotificationCredentialError(
                "active notification connection not found"
            )
        record.encrypted_access_token = self._encrypt(credentials.access_token)
        record.encrypted_refresh_token = self._encrypt(credentials.refresh_token)
        record.access_token_expires_at = credentials.access_token_expires_at
        record.refresh_token_expires_at = credentials.refresh_token_expires_at
        self.db.add(record)
        self.db.commit()

    def disconnect(self, connection_id: str) -> bool:
        record = self.get_record(connection_id)
        if record is None:
            return False
        record.disconnected_at = datetime.now(timezone.utc)
        record.encrypted_access_token = None
        record.encrypted_refresh_token = None
        record.access_token_expires_at = None
        record.refresh_token_expires_at = None
        self.db.add(record)
        self.db.commit()
        return True

    def _encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self.cipher is None:
            raise NotificationCredentialError("notification credential encryption is not configured")
        return self.cipher.encrypt(value.encode()).decode()

    def _decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self.cipher is None:
            raise NotificationCredentialError("notification credential encryption is not configured")
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise NotificationCredentialError(
                "notification credentials cannot be decrypted"
            ) from exc


@dataclass(frozen=True)
class DeliveryReservation:
    delivery: NotificationDeliveryRecord
    created: bool


class SqlAlchemyNotificationDeliveryRepository:
    def __init__(self, db) -> None:
        self.db = db

    def reserve_default_alert(
        self,
        *,
        recipient_id: str,
        analysis_id: int,
        connection_id: str,
        message: str,
    ) -> DeliveryReservation:
        existing = self._find_default_alert(recipient_id, analysis_id)
        if existing is not None:
            return DeliveryReservation(existing, False)

        record = NotificationDeliveryRecord(
            recipient_id=recipient_id,
            analysis_id=analysis_id,
            connection_id=connection_id,
            kind="default_alert",
            message=message,
            status="pending",
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._find_default_alert(recipient_id, analysis_id)
            return DeliveryReservation(existing, False)
        self.db.refresh(record)
        return DeliveryReservation(record, True)

    def reserve_user_alert(
        self,
        *,
        evaluation_id: int,
        recipient_id: str,
        analysis_id: int,
        connection_id: str,
        message: str,
    ) -> DeliveryReservation:
        existing = self.db.scalar(
            select(NotificationDeliveryRecord).where(
                NotificationDeliveryRecord.evaluation_id == evaluation_id,
                NotificationDeliveryRecord.connection_id == connection_id,
                NotificationDeliveryRecord.kind == "user_alert",
            )
        )
        if existing is not None:
            return DeliveryReservation(existing, False)
        record = NotificationDeliveryRecord(
            evaluation_id=evaluation_id,
            recipient_id=recipient_id,
            analysis_id=analysis_id,
            connection_id=connection_id,
            kind="user_alert",
            message=message,
            status="pending",
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(NotificationDeliveryRecord).where(
                    NotificationDeliveryRecord.evaluation_id == evaluation_id,
                    NotificationDeliveryRecord.connection_id == connection_id,
                    NotificationDeliveryRecord.kind == "user_alert",
                )
            )
            return DeliveryReservation(existing, False)
        self.db.refresh(record)
        return DeliveryReservation(record, True)

    def _find_default_alert(
        self,
        recipient_id: str,
        analysis_id: int,
    ) -> NotificationDeliveryRecord | None:
        return self.db.scalar(
            select(NotificationDeliveryRecord).where(
                NotificationDeliveryRecord.recipient_id == recipient_id,
                NotificationDeliveryRecord.analysis_id == analysis_id,
                NotificationDeliveryRecord.kind == "default_alert",
            )
        )

    def mark_sent(self, delivery_id: int) -> NotificationDeliveryRecord:
        record = self.db.get(NotificationDeliveryRecord, delivery_id)
        record.status = "sent"
        record.sent_at = datetime.now(timezone.utc)
        self.db.commit()
        return record

    def mark_failed(
        self,
        delivery_id: int,
        *,
        reason: str,
    ) -> NotificationDeliveryRecord:
        record = self.db.get(NotificationDeliveryRecord, delivery_id)
        record.status = "failed"
        record.failure_reason = reason[:1000]
        self.db.commit()
        return record

    def list_for_analysis(
        self,
        analysis_id: int,
    ) -> list[NotificationDeliveryRecord]:
        statement = (
            select(NotificationDeliveryRecord)
            .where(NotificationDeliveryRecord.analysis_id == analysis_id)
            .order_by(NotificationDeliveryRecord.id)
        )
        return list(self.db.scalars(statement))


@dataclass(frozen=True)
class EvaluationReservation:
    evaluation: AlertEvaluationRecord
    created: bool


class SqlAlchemyAlertEvaluationRepository:
    def __init__(self, db) -> None:
        self.db = db

    def reserve(self, *, analysis_id: int, condition_id: int) -> EvaluationReservation:
        existing = self.get_for_analysis_and_condition(analysis_id, condition_id)
        if existing is not None:
            return EvaluationReservation(existing, False)
        record = AlertEvaluationRecord(analysis_id=analysis_id, condition_id=condition_id)
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return EvaluationReservation(
                self.get_for_analysis_and_condition(analysis_id, condition_id), False
            )
        self.db.refresh(record)
        return EvaluationReservation(record, True)

    def get_for_analysis_and_condition(
        self, analysis_id: int, condition_id: int
    ) -> AlertEvaluationRecord | None:
        return self.db.scalar(
            select(AlertEvaluationRecord).where(
                AlertEvaluationRecord.analysis_id == analysis_id,
                AlertEvaluationRecord.condition_id == condition_id,
            )
        )

    def complete(
        self,
        evaluation_id: int,
        *,
        matched: bool,
        reason: str,
        notification_message: str | None,
        evidence: list[str],
    ) -> AlertEvaluationRecord:
        record = self.db.get(AlertEvaluationRecord, evaluation_id)
        record.status = "completed"
        record.matched = matched
        record.reason = reason
        record.notification_message = notification_message
        record.evidence = evidence
        record.evaluated_at = datetime.now(timezone.utc)
        self.db.commit()
        return record

    def mark_failed(self, evaluation_id: int, *, reason: str) -> AlertEvaluationRecord:
        record = self.db.get(AlertEvaluationRecord, evaluation_id)
        record.status = "failed"
        record.matched = None
        record.failure_reason = reason[:1000]
        record.evaluated_at = datetime.now(timezone.utc)
        self.db.commit()
        return record


class SqlAlchemyUserAlertEvaluationTargetQuery:
    def __init__(self, db) -> None:
        self.db = db

    def list_active_for_symbol(self, symbol: str) -> list[UserAlertEvaluationTarget]:
        rows = self.db.execute(
            select(WatchlistSubscription, CustomAlertConditionRecord)
            .join(
                CustomAlertConditionRecord,
                CustomAlertConditionRecord.subscription_id == WatchlistSubscription.id,
            )
            .where(
                WatchlistSubscription.symbol == symbol,
                WatchlistSubscription.owner_id.is_not(None),
                WatchlistSubscription.ended_at.is_(None),
                CustomAlertConditionRecord.enabled.is_(True),
                CustomAlertConditionRecord.ended_at.is_(None),
            )
            .order_by(CustomAlertConditionRecord.id)
        ).all()
        return [
            UserAlertEvaluationTarget(
                owner_id=subscription.owner_id,
                subscription_id=subscription.id,
                condition_record_id=record.id,
                condition=self._to_condition(record),
            )
            for subscription, record in rows
        ]

    def is_still_active(self, *, subscription_id: int, condition_record_id: int) -> bool:
        return self.db.scalar(
            select(CustomAlertConditionRecord.id)
            .join(
                WatchlistSubscription,
                CustomAlertConditionRecord.subscription_id == WatchlistSubscription.id,
            )
            .where(
                WatchlistSubscription.id == subscription_id,
                WatchlistSubscription.ended_at.is_(None),
                CustomAlertConditionRecord.id == condition_record_id,
                CustomAlertConditionRecord.enabled.is_(True),
                CustomAlertConditionRecord.ended_at.is_(None),
            )
        ) is not None

    @staticmethod
    def _to_condition(record: CustomAlertConditionRecord) -> CustomAlertCondition:
        return CustomAlertCondition(
            id=f"custom.{record.id}",
            symbol=record.symbol,
            name=record.name,
            user_rule=record.user_rule,
            normalized_rule=record.normalized_rule,
            validation_summary=record.validation_summary,
            required_tools=record.required_tools or [],
            related_symbols=record.related_symbols or [],
            news_symbols=record.news_symbols or [],
            enabled=record.enabled,
        )
