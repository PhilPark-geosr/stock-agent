from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class LoginIdentity:
    provider: str
    provider_subject_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.provider_subject_id.strip():
            raise ValueError("login identity requires provider and provider subject id")


@dataclass(frozen=True)
class ExternalLoginCredential:
    authorization_code: str
    redirect_uri: str


@dataclass(frozen=True)
class UserAccount:
    id: str
    login_identity: LoginIdentity

    @classmethod
    def register(cls, identity: LoginIdentity) -> "UserAccount":
        return cls(id=str(uuid4()), login_identity=identity)

