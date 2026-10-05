from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.youtube import (
    YouTubeOAuthClient,
    YouTubeOAuthConfig,
    YouTubePublishingAdapter,
)
from clipper.publishing import OAuthConnection, PublishRequest


def test_youtube_oauth_requests_upload_and_metrics_access() -> None:
    oauth = YouTubeOAuthClient(YouTubeOAuthConfig("client", "secret", "http://localhost/callback"))

    query = parse_qs(urlparse(oauth.authorization_url("state-1")).query)

    assert set(query["scope"][0].split()) == {
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    }
    assert query["include_granted_scopes"] == ["true"]
    assert query["prompt"] == ["consent"]


def test_encrypted_credentials_and_oauth_state_round_trip(tmp_path: Path) -> None:
    store = EncryptedCredentialStore(tmp_path)
    secret_value = "very-secret-refresh-token"  # noqa: S105 - synthetic test fixture
    connection = OAuthConnection(
        refresh_token=secret_value,
        access_token="temporary-access-value",  # noqa: S106
        external_account_id="provider-account-1",
    )

    store.save("account-1", connection)

    token_file = tmp_path / "credentials" / "account-1.token"
    assert b"very-secret-refresh-token" not in token_file.read_bytes()
    assert b"temporary-access-value" not in token_file.read_bytes()
    assert store.load("account-1") == connection
    assert store.open_state(store.seal_state("account-1")) == "account-1"


def test_youtube_adapter_refreshes_token_and_uses_resumable_upload(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video-content")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-123"})
        if request.method == "POST":
            assert request.headers["authorization"] == "Bearer access-123"
            return httpx.Response(200, headers={"Location": "https://upload.example/session"})
        assert request.content == b"video-content"
        return httpx.Response(200, json={"id": "video-123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    oauth = YouTubeOAuthClient(
        YouTubeOAuthConfig("client", "secret", "http://localhost/callback"),
        client=client,
    )
    adapter = YouTubePublishingAdapter(oauth, client=client)

    published = adapter.publish(
        PublishRequest(media, "Title", "Description", "public"),
        OAuthConnection("refresh-123"),
    )

    assert published.post_url == "https://www.youtube.com/watch?v=video-123"
    assert published.external_id == "video-123"
    assert published.status == "processing"
    assert [request.method for request in requests] == ["POST", "POST", "PUT"]


def test_youtube_adapter_refreshes_processing_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-123"})
        assert request.url.params["part"] == "status,processingDetails"
        assert request.url.params["id"] == "video-123"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "status": {"uploadStatus": "processed"},
                        "processingDetails": {"processingStatus": "succeeded"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubePublishingAdapter(
        YouTubeOAuthClient(
            YouTubeOAuthConfig("client", "secret", "http://localhost/callback"),
            client=client,
        ),
        client=client,
    )

    published = adapter.refresh("video-123", OAuthConnection("refresh-123"), "creator")

    assert published.status == "published"
    assert published.post_url == "https://www.youtube.com/watch?v=video-123"


def test_youtube_adapter_reads_metrics_from_an_existing_shorts_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-123"})
        assert request.url.params["part"] == "statistics"
        assert request.url.params["id"] == "video-123"
        assert request.headers["authorization"] == "Bearer access-123"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "statistics": {
                            "viewCount": "27",
                            "likeCount": "4",
                            "commentCount": "2",
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    oauth = YouTubeOAuthClient(
        YouTubeOAuthConfig("client", "secret", "http://localhost/callback"),
        client=client,
    )
    adapter = YouTubePublishingAdapter(oauth, client=client)

    metrics = adapter.metrics(
        None,
        "https://www.youtube.com/shorts/video-123",
        OAuthConnection("refresh-123"),
    )

    assert metrics.external_id == "video-123"
    assert metrics.views == 27
    assert metrics.likes == 4
    assert metrics.comments == 2
    assert [request.method for request in requests] == ["POST", "GET"]
