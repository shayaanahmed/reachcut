from urllib.parse import parse_qs, urlparse

import httpx

from clipper.providers.social_oauth import (
    MetaOAuthClient,
    OAuthAppConfig,
    TikTokOAuthClient,
    XOAuthClient,
)


def test_tiktok_oauth_exchanges_code_for_refreshable_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
                        "access_token": "page-token",
                        "instagram_business_account": {"id": "instagram-1"},
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


def test_x_oauth_uses_pkce_and_requests_persistent_publish_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
