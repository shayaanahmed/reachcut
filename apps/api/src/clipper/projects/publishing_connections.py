from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import SocialAccount
from clipper.providers.credentials import CredentialStoreError, EncryptedCredentialStore
from clipper.publishing import OAuthClient, OAuthConnection, PublishingPlatform


class PublishingConnectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountConnectionReadiness:
    account_id: str
    platform: str
    provider_configured: bool
    credentials_available: bool
    publishing_ready: bool
    issues: tuple[str, ...]


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

    def authorization_url(self, session: Session, account_id: str) -> str:
        account = self._account(session, account_id)
        client = self._client(account.platform)
        state = self._credentials.seal_state(account.id)
        return client.authorization_url(state)

    def authorization_url_for_platform(self, platform: str) -> str:
        client = self._client(platform)
        state = self._credentials.seal_state(f"new:{platform}")
        return client.authorization_url(state)

    def complete_authorization(
        self,
        session: Session,
        platform: str,
        state: str,
        code: str,
    ) -> SocialAccount:
        target = self._credentials.open_state(state)
        callback_platform = platform
        if target.startswith("new:"):
            requested_platform = target.removeprefix("new:")
            if requested_platform != callback_platform:
                raise PublishingConnectionError(
                    "the authorization platform does not match the requested provider"
                )
            connection = self._client(callback_platform).exchange_code(code, state)
            return self._save_discovered_account(session, callback_platform, connection)

        account = self._account(session, target)
        if account.platform != platform:
            raise PublishingConnectionError("the authorization platform does not match the account")
        connection = self._client(platform).exchange_code(code, state)
        self._credentials.save(account.id, connection)
        account.connection_status = "connected"
        if connection.username:
            account.username = connection.username[:100]
        if connection.profile_url:
            account.profile_url = connection.profile_url[:2048]
        session.commit()
        return account

    def disconnect(self, session: Session, account_id: str) -> SocialAccount:
        account = self._account(session, account_id)
        self._credentials.delete(account.id)
        account.connection_status = "disconnected"
        session.commit()
        return account

    def connection_readiness(
        self,
        session: Session,
        account_id: str,
    ) -> AccountConnectionReadiness:
        """Report publish readiness without exposing credential contents."""
        account = self._account(session, account_id)
        provider_configured = account.platform in self.configured_platforms
        credentials_available = False
        credential_error = False
        connection: OAuthConnection | None = None
        try:
            connection = self._credentials.load(account.id)
            credentials_available = connection is not None
        except CredentialStoreError:
            credential_error = True

        issues: list[str] = []
        if not provider_configured:
            issues.append("provider_not_configured")
        if account.connection_status != "connected":
            issues.append("account_not_connected")
        if credential_error:
            issues.append("credentials_unreadable")
        elif not credentials_available:
            issues.append("credentials_missing")
        elif (
            account.platform == "instagram"
            and connection
            and connection.refresh_token
            and connection.refresh_token == connection.access_token
        ):
            issues.append("account_reconnect_required")
        return AccountConnectionReadiness(
            account_id=account.id,
            platform=account.platform,
            provider_configured=provider_configured,
            credentials_available=credentials_available,
            publishing_ready=not issues,
            issues=tuple(issues),
        )

    def _client(self, platform: str) -> OAuthClient:
        if platform not in self._oauth_clients:
            raise PublishingConnectionError(f"{platform} OAuth is not supported")
        return self._oauth_clients[cast(PublishingPlatform, platform)]

    def _save_discovered_account(
        self,
        session: Session,
        platform: str,
        connection: OAuthConnection,
    ) -> SocialAccount:
        accounts = list(
            session.scalars(
                select(SocialAccount).where(
                    SocialAccount.platform == platform,
                    SocialAccount.is_active.is_(True),
                )
            )
        )
        account = self._matching_account(accounts, connection)
        if account is None:
            account = SocialAccount(
                platform=platform,
                label=(connection.display_name or self._default_label(platform))[:100],
                username=connection.username.lstrip("@")[:100],
                profile_url=connection.profile_url[:2048] or None,
                connection_status="connected",
                is_default=not any(candidate.is_default for candidate in accounts),
            )
            session.add(account)
            session.flush()
        else:
            account.connection_status = "connected"
            if connection.username:
                account.username = connection.username.lstrip("@")[:100]
            if connection.profile_url:
                account.profile_url = connection.profile_url[:2048]

        self._credentials.save(account.id, connection)
        session.commit()
        return account

    def _matching_account(
        self,
        accounts: list[SocialAccount],
        connection: OAuthConnection,
    ) -> SocialAccount | None:
        for account in accounts:
            try:
                stored = self._credentials.load(account.id)
            except CredentialStoreError:
                continue
            if (
                stored
                and connection.external_account_id
                and stored.external_account_id == connection.external_account_id
            ):
                return account
        if connection.username:
            normalized = connection.username.lstrip("@").casefold()
            return next(
                (account for account in accounts if account.username.casefold() == normalized),
                None,
            )
        return None

    @staticmethod
    def _default_label(platform: str) -> str:
        return {
            "youtube": "YouTube channel",
            "tiktok": "TikTok account",
            "instagram": "Instagram account",
            "facebook": "Facebook Page",
            "x": "X account",
        }.get(platform, "Social account")

    @staticmethod
    def _account(session: Session, account_id: str) -> SocialAccount:
        account = session.get(SocialAccount, account_id)
        if not account or not account.is_active:
            raise PublishingConnectionError("social account not found")
        return account
