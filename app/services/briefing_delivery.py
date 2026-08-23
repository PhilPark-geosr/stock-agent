from __future__ import annotations

import logging
from collections.abc import Callable

from app.domain.models import BriefingDelivery, InvestmentBriefing
from app.interfaces.briefings import BriefingRenderer
from app.interfaces.notifications import AlertNotifier
from app.interfaces.repositories import BriefingRepository

logger = logging.getLogger(__name__)


class NotificationConnectionRequired(RuntimeError):
    pass


class BriefingDeliveryService:
    def __init__(
        self,
        *,
        repository: BriefingRepository,
        renderer: BriefingRenderer,
        notifier: AlertNotifier,
        connection_is_active: Callable[[str, str], bool],
        max_message_chars: int = 200,
    ) -> None:
        self.repository = repository
        self.renderer = renderer
        self.notifier = notifier
        self.connection_is_active = connection_is_active
        self.max_message_chars = max_message_chars

    def deliver(self, briefing: InvestmentBriefing, channel: str = "KAKAO") -> BriefingDelivery:
        if not self.connection_is_active(briefing.user_account_id, channel):
            raise NotificationConnectionRequired("active notification connection required")
        delivery = self.repository.ensure_delivery(briefing.id, channel)
        if delivery.status == "SENT":
            return delivery

        message = self.renderer.render(
            briefing,
            self.repository.list_items(briefing.id),
            self.repository.list_failures(briefing.id),
        )
        try:
            chunks = self._split_message(message)
            for index, chunk in enumerate(chunks, start=1):
                prefix = f"[{index}/{len(chunks)}] " if len(chunks) > 1 else ""
                self.notifier.send_alert(prefix + chunk)
        except Exception as exc:
            logger.exception("Briefing delivery failed briefing_id=%s", briefing.id)
            return self.repository.record_delivery_attempt(
                delivery,
                status="FAILED",
                error=str(exc),
            )
        return self.repository.record_delivery_attempt(delivery, status="SENT")

    def _split_message(self, message: str) -> list[str]:
        if len(message) <= self.max_message_chars:
            return [message]
        chunk_size = self.max_message_chars - 8
        chunks: list[str] = []
        remaining = message
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, chunk_size + 1)
            if split_at <= 0:
                split_at = chunk_size
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        return chunks
