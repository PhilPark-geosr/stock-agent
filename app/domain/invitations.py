from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


def hash_code(code: str) -> str:
    return sha256(code.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class Invitation:
    id: str
    code_hash: str
    issued_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def can_use(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at
