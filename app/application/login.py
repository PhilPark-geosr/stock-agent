from app.domain.auth import ExternalLoginCredential, UserAccount
from app.interfaces.auth import ExternalLogin, UserAccountRepository


class LoginService:
    def __init__(self, external_login: ExternalLogin, accounts: UserAccountRepository) -> None:
        self.external_login = external_login
        self.accounts = accounts

    def login(self, credential: ExternalLoginCredential) -> UserAccount:
        identity = self.external_login.login(credential)
        existing = self.accounts.find_by_login_identity(identity)
        if existing is not None:
            return existing
        return self.accounts.save_or_get_existing(UserAccount.register(identity))

