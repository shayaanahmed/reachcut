from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from clipper.persistence import SocialAccount, now_utc
from clipper.persistence.models import OAuthAccountSelection, SocialAccountIdentity
from clipper.providers.credentials import CredentialStoreError, EncryptedCredentialStore
from clipper.publishing import OAuthClient, OAuthConnection, PublishingPlatform
from clipper.publishing.contracts import MultiAccountOAuthClient


class PublishingConnectionError(RuntimeError):
    pass


class AccountSelectionRequired(PublishingConnectionError):
    def __init__(self, selection_token: str) -> None:
        super().__init__("Choose the destination to connect")
        self.selection_token = selection_token


@dataclass(frozen=True)
class AccountChoice:
    external_account_id: str
    display_name: str
    username: str
    parent_page_name: str
    already_connected: bool


@dataclass(frozen=True)
class PendingAccountSelection:
    platform: str
    candidates: tuple[AccountChoice, ...]


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
        account: SocialAccount | None = None
        if target.startswith("new:"):
            if target.removeprefix("new:") != platform:
                raise PublishingConnectionError(
                    "the authorization platform does not match the request"
                )
        else:
            account = self._account(session, target)
            if account.platform != platform:
                raise PublishingConnectionError(
                    "the authorization platform does not match the account"
                )
        client = self._client(platform)
        connections = (
            client.exchange_code_candidates(code, state)
            if isinstance(client, MultiAccountOAuthClient)
            else [client.exchange_code(code, state)]
        )
        if not connections:
            raise PublishingConnectionError("No publishing destinations were returned")
        if account:
            expected = self._expected_identity(account)
            matches = (
                [item for item in connections if item.external_account_id == expected]
                if expected
                else [
                    item
                    for item in connections
                    if account.username
                    and item.username
                    and self._username(account.username) == self._username(item.username)
                ]
            )
            if len(matches) != 1:
                raise PublishingConnectionError(
                    f"Destination {account.username or account.label} was not returned. "
                    "Reconnect and grant access to that Page/account. "
                    "Its saved connection was not changed."
                )
            return self._save_connection(session, account, matches[0])
        existing = None
        if len(connections) == 1 and isinstance(client, MultiAccountOAuthClient):
            existing = self._matching_account(
                list(
                    session.scalars(select(SocialAccount).where(SocialAccount.platform == platform))
                ),
                connections[0],
            )
        if len(connections) == 1 and not (existing and existing.is_active):
            return self._save_discovered_account(session, platform, connections[0])
        session.execute(
            delete(OAuthAccountSelection).where(
                OAuthAccountSelection.created_at < now_utc() - timedelta(minutes=10)
            )
        )
        selection = OAuthAccountSelection(
            id=str(uuid4()),
            encrypted_payload=self._credentials.seal_state(
                json.dumps(
                    {
                        "platform": platform,
                        "connections": [asdict(item) for item in connections],
                    }
                )
            ),
        )
        session.add(selection)
        session.commit()
        raise AccountSelectionRequired(self._credentials.seal_state("selection:" + selection.id))

    def _pending(
        self, session: Session, token: str
    ) -> tuple[OAuthAccountSelection, str, list[OAuthConnection]]:
        reference = self._credentials.open_state(token)
        if not reference.startswith("selection:"):
            raise PublishingConnectionError("Invalid account selection")
        pending = session.get(OAuthAccountSelection, reference.removeprefix("selection:"))
        if not pending:
            raise PublishingConnectionError(
                "Account selection expired or was already used. Connect again."
            )
        payload = json.loads(self._credentials.open_state(pending.encrypted_payload))
        return (
            pending,
            str(payload["platform"]),
            [OAuthConnection(**item) for item in payload["connections"]],
        )

    def pending_selection(self, session: Session, token: str) -> PendingAccountSelection:
        _, platform, connections = self._pending(session, token)
        accounts = list(
            session.scalars(select(SocialAccount).where(SocialAccount.platform == platform))
        )
        return PendingAccountSelection(
            platform,
            tuple(
                AccountChoice(
                    item.external_account_id,
                    item.display_name,
                    item.username,
                    item.parent_page_name,
                    any(
                        account.is_active
                        and self._expected_identity(account) == item.external_account_id
                        for account in accounts
                    ),
                )
                for item in connections
            ),
        )

    def select_account(self, session: Session, token: str, external_id: str) -> SocialAccount:
        pending, platform, connections = self._pending(session, token)
        selected = next(
            (item for item in connections if item.external_account_id == external_id), None
        )
        if not selected:
            raise PublishingConnectionError("Choose an account returned by this authorization")
        # Claim once in the same transaction as the account update. SQLite's write lock
        # also serializes two tabs attempting to consume the same selection.
        consumed = session.execute(
            delete(OAuthAccountSelection).where(OAuthAccountSelection.id == pending.id)
        )
        if not consumed.rowcount:  # type: ignore[attr-defined]
            session.rollback()
            raise PublishingConnectionError("This account selection was already used")
        return self._save_discovered_account(session, platform, selected)

    @staticmethod
    def _username(value: str) -> str:
        return value.strip().lstrip("@").casefold()

    def _expected_identity(self, account: SocialAccount) -> str:
        if account.identity:
            return account.identity.external_account_id
        try:
            stored = self._credentials.load(account.id)
        except CredentialStoreError:
            stored = None
        if stored and stored.external_account_id:
            return stored.external_account_id
        # Legacy Facebook records retain the numeric Page ID in their public URL.
        if account.platform == "facebook" and account.profile_url:
            path = urlparse(account.profile_url).path.strip("/")
            if path.isdigit():
                return path
        return ""

    def _bind_identity(self, account: SocialAccount, connection: OAuthConnection) -> None:
        if not connection.external_account_id:
            raise PublishingConnectionError("Provider did not return an account identity")
        if (
            account.identity
            and account.identity.external_account_id != connection.external_account_id
        ):
            raise PublishingConnectionError(
                "Cannot replace an account with a different destination"
            )
        if not account.identity:
            account.identity = SocialAccountIdentity(
                platform=account.platform, external_account_id=connection.external_account_id
            )
        account.identity.parent_page_id = connection.parent_page_id
        account.identity.parent_page_name = connection.parent_page_name

    def _save_connection(
        self, session: Session, account: SocialAccount, connection: OAuthConnection
    ) -> SocialAccount:
        expected = self._expected_identity(account)
        if expected and expected != connection.external_account_id:
            raise PublishingConnectionError(
                "Cannot replace an account with a different destination"
            )
        self._bind_identity(account, connection)
        session.flush()
        self._credentials.save(account.id, connection)
        account.connection_status = "connected"
        account.is_active = True
        if connection.username:
            account.username = connection.username.lstrip("@")[:100]
        if connection.profile_url:
            account.profile_url = connection.profile_url[:2048]
        session.commit()
        return account

    def backfill_identities(self, session: Session) -> None:
        """Persist existing provider IDs before tokens can be disconnected or replaced."""
        for account in session.scalars(
            select(SocialAccount).where(SocialAccount.is_active.is_(True))
        ):
            if account.identity:
                continue
            try:
                connection = self._credentials.load(account.id)
            except CredentialStoreError:
                continue
            if not connection or not connection.external_account_id:
                continue
            existing = session.scalar(
                select(SocialAccountIdentity).where(
                    SocialAccountIdentity.platform == account.platform,
                    SocialAccountIdentity.external_account_id == connection.external_account_id,
                )
            )
            if existing:
                continue
            if (
                account.platform == "instagram"
                and account.username
                and connection.username
                and self._username(account.username) != self._username(connection.username)
            ):
                continue
            self._bind_identity(account, connection)
            session.flush()
        session.commit()

    def disconnect(self, session: Session, account_id: str) -> SocialAccount:
        account = self._account(session, account_id)
        stored = self._credentials.load(account.id)
        if stored and stored.external_account_id:
            self._bind_identity(account, stored)
            session.flush()
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
        if (
            account.identity
            and connection
            and account.identity.external_account_id != connection.external_account_id
        ):
            issues.append("account_identity_mismatch")
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
                select(SocialAccount)
                .where(SocialAccount.platform == platform)
                .order_by(SocialAccount.is_active.desc(), SocialAccount.created_at)
            )
        )
        account = self._matching_account(accounts, connection)
        if account is None:
            account = SocialAccount(
                platform=platform,
                label=(connection.display_name or self._default_label(platform))[:100],
                username=connection.username.lstrip("@")[:100],
                is_default=not any(item.is_active and item.is_default for item in accounts),
            )
            session.add(account)
            session.flush()
        elif not account.is_active:
            account.is_default = not any(item.is_active and item.is_default for item in accounts)
        return self._save_connection(session, account, connection)

    def _matching_account(
        self, accounts: list[SocialAccount], connection: OAuthConnection
    ) -> SocialAccount | None:
        for account in accounts:
            if self._expected_identity(account) == connection.external_account_id:
                return account
        if connection.username:
            matches = [
                account
                for account in accounts
                if not self._expected_identity(account)
                and self._username(account.username) == self._username(connection.username)
            ]
            active = [account for account in matches if account.is_active]
            if len(active) == 1:
                return active[0]
            if len(matches) == 1:
                return matches[0]
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
