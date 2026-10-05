from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from sqlalchemy.orm import Session

from clipper.persistence import SocialAccount
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.publishing import OAuthClient, OAuthConnection, PublishingPlatform


class PublishingConnectionError(RuntimeError):
    pass


class PublishingConnectionService:
    def __init__(
        self,
        oauth_clients: Mapping[PublishingPlatform, OAuthClient],
        credentials: EncryptedCredentialStore,
    ) -> None:
        self._oauth_clients = dict(oauth_clients)
        self._credentials = credentials

    @property
    def configured_platforms(self) -> list[PublishingPlatform]:
        return [platform for platform, client in self._oauth_clients.items() if client.configured]

    @property
    def youtube_configured(self) -> bool:
        client = self._oauth_clients.get("youtube")
        return bool(client and client.configured)

    def authorization_url(self, session: Session, account_id: str) -> str:
        account = self._account(session, account_id)
        client = self._client(account.platform)
        state = self._credentials.seal_state(account.id)
        return client.authorization_url(state)

    def complete_authorization(
        self,
        session: Session,
        platform: str,
        state: str,
        code: str,
    ) -> SocialAccount:
        account_id = self._credentials.open_state(state)
        account = self._account(session, account_id)
        callback_platform = account.platform if platform == "meta" else platform
        if account.platform != callback_platform:
            raise PublishingConnectionError("the authorization platform does not match the account")
        connection = self._client(callback_platform).exchange_code(code, state)
        self._credentials.save(account.id, connection)
        account.connection_status = "connected"
        session.commit()
        return account

    def disconnect(self, session: Session, account_id: str) -> SocialAccount:
        account = self._account(session, account_id)
        self._credentials.delete(account.id)
        account.connection_status = "manual"
        session.commit()
        return account

    def save_api_connection(
        self,
        session: Session,
        account_id: str,
        connection: OAuthConnection,
    ) -> SocialAccount:
        """Compatibility path for existing clients; the web UI uses OAuth."""
        account = self._account(session, account_id)
        if not connection.access_token:
            raise PublishingConnectionError("an access token is required")
        if account.platform in {"instagram", "facebook"} and not connection.external_account_id:
            raise PublishingConnectionError(f"a {account.platform} account or Page ID is required")
        self._credentials.save(account.id, connection)
        account.connection_status = "connected"
        session.commit()
        return account

    def _client(self, platform: str) -> OAuthClient:
        if platform not in self._oauth_clients:
            raise PublishingConnectionError(f"{platform} OAuth is not supported")
        return self._oauth_clients[cast(PublishingPlatform, platform)]

    @staticmethod
    def _account(session: Session, account_id: str) -> SocialAccount:
        account = session.get(SocialAccount, account_id)
        if not account or not account.is_active:
            raise PublishingConnectionError("social account not found")
        return account
