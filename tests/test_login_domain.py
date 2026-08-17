from dataclasses import FrozenInstanceError

import pytest

from app.application.login import LoginService
from app.domain.auth import ExternalLoginCredential, LoginIdentity, UserAccount


class FakeExternalLogin:
    def __init__(self, identity: LoginIdentity) -> None:
        self.identity = identity
        self.credentials: list[ExternalLoginCredential] = []

    def login(self, credential: ExternalLoginCredential) -> LoginIdentity:
        self.credentials.append(credential)
        return self.identity


class FakeAccounts:
    def __init__(self, existing: UserAccount | None = None) -> None:
        self.existing = existing
        self.saved: list[UserAccount] = []

    def find_by_login_identity(self, identity: LoginIdentity) -> UserAccount | None:
        return self.existing if self.existing and self.existing.login_identity == identity else None

    def save_or_get_existing(self, account: UserAccount) -> UserAccount:
        self.saved.append(account)
        return self.existing or account


def test_login_identity_requires_provider_and_subject() -> None:
    with pytest.raises(ValueError):
        LoginIdentity(provider="", provider_subject_id="123")
    with pytest.raises(ValueError):
        LoginIdentity(provider="kakao", provider_subject_id="")


def test_login_identity_is_immutable() -> None:
    identity = LoginIdentity("kakao", "123")
    with pytest.raises(FrozenInstanceError):
        identity.provider = "other"  # type: ignore[misc]


def test_login_service_registers_new_account_from_external_identity() -> None:
    identity = LoginIdentity("kakao", "123")
    external = FakeExternalLogin(identity)
    accounts = FakeAccounts()
    credential = ExternalLoginCredential("code", "https://service/callback")

    account = LoginService(external, accounts).login(credential)

    assert account.login_identity == identity
    assert accounts.saved == [account]
    assert external.credentials == [credential]


def test_login_service_returns_existing_account() -> None:
    identity = LoginIdentity("kakao", "123")
    existing = UserAccount.register(identity)
    accounts = FakeAccounts(existing)

    result = LoginService(FakeExternalLogin(identity), accounts).login(
        ExternalLoginCredential("code", "https://service/callback")
    )

    assert result is existing
    assert accounts.saved == []

