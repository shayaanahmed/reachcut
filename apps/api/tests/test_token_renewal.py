# ruff: noqa: S105, S106 - synthetic OAuth credentials
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1
from clipper.persistence import Base, Clip, Project, SocialAccount, now_utc
from clipper.projects import AutomaticPublicationCreate, PublicationService
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.publishing_http import ProviderApiError
from clipper.providers.social_oauth import FacebookOAuthClient, InstagramOAuthClient, OAuthAppConfig
from clipper.providers.tiktok import TikTokPublishingAdapter
from clipper.providers.x import XPublishingAdapter
from clipper.providers.youtube import (
    YouTubeOAuthClient,
    YouTubeOAuthConfig,
    YouTubePublishingAdapter,
)
from clipper.publishing import OAuthConnection


@pytest.mark.parametrize("platform", ["youtube", "tiktok", "x"])
def test_renewal_serializes_rotation_and_preserves_identity(tmp_path: Path, platform: str) -> None:
    calls: list[httpx.Request] = []

    def token(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert "refresh_token=old-refresh" in request.content.decode()
        return httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 7200},
        )

    client = httpx.Client(transport=httpx.MockTransport(token))
    adapters = {
        "youtube": YouTubePublishingAdapter(
            YouTubeOAuthClient(YouTubeOAuthConfig("id", "secret", "http://callback"), client=client)
        ),
        "tiktok": TikTokPublishingAdapter("id", "secret", client=client),
        "x": XPublishingAdapter("id", "secret", client=client),
    }
    store = EncryptedCredentialStore(tmp_path)
    original = OAuthConnection(
        access_token="expired",
        refresh_token="old-refresh",
        external_account_id="account",
        display_name="Creator",
        username="creator",
        parent_page_id="page",
        access_token_expires_at=1,
    )
    store.save("account", original)
    renew = adapters[platform].refresh_connection
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: store.refresh("account", renew), range(3)))
    assert len(calls) == 1
    for result in results:
        assert result.access_token == "new-access"
        assert result.refresh_token == "new-refresh"
        assert result.display_name == original.display_name
        assert result.username == original.username
        assert result.parent_page_id == original.parent_page_id
    assert store.load("account") == results[-1]


@pytest.mark.parametrize("platform", ["instagram", "facebook"])
def test_meta_uses_page_token_derived_from_extended_user_token(platform: str) -> None:
    steps: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "code" in request.url.params:
            steps.append("login")
            return httpx.Response(200, json={"access_token": "short-user"})
        if request.url.params.get("grant_type") == "fb_exchange_token":
            steps.append("extend")
            assert request.url.params["fb_exchange_token"] == "short-user"
            return httpx.Response(200, json={"access_token": "long-user"})
        if request.url.path.endswith("/me/permissions"):
            steps.append("permissions")
            assert request.url.params["access_token"] == "long-user"
            return httpx.Response(200, json={"data": []})
        steps.append("pages")
        assert request.url.params["access_token"] == "long-user"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "page",
                        "access_token": "durable-page",
                        "instagram_business_account": {"id": "ig", "username": "creator"},
                    }
                ]
            },
        )

    config = OAuthAppConfig("id", "secret", "http://callback", "business-config")
    provider = InstagramOAuthClient if platform == "instagram" else FacebookOAuthClient
    connection = provider(
        config, "v26.0", client=httpx.Client(transport=httpx.MockTransport(handler))
    ).exchange_code("code")
    assert steps == ["login", "extend", "pages"] + (
        ["permissions"] if platform == "instagram" else []
    )
    assert connection.access_token == "durable-page"
    assert connection.external_account_id == ("ig" if platform == "instagram" else "page")


def test_rotated_credentials_survive_failed_upload(
    tmp_path: Path, make_plan: Callable[..., EditingPlanV1]
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    credentials = EncryptedCredentialStore(tmp_path)
    credentials.save(
        "account", OAuthConnection(refresh_token="old-refresh", external_account_id="account")
    )

    class FailingPublisher:
        def refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
            return replace(
                connection, refresh_token="replacement-refresh", access_token="replacement-access"
            )

        def publish(self, *args: object) -> None:
            assert credentials.load("account").refresh_token == "replacement-refresh"
            raise ProviderApiError("Upload failed after refresh")

    with Session(engine) as session:
        project = Project(
            title="Video",
            original_filename="video.mp4",
            source_path=str(tmp_path / "video.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        clip = Clip(
            project=project,
            plan=make_plan().model_dump(mode="json"),
            approval_status="approved",
            final_path=str(tmp_path / "final.mp4"),
        )
        session.add_all(
            [
                project,
                clip,
                SocialAccount(
                    id="account", platform="x", label="Creator", connection_status="connected"
                ),
            ]
        )
        session.commit()
        with pytest.raises(ProviderApiError, match="Upload failed"):
            PublicationService().publish(
                session,
                clip.id,
                AutomaticPublicationCreate(
                    social_account_id="account", title="Video", description="Description"
                ),
                FailingPublisher(),
                credentials,
            )
        assert credentials.load("account").refresh_token == "replacement-refresh"
