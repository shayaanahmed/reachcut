from collections.abc import Generator
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.main import app
from clipper.persistence import Base, SocialAccount, get_session
from clipper.projects import (
    PublishingConnectionService,
    SocialAccountService,
    SocialAccountUpdate,
)
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.publishing import OAuthConnection


class DiscoveredOAuthClient:
    configured = True

    def authorization_url(self, state: str) -> str:
        return f"https://provider.example/authorize?{urlencode({'state': state})}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        assert code == "oauth-code"
        assert state
        return OAuthConnection(
            access_token="access-token",  # noqa: S106
            external_account_id="creator-42",
            display_name="Creator Studio",
            username="creator",
            profile_url="https://social.example/creator",
        )


def add_account(
    session: Session,
    label: str,
    *,
    platform: str = "youtube",
    is_default: bool = False,
) -> SocialAccount:
    account = SocialAccount(
        platform=platform,
        label=label,
        username=label.lower().replace(" ", ""),
        connection_status="disconnected",
        is_default=is_default,
    )
    session.add(account)
    session.commit()
    return account


def connect_new_account(
    connections: PublishingConnectionService,
    session: Session,
    platform: str,
) -> SocialAccount:
    authorization_url = connections.authorization_url_for_platform(platform)
    state = parse_qs(urlparse(authorization_url).query)["state"][0]
    return connections.complete_authorization(session, platform, state, "oauth-code")


def test_social_accounts_keep_one_default_and_archive_without_losing_history() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = SocialAccountService()

    with Session(engine) as session:
        first = add_account(session, "Main", is_default=True)
        second = add_account(session, "Experiments")
        service.update(
            session,
            second.id,
            SocialAccountUpdate(
                label="Experiments",
                default_hashtags=("clips", "#CreatorTips", "clips"),
                currency="eur",
                is_default=True,
            ),
        )

        assert first.is_default is False
        assert second.is_default is True
        assert second.username == "experiments"
        assert second.default_hashtags == ["#clips", "#CreatorTips"]
        assert second.currency == "EUR"

        service.archive(session, second.id)
        session.refresh(first)
        assert first.is_default is True
        assert [account.id for account in service.list(session)] == [first.id]


def test_social_account_routes_update_and_archive_without_legacy_creation() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        account_id = add_account(session, "Main TikTok", platform="tiktok", is_default=True).id

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            legacy_create = client.post(
                "/api/social-accounts",
                json={
                    "platform": "tiktok",
                    "label": "Placeholder",
                },
            )
            assert legacy_create.status_code == 405

            updated = client.put(
                f"/api/social-accounts/{account_id}",
                json={
                    "label": "Primary TikTok",
                    "default_hashtags": ["#clips"],
                    "default_cta": "Follow for more",
                    "currency": "USD",
                    "is_default": True,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["label"] == "Primary TikTok"
            assert updated.json()["default_cta"] == "Follow for more"
            assert updated.json()["username"] == "maintiktok"

            legacy_token_save = client.post(
                f"/api/social-accounts/{account_id}/connection",
                json={"access_token": "do-not-accept"},
            )
            assert legacy_token_save.status_code == 405
            assert (
                client.get(f"/api/social-accounts/{account_id}/connect/youtube").status_code == 404
            )

            readiness = client.get("/api/social-accounts/readiness")
            assert readiness.status_code == 200
            assert readiness.json()[0]["account_id"] == account_id
            assert readiness.json()[0]["publishing_ready"] is False
            assert "credentials_missing" in readiness.json()[0]["issues"]

            archived = client.delete(f"/api/social-accounts/{account_id}")
            assert archived.status_code == 204
            assert client.get("/api/social-accounts").json() == []
    finally:
        app.dependency_overrides.clear()


def test_disconnect_removes_encrypted_credentials_and_marks_account_disconnected(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    connections = PublishingConnectionService(
        {"instagram": DiscoveredOAuthClient()},
        credentials,
    )

    with Session(engine) as session:
        connected = connect_new_account(connections, session, "instagram")

        assert connected.connection_status == "connected"
        assert credentials.load(connected.id) is not None

        disconnected = connections.disconnect(session, connected.id)

        assert disconnected.connection_status == "disconnected"
        assert credentials.load(connected.id) is None


def test_connection_readiness_detects_missing_and_available_credentials(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    connections = PublishingConnectionService(
        {"youtube": DiscoveredOAuthClient()},
        credentials,
    )

    with Session(engine) as session:
        account = connect_new_account(connections, session, "youtube")
        ready = connections.connection_readiness(session, account.id)
        assert ready.publishing_ready is True
        assert ready.provider_configured is True
        assert ready.credentials_available is True
        assert ready.issues == ()

        connections.disconnect(session, account.id)
        missing = connections.connection_readiness(session, account.id)
        assert missing.publishing_ready is False
        assert missing.issues == ("account_not_connected", "credentials_missing")


def test_platform_first_oauth_creates_real_account_after_callback_and_deduplicates(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    connections = PublishingConnectionService(
        {"x": DiscoveredOAuthClient()},
        credentials,
    )

    with Session(engine) as session:
        authorization_url = connections.authorization_url_for_platform("x")
        state = parse_qs(urlparse(authorization_url).query)["state"][0]

        assert SocialAccountService().list(session) == []

        connected = connections.complete_authorization(session, "x", state, "oauth-code")

        assert connected.label == "Creator Studio"
        assert connected.username == "creator"
        assert connected.profile_url == "https://social.example/creator"
        assert connected.connection_status == "connected"
        stored = credentials.load(connected.id)
        assert stored is not None
        assert stored.external_account_id == "creator-42"

        next_url = connections.authorization_url_for_platform("x")
        next_state = parse_qs(urlparse(next_url).query)["state"][0]
        duplicate = connections.complete_authorization(session, "x", next_state, "oauth-code")

        assert duplicate.id == connected.id
        assert len(SocialAccountService().list(session)) == 1
