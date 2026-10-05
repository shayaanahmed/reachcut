from collections.abc import Generator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.main import app
from clipper.persistence import Base, get_session
from clipper.projects import (
    PublishingConnectionService,
    SocialAccountCreate,
    SocialAccountService,
)
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.youtube import YouTubeOAuthClient, YouTubeOAuthConfig
from clipper.publishing import OAuthConnection


def account_request(label: str, *, is_default: bool = False) -> SocialAccountCreate:
    return SocialAccountCreate(
        platform="youtube",
        label=label,
        username=f"@{label.lower().replace(' ', '')}",
        default_hashtags=("clips", "#CreatorTips", "clips"),
        currency="eur",
        is_default=is_default,
    )


def test_social_accounts_keep_one_default_and_archive_without_losing_history() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = SocialAccountService()

    with Session(engine) as session:
        first = service.create(session, account_request("Main"))
        second = service.create(session, account_request("Experiments", is_default=True))

        assert first.is_default is False
        assert second.is_default is True
        assert second.username == "experiments"
        assert second.default_hashtags == ["#clips", "#CreatorTips"]
        assert second.currency == "EUR"

        service.archive(session, second.id)
        session.refresh(first)
        assert first.is_default is True
        assert [account.id for account in service.list(session)] == [first.id]


def test_social_account_routes_create_update_and_archive() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/social-accounts",
                json={
                    "platform": "tiktok",
                    "label": "Main TikTok",
                    "username": "@creator",
                    "default_hashtags": ["shorts", "#creator"],
                    "currency": "EUR",
                },
            )
            assert created.status_code == 201
            account_id = created.json()["id"]
            assert created.json()["is_default"] is True
            assert created.json()["default_hashtags"] == ["#shorts", "#creator"]

            updated = client.put(
                f"/api/social-accounts/{account_id}",
                json={
                    "label": "Primary TikTok",
                    "username": "creator",
                    "default_hashtags": ["#clips"],
                    "default_cta": "Follow for more",
                    "currency": "USD",
                    "is_default": True,
                },
            )
            assert updated.status_code == 200
            assert updated.json()["label"] == "Primary TikTok"
            assert updated.json()["default_cta"] == "Follow for more"

            archived = client.delete(f"/api/social-accounts/{account_id}")
            assert archived.status_code == 204
            assert client.get("/api/social-accounts").json() == []
    finally:
        app.dependency_overrides.clear()


def test_non_youtube_connection_is_encrypted_and_marked_connected(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    accounts = SocialAccountService()
    credentials = EncryptedCredentialStore(tmp_path)
    connections = PublishingConnectionService(
        {"youtube": YouTubeOAuthClient(YouTubeOAuthConfig("", "", ""))},
        credentials,
    )

    with Session(engine) as session:
        account = accounts.create(
            session,
            SocialAccountCreate(platform="instagram", label="Main Instagram"),
        )
        connected = connections.save_api_connection(
            session,
            account.id,
            OAuthConnection(
                access_token="test-access-value",  # noqa: S106
                external_account_id="ig-user-1",
            ),
        )

        assert connected.connection_status == "connected"
        assert credentials.load(account.id) == OAuthConnection(
            access_token="test-access-value",  # noqa: S106
            external_account_id="ig-user-1",
        )
