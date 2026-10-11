from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from clipper.providers.social_oauth import (
    MetaOAuthClient,
    OAuthAppConfig,
    TikTokOAuthClient,
    XOAuthClient,
)
from clipper.publishing import OAuthProviderError


def test_tiktok_oauth_exchanges_code_for_refreshable_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/user/info/":
            assert request.headers["authorization"] == "Bearer access"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "user": {
                            "open_id": "creator-1",
                            "display_name": "Creator One",
                        }
                    }
                },
            )
        assert request.url == "https://open.tiktokapis.com/v2/oauth/token/"
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "open_id": "creator-1",
            },
        )

    client = TikTokOAuthClient(
        OAuthAppConfig("client", "secret", "https://example.test/tiktok"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    authorization = parse_qs(urlparse(client.authorization_url("state-1")).query)
    connection = client.exchange_code("code-1")

    assert "video.publish" in authorization["scope"][0]
    assert connection.access_token == "access"  # noqa: S105 - synthetic test fixture
    assert connection.refresh_token == "refresh"  # noqa: S105 - synthetic test fixture
    assert connection.external_account_id == "creator-1"
    assert connection.display_name == "Creator One"


def test_meta_oauth_resolves_instagram_account_without_manual_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "page-1",
                        "name": "Creator Page",
                        "access_token": "page-token",
                        "instagram_business_account": {
                            "id": "instagram-1",
                            "name": "Creator Studio",
                            "username": "creator",
                        },
                    }
                ]
            },
        )

    client = MetaOAuthClient(
        OAuthAppConfig("client", "secret", "https://example.test/meta"),
        "v24.0",
        "instagram",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    connection = client.exchange_code("code-1")

    assert connection.access_token == "page-token"  # noqa: S105 - synthetic test fixture
    assert connection.external_account_id == "instagram-1"
    assert connection.display_name == "Creator Studio"
    assert connection.username == "creator"
    assert connection.profile_url == "https://www.instagram.com/creator/"


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ([], "Meta returned no Facebook Pages for this login"),
        (
            [{"id": "page-1", "access_token": "page-token"}],
            "none has a linked Instagram professional account",
        ),
    ],
)
def test_meta_oauth_explains_why_an_instagram_account_cannot_be_resolved(
    pages: list[dict[str, str]],
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        return httpx.Response(200, json={"data": pages})

    client = MetaOAuthClient(
        OAuthAppConfig("client", "secret", "https://example.test/meta"),
        "v24.0",
        "instagram",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OAuthProviderError, match=message):
        client.exchange_code("code-1")


def test_x_oauth_uses_pkce_and_requests_persistent_publish_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/2/users/me":
            return httpx.Response(
                200,
                json={"data": {"id": "x-1", "name": "Creator", "username": "creator"}},
            )
        return httpx.Response(
            200,
            json={"access_token": "access", "refresh_token": "refresh"},
        )

    client = XOAuthClient(
        OAuthAppConfig("client", "secret", "https://example.test/x"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    authorization = parse_qs(urlparse(client.authorization_url("state-1")).query)
    connection = client.exchange_code("code-1", "state-1")

    assert authorization["code_challenge_method"] == ["S256"]
    assert "tweet.write" in authorization["scope"][0]
    assert "media.write" in authorization["scope"][0]
    assert "offline.access" in authorization["scope"][0]
    assert connection.refresh_token == "refresh"  # noqa: S105 - synthetic test fixture
    assert connection.external_account_id == "x-1"
    assert connection.username == "creator"
