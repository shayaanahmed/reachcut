from pathlib import Path

import httpx
import pytest

from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.publishing_http import ProviderApiError, trusted_upload_url
from clipper.providers.tiktok import TikTokPublishingAdapter, _tiktok_chunk_plan
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
            assert request.content == b"rendered-video"
            assert request.headers["content-length"] == str(len(b"rendered-video"))
            assert request.headers["content-range"] == "bytes 0-13/14"
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


def test_instagram_local_resumable_upload_publishes_returned_permalink(media: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "rupload.facebook.com":
            assert request.content == b"rendered-video"
            assert request.headers["authorization"] == "OAuth test-access-value"
            assert "content-type" not in request.headers
            assert request.headers["content-length"] == "14"
            assert "transfer-encoding" not in request.headers
            assert request.headers["file_size"] == "14"
            return httpx.Response(200)
        assert request.url.host == "graph.facebook.com"
        if request.method == "POST" and request.url.path.endswith("/ig-1/media"):
            assert request.url.params["media_type"] == "REELS"
            assert request.url.params["upload_type"] == "resumable"
            assert "video_url" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "id": "container-1",
                    "uri": "https://rupload.facebook.com/ig-api-upload/container-1",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.method == "POST" and request.url.path.endswith("/ig-1/media_publish"):
            return httpx.Response(200, json={"id": "media-1"})
        return httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/example/"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = InstagramPublishingAdapter("v26.0", client=client).publish(
        PublishRequest(media, "Title", "Caption"),
        OAuthConnection(access_token="test-access-value", external_account_id="ig-1"),  # noqa: S106
    )

    assert result.post_url == "https://www.instagram.com/reel/example/"
    assert result.external_id == "media-1"
    assert {request.url.host for request in requests} == {
        "graph.facebook.com",
        "rupload.facebook.com",
    }


def test_instagram_rejects_old_direct_login_credentials(media: Path) -> None:
    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )

    with pytest.raises(ProviderApiError, match="Reconnect the account through Facebook Login"):
        adapter.publish(
            PublishRequest(media, "Title", "Caption"),
            OAuthConnection(
                access_token="direct-token",  # noqa: S106
                refresh_token="direct-token",  # noqa: S106
                external_account_id="ig-1",
            ),
        )


def test_instagram_metrics_combines_media_counts_and_reel_views() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "test-access-value"  # noqa: S105
        if request.url.path.endswith("/media-1/insights"):
            assert request.url.params["metric"] == "views"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "views",
                            "period": "lifetime",
                            "values": [{"value": 1250}],
                        }
                    ]
                },
            )
        assert request.url.params["fields"] == "like_count,comments_count"
        return httpx.Response(200, json={"id": "media-1", "like_count": 88, "comments_count": 9})

    metrics = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).metrics(
        "media-1",
        "https://www.instagram.com/reel/example/",
        OAuthConnection(access_token="test-access-value", external_account_id="ig-1"),  # noqa: S106
    )

    assert (metrics.external_id, metrics.views, metrics.likes, metrics.comments) == (
        "media-1",
        1250,
        88,
        9,
    )


def test_instagram_metrics_explains_missing_insights_permission() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/insights"):
            return httpx.Response(400, json={"error": {"code": 10}})
        return httpx.Response(200, json={"like_count": 0, "comments_count": 0})

    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderApiError, match="instagram_manage_insights"):
        adapter.metrics(
            "media-1",
            None,
            OAuthConnection(access_token="test-access-value", external_account_id="ig-1"),  # noqa: S106
        )


def test_facebook_local_reel_upload_finishes_and_builds_url(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rupload.facebook.com":
            assert request.content == b"rendered-video"
            assert request.headers["content-type"] == "application/octet-stream"
            assert request.headers["content-length"] == str(len(b"rendered-video"))
            assert "transfer-encoding" not in request.headers
            assert request.headers["file_size"] == str(len(b"rendered-video"))
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
    result = FacebookPublishingAdapter("v26.0", client=client).publish(
        PublishRequest(media, "Title", "Caption"),
        OAuthConnection(access_token="test-access-value", external_account_id="page-1"),  # noqa: S106
    )

    assert result.post_url == "https://www.facebook.com/reel/video-1"


def test_facebook_metrics_reads_reel_counts_and_can_resolve_id_from_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/video-1")
        assert request.url.params["access_token"] == "test-access-value"  # noqa: S105
        assert "views" in request.url.params["fields"]
        return httpx.Response(
            200,
            json={
                "id": "video-1",
                "views": 2400,
                "likes": {"data": [], "summary": {"total_count": 120}},
                "comments": {"data": [], "summary": {"total_count": 15}},
            },
        )

    metrics = FacebookPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).metrics(
        None,
        "https://www.facebook.com/reel/video-1/",
        OAuthConnection(access_token="test-access-value", external_account_id="page-1"),  # noqa: S106
    )

    assert (metrics.external_id, metrics.views, metrics.likes, metrics.comments) == (
        "video-1",
        2400,
        120,
        15,
    )


def test_x_chunked_upload_creates_post_with_media(media: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/initialize"):
            return httpx.Response(200, json={"data": {"id": "media-1"}})
        if request.url.path.endswith("/append"):
            assert b"rendered-video" in request.content
            assert request.headers["content-type"].startswith("multipart/form-data;")
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


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (4 * 1024 * 1024, (4 * 1024 * 1024, 1)),
        (64 * 1024 * 1024, (64 * 1024 * 1024, 1)),
        (70 * 1024 * 1024, (32 * 1024 * 1024, 2)),
        (100 * 1024 * 1024, (32 * 1024 * 1024, 3)),
    ],
)
def test_tiktok_chunk_plan_keeps_the_remainder_in_the_final_chunk(
    size: int,
    expected: tuple[int, int],
) -> None:
    assert _tiktok_chunk_plan(size) == expected


def test_instagram_upload_error_exposes_container_diagnostics_without_publishing(
    media: Path,
) -> None:
    published = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal published
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(
                400,
                json={
                    "debug_info": {
                        "retriable": False,
                        "type": "ProcessingFailedError",
                        "message": "Request processing failed",
                    }
                },
                headers={"x-fb-trace-id": "trace-123"},
            )
        if request.method == "POST" and request.url.path.endswith("/ig-1/media"):
            return httpx.Response(
                200,
                json={
                    "id": "container-1",
                    "uri": "https://rupload.facebook.com/ig-api-upload/container-1",
                },
            )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "video_status": {
                        "uploading_phase": {
                            "status": "error",
                            "bytes_transferred": 0,
                            "errors": [
                                {"code": 1363008, "message": "OIL Error[FILE_NOT_FOUND: 6]"}
                            ],
                        }
                    }
                },
            )
        published = True
        raise AssertionError("A failed upload must not publish")

    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        compatibility_encoder=None,
    )
    with pytest.raises(ProviderApiError) as error:
        adapter.publish(
            PublishRequest(media, "Title", "Caption"),
            OAuthConnection(access_token="test-value", external_account_id="ig-1"),  # noqa: S106
        )
    assert "container-1" in str(error.value)
    assert "1363008" in str(error.value)
    assert "bytes transferred: 0" in str(error.value)
    assert "trace-123" in str(error.value)
    assert not published


@pytest.mark.parametrize("second_upload_fails", [False, True])
def test_instagram_reencodes_rejected_video_once_before_publishing(
    media: Path, second_upload_fails: bool
) -> None:
    containers = 0
    uploads: list[bytes] = []
    publications: list[str] = []
    copies: list[Path] = []

    def encode(source: Path, output: Path) -> None:
        assert source == media
        copies.append(output)
        output.write_bytes(b"compatible-video")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal containers
        if request.url.host == "rupload.facebook.com":
            uploads.append(request.content)
            return httpx.Response(400 if len(uploads) == 1 or second_upload_fails else 200)
        if request.method == "POST" and request.url.path.endswith("/ig-1/media"):
            containers += 1
            return httpx.Response(
                200,
                json={
                    "id": f"container-{containers}",
                    "uri": f"https://rupload.facebook.com/ig-api-upload/container-{containers}",
                },
            )
        if request.method == "GET" and "/container-" in request.url.path:
            if len(uploads) == 1 or second_upload_fails:
                return httpx.Response(
                    200,
                    json={
                        "video_status": {
                            "uploading_phase": {
                                "status": "error",
                                "bytes_transferred": 0,
                                "errors": [
                                    {"code": 1363008, "message": "OIL Error[FILE_NOT_FOUND: 6]"}
                                ],
                            }
                        }
                    },
                )
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.url.path.endswith("/media_publish"):
            publications.append(request.url.params["creation_id"])
            return httpx.Response(200, json={"id": "media-1"})
        return httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/test/"})

    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        compatibility_encoder=encode,
    )
    request = PublishRequest(media, "Title", "Caption")
    connection = OAuthConnection(access_token="test-value", external_account_id="ig-1")  # noqa: S106
    if second_upload_fails:
        with pytest.raises(ProviderApiError, match="compatibility upload also failed"):
            adapter.publish(request, connection)
    else:
        assert adapter.publish(request, connection).external_id == "media-1"
    assert containers == 2
    assert uploads == [b"rendered-video", b"compatible-video"]
    assert publications == ([] if second_upload_fails else ["container-2"])
    assert media.read_bytes() == b"rendered-video"
    assert len(copies) == 1 and not copies[0].exists()


def test_instagram_never_retries_a_failed_publish_call(media: Path) -> None:
    publish_calls = 0

    def encode(source: Path, output: Path) -> None:
        raise AssertionError("A publishing failure must not trigger re-encoding or another post")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal publish_calls
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200)
        if request.url.path.endswith("/ig-1/media"):
            return httpx.Response(
                200,
                json={
                    "id": "container-1",
                    "uri": "https://rupload.facebook.com/container-1",
                },
            )
        if request.method == "GET":
            return httpx.Response(200, json={"status_code": "FINISHED"})
        publish_calls += 1
        return httpx.Response(500, json={"error": {"message": "Temporary publishing failure"}})

    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        compatibility_encoder=encode,
    )
    with pytest.raises(ProviderApiError, match="Temporary publishing failure"):
        adapter.publish(
            PublishRequest(media, "Title", "Caption"),
            OAuthConnection(access_token="test-value", external_account_id="ig-1"),  # noqa: S106
        )
    assert publish_calls == 1


@pytest.mark.parametrize(("error_code", "transferred"), [(190, 0), (1363008, 100), (1363010, 0)])
def test_instagram_does_not_reencode_unrelated_upload_failures(
    media: Path, error_code: int, transferred: int
) -> None:
    def encode(source: Path, output: Path) -> None:
        raise AssertionError("Only the verified zero-byte FILE_NOT_FOUND rejection may retry")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(400)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "container-1",
                    "uri": "https://rupload.facebook.com/container-1",
                },
            )
        return httpx.Response(
            200,
            json={
                "video_status": {
                    "uploading_phase": {
                        "status": "error",
                        "bytes_transferred": transferred,
                        "errors": [{"code": error_code, "message": "OIL Error[FILE_NOT_FOUND: 6]"}],
                    }
                }
            },
        )

    adapter = InstagramPublishingAdapter(
        "v26.0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        compatibility_encoder=encode,
    )
    with pytest.raises(ProviderApiError, match="Instagram video upload failed"):
        adapter.publish(
            PublishRequest(media, "Title", "Caption"),
            OAuthConnection(access_token="test-value", external_account_id="ig-1"),  # noqa: S106
        )
