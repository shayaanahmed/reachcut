from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from clipper.providers.social_oauth import (
    FacebookOAuthClient,
    InstagramOAuthClient,
    OAuthAppConfig,
    TikTokOAuthClient,
    XOAuthClient,
)
from clipper.publishing import OAuthProviderError


def test_meta_oauth_requires_business_login_configuration_id() -> None:
    config = OAuthAppConfig("client", "secret", "http://localhost/callback")

    assert not InstagramOAuthClient(config, "v26.0").configured
    assert not FacebookOAuthClient(config, "v26.0").configured


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
        assert "code_verifier" in request.content.decode()
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
    connection = client.exchange_code("code-1", "state-1")

    assert "video.publish" in authorization["scope"][0]
    assert authorization["code_challenge_method"] == ["S256"]
    assert authorization["code_challenge"]
    assert connection.access_token == "access"  # noqa: S105 - synthetic test fixture
    assert connection.refresh_token == "refresh"  # noqa: S105 - synthetic test fixture
    assert connection.external_account_id == "creator-1"
    assert connection.display_name == "Creator One"


def test_instagram_oauth_resolves_professional_account_from_facebook_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        assert request.url.path.endswith("/me/accounts")
        assert "instagram_business_account" in request.url.params["fields"]
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

    client = InstagramOAuthClient(
        OAuthAppConfig(
            "client",
            "secret",
            "https://example.test/instagram",
            "instagram-config",
        ),
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    authorization = parse_qs(urlparse(client.authorization_url("state-1")).query)

    connection = client.exchange_code("code-1")

    assert urlparse(client.authorization_url("state-1")).hostname == "www.facebook.com"
    assert authorization["config_id"] == ["instagram-config"]
    assert authorization["override_default_response_type"] == ["true"]
    assert "scope" not in authorization
    assert authorization["auth_type"] == ["rerequest"]
    assert authorization["return_scopes"] == ["true"]
    assert connection.access_token == "page-token"  # noqa: S105 - synthetic test fixture
    assert connection.refresh_token == ""
    assert connection.external_account_id == "instagram-1"
    assert connection.display_name == "Creator Studio"
    assert connection.username == "creator"
    assert connection.profile_url == "https://www.instagram.com/creator/"


def test_instagram_oauth_explains_when_page_has_no_linked_professional_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        return httpx.Response(
            200,
            json={"data": [{"id": "page-1", "access_token": "page-token"}]},
        )

    client = InstagramOAuthClient(
        OAuthAppConfig("client", "secret", "http://localhost/instagram", "instagram-config"),
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OAuthProviderError, match="linked Instagram professional account"):
        client.exchange_code("code-1")


def test_instagram_oauth_reports_exact_missing_permissions_when_no_page_is_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        if request.url.path.endswith("/me/permissions"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"permission": "pages_show_list", "status": "granted"},
                        {"permission": "instagram_basic", "status": "granted"},
                        {"permission": "pages_read_engagement", "status": "declined"},
                    ]
                },
            )
        return httpx.Response(200, json={"data": []})

    client = InstagramOAuthClient(
        OAuthAppConfig("client", "secret", "http://localhost/instagram", "instagram-config"),
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OAuthProviderError) as error:
        client.exchange_code("code-1")

    assert "instagram_content_publish" in str(error.value)
    assert "business_management" in str(error.value)
    assert "pages_read_engagement" in str(error.value)
    assert "User access token" in str(error.value)


def test_facebook_oauth_explains_when_no_page_is_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "user-token"})
        if request.url.path.endswith("/me/permissions"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"permission": "business_management", "status": "granted"},
                        {"permission": "pages_show_list", "status": "granted"},
                        {"permission": "pages_read_engagement", "status": "granted"},
                        {"permission": "pages_manage_posts", "status": "granted"},
                    ]
                },
            )
        return httpx.Response(200, json={"data": []})

    client = FacebookOAuthClient(
        OAuthAppConfig(
            "client",
            "secret",
            "https://example.test/facebook",
            "facebook-config",
        ),
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    authorization = parse_qs(urlparse(client.authorization_url("state-1")).query)

    assert authorization["config_id"] == ["facebook-config"]
    assert authorization["override_default_response_type"] == ["true"]
    assert "scope" not in authorization
    assert authorization["auth_type"] == ["rerequest"]
    assert authorization["return_scopes"] == ["true"]
    with pytest.raises(OAuthProviderError, match="Meta granted the required Facebook Page"):
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
