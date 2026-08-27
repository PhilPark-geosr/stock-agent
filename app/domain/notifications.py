from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal


@dataclass(frozen=True)
class NotificationConnection:
    id: str
    owner_id: str
    channel: Literal["kakao"]
    connected_at: datetime
    disconnected_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.disconnected_at is None


@dataclass(frozen=True)
class NotificationCredentials:
    access_token: str
    refresh_token: str | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None = None

    def requires_refresh(self, now: datetime) -> bool:
        if self.access_token_expires_at is None:
            return False
        return self.access_token_expires_at <= now + timedelta(seconds=60)
