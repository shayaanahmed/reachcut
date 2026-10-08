from pathlib import Path

import httpx
import pytest

from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.publishing_http import ProviderApiError, trusted_upload_url
from clipper.providers.tiktok import TikTokPublishingAdapter
from clipper.providers.x import XPublishingAdapter
from clipper.publishing import OAuthConnection, PublishRequest


@pytest.fixture
def media(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"rendered-video")
    return path


@pytest.mark.parametrize(
    "url",
    [
        "http://upload.tiktokapis.com/video",
        "https://tiktokapis.com.evil.example/video",
        "https://user:password@upload.tiktokapis.com/video",
        "https://upload.tiktokapis.com:8443/video",
        "https://127.0.0.1/video",
    ],
)
def test_provider_upload_url_rejects_untrusted_destinations(url: str) -> None:
    with pytest.raises(ProviderApiError, match="untrusted upload URL"):
        trusted_upload_url(
            url,
            provider="TikTok",
            allowed_host_suffixes=("tiktokapis.com",),
        )


def test_provider_upload_url_accepts_expected_https_subdomain() -> None:
    url = "https://open-upload.tiktokapis.com/video?upload_id=one"

    assert (
        trusted_upload_url(
            url,
            provider="TikTok",
            allowed_host_suffixes=("tiktokapis.com",),
        )
        == url
    )


def test_tiktok_upload_stays_processing_until_status_returns_post_id(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/creator_info/query/"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "privacy_level_options": ["PUBLIC_TO_EVERYONE"],
                        "max_video_post_duration_sec": 300,
                    },
                    "error": {"code": "ok"},
                },
            )
        if request.url.path.endswith("/video/init/"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "publish_id": "publish-1",
                        "upload_url": "https://open-upload.tiktokapis.com/video",
                    },
                    "error": {"code": "ok"},
                },
            )
        if request.url.host == "open-upload.tiktokapis.com":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "PUBLISH_COMPLETE",
                    "publicaly_available_post_id": [12345],
                },
                "error": {"code": "ok"},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TikTokPublishingAdapter(client=client)
    connection = OAuthConnection(access_token="test-access-value")  # noqa: S106

    started = adapter.publish(
        PublishRequest(media, "Title", "Caption", "public", "creator"), connection
    )
    completed = adapter.refresh("publish-1", connection, "creator")

    assert started.status == "processing"
    assert started.external_id == "publish-1"
    assert completed.post_url == "https://www.tiktok.com/@creator/video/12345"


def test_instagram_resumable_upload_publishes_returned_permalink(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200)
        if request.method == "POST" and request.url.path.endswith("/ig-1/media"):
            return httpx.Response(
                200,
                json={
                    "id": "container-1",
                    "uri": "https://rupload.facebook.com/container-1",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.method == "POST" and request.url.path.endswith("/ig-1/media_publish"):
            return httpx.Response(200, json={"id": "media-1"})
        return httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/example/"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = InstagramPublishingAdapter("v24.0", client=client).publish(
        PublishRequest(media, "Title", "Caption"),
        OAuthConnection(access_token="test-access-value", external_account_id="ig-1"),  # noqa: S106
    )

    assert result.post_url == "https://www.instagram.com/reel/example/"
    assert result.external_id == "media-1"


def test_facebook_local_reel_upload_finishes_and_builds_url(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200)
        if request.url.params.get("upload_phase") == "start":
            return httpx.Response(
                200,
                json={
                    "video_id": "video-1",
                    "upload_url": "https://rupload.facebook.com/video-1",
                },
            )
        return httpx.Response(200, json={"success": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = FacebookPublishingAdapter("v24.0", client=client).publish(
        PublishRequest(media, "Title", "Caption"),
        OAuthConnection(access_token="test-access-value", external_account_id="page-1"),  # noqa: S106
    )

    assert result.post_url == "https://www.facebook.com/reel/video-1"


def test_x_chunked_upload_creates_post_with_media(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/initialize"):
            return httpx.Response(200, json={"data": {"id": "media-1"}})
        if request.url.path.endswith("/append"):
            return httpx.Response(204)
        if request.url.path.endswith("/finalize"):
            return httpx.Response(200, json={"data": {"id": "media-1"}})
        return httpx.Response(201, json={"data": {"id": "post-1"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = XPublishingAdapter(client=client).publish(
        PublishRequest(media, "Title", "Caption", account_username="creator"),
        OAuthConnection(access_token="test-access-value"),  # noqa: S106
    )

    assert result.post_url == "https://x.com/creator/status/post-1"
