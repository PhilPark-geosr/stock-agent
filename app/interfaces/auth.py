from typing import Protocol

from app.domain.auth import ExternalLoginCredential, LoginIdentity, UserAccount


class ExternalLogin(Protocol):
    def login(self, credential: ExternalLoginCredential) -> LoginIdentity: ...


class UserAccountRepository(Protocol):
    def find_by_login_identity(self, identity: LoginIdentity) -> UserAccount | None: ...

    def save_or_get_existing(self, account: UserAccount) -> UserAccount: ...

