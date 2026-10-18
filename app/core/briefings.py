import os
import httpx
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app.application.briefing_analysis import BriefingAnalyzer
from app.application.briefing_delivery import BriefingDelivery
from app.application.briefing_evidence import EvidenceBuilder
from app.application.briefing_prompts import PromptPolicy
from app.application.briefings import BriefingCoordinator
from app.integrations.briefing_calendar import BriefingContextSource
from app.integrations.briefing_sources import DisclosureSource, YFinanceEvidenceSource
from app.integrations.kakao_auth import kakao_settings
from app.integrations.kakao_notify import KakaoNotificationSender
from app.integrations.llm.gemini_briefing_model import GeminiBriefingModel
from app.repositories.briefings import BriefingHistory
from app.repositories.notifications import SqlAlchemyNotificationConnectionRepository
from app.repositories.repositories import WatchlistRepository


class _KakaoBriefingSender:
    def __init__(self, connections, settings):
        self.connections, self.settings = connections, settings

    def send(self, *, connection, message):
        with httpx.Client(timeout=30) as client:
            KakaoNotificationSender(self.connections, rest_api_key=self.settings["rest_api_key"],
                client_secret=self.settings["client_secret"], client=client).send(connection=connection, message=message)


def build_briefing_coordinator(db, *, clock=None, sources=None, model=None, sender=None, connections=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    history = BriefingHistory(db, clock)
    cipher = None
    if os.getenv("NOTIFICATION_TOKEN_FERNET_KEY"):
        try:
            cipher = Fernet(os.environ["NOTIFICATION_TOKEN_FERNET_KEY"].encode())
        except (ValueError, TypeError):
            pass
    connections = connections or SqlAlchemyNotificationConnectionRepository(db, cipher)
    settings = kakao_settings()
    if sender is None and cipher is not None and settings["rest_api_key"]:
        sender = _KakaoBriefingSender(connections, settings)
    return BriefingCoordinator(history=history, context_source=BriefingContextSource(WatchlistRepository(db), history),
        prompts=PromptPolicy(db), evidence=EvidenceBuilder(sources if sources is not None else [YFinanceEvidenceSource(), DisclosureSource()]),
        analyzer=BriefingAnalyzer(model or GeminiBriefingModel()),
        delivery=BriefingDelivery(history, connections, sender, clock), clock=clock)
