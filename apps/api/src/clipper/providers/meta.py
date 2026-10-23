from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import httpx

from clipper.media.errors import MediaError
from clipper.media.instagram import encode_instagram_video
from clipper.providers.publishing_http import (
    ProviderApiError,
    ProviderPublishingPermissionError,
    ProviderUploadRejected,
    PublishingHttpClient,
    local_video_size,
    trusted_upload_url,
)
from clipper.publishing import OAuthConnection, ProviderMetrics, PublishedPost, PublishRequest
from clipper.publishing.permissions import instagram_deletion_issue, instagram_publishing_issue


class _InstagramUploadRejected(ProviderApiError):
    def __init__(self, message: str, *, compatibility_retry: bool) -> None:
        super().__init__(message)
        self.compatibility_retry = compatibility_retry


class InstagramPublishingAdapter(PublishingHttpClient):
    def __init__(
        self,
        graph_version: str,
        *,
        client: httpx.Client | None = None,
        compatibility_encoder: Callable[[Path, Path], None] | None = encode_instagram_video,
    ) -> None:
        super().__init__(client)
        self._base = f"https://graph.facebook.com/{graph_version}"
        self._compatibility_encoder = compatibility_encoder

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        try:
            return self._publish(request, connection)
        except _InstagramUploadRejected as error:
            if not error.compatibility_retry or self._compatibility_encoder is None:
                raise ProviderUploadRejected(str(error)) from error
        # A rejected container cannot be reused. Only retry before media_publish,
        # with a new container and a temporary encoding; never retry publishing.
        with TemporaryDirectory(prefix="reachcut-instagram-") as directory:
            compatible = Path(directory) / "compatible.mp4"
            try:
                self._compatibility_encoder(request.media_path, compatible)
            except MediaError as error:
                raise ProviderUploadRejected(str(error)) from error
            try:
                return self._publish(replace(request, media_path=compatible), connection)
            except (ProviderUploadRejected, _InstagramUploadRejected) as error:
                if isinstance(error, ProviderPublishingPermissionError):
                    raise
                raise ProviderUploadRejected(
                    f"Instagram compatibility upload also failed: {error}"
                ) from error
            except ProviderApiError:
                raise

    def _publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        if connection.refresh_token and connection.refresh_token == connection.access_token:
            raise ProviderPublishingPermissionError(
                "Instagram is connected with the old direct-login credentials. Reconnect the "
                "account through Facebook Login to enable local video upload."
            )
        account_id, token = _meta_credentials(connection, "Instagram")
        issue = instagram_publishing_issue(connection)
        if issue:
            raise ProviderPublishingPermissionError(issue)
        size = local_video_size(request.media_path, "Instagram")
        stage = "checking the linked account"
        publish_attempted = False
        container_id = None
        media_id = None
        try:
            with self.client_session() as client:
                if connection.parent_page_id:
                    linked = client.get(
                        f"{self._base}/{connection.parent_page_id}",
                        params={"fields": "instagram_business_account"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    linked.raise_for_status()
                    account = linked.json().get("instagram_business_account")
                    if not isinstance(account, dict) or str(account.get("id")) != account_id:
                        raise ProviderPublishingPermissionError(
                            "Instagram publishing authorization does not match "
                            "the selected account. "
                            "The saved Facebook Page no longer exposes this Instagram account. "
                            "In Meta Business Suite, link the intended Instagram professional "
                            "account to the correct Page, then reconnect that account in Accounts "
                            "and grant publishing access to it. No video was uploaded."
                        )
                stage = "creating the upload container"
                created = client.post(
                    f"{self._base}/{account_id}/media",
                    params={
                        "media_type": "REELS",
                        "upload_type": "resumable",
                        "caption": request.description[:2200],
                        "access_token": token,
                    },
                )
                created.raise_for_status()
                payload = created.json()
                container_id = payload.get("id")
                upload_uri = payload.get("uri")
                if not container_id or not upload_uri:
                    raise ProviderApiError("Instagram did not return an upload container")
                upload_uri = trusted_upload_url(
                    upload_uri,
                    provider="Instagram",
                    allowed_host_suffixes=("facebook.com",),
                )
                stage = "transferring video to the container"
                with request.media_path.open("rb") as media:
                    uploaded = client.post(
                        upload_uri,
                        headers={
                            "Authorization": f"OAuth {token}",
                            "Content-Length": str(size),
                            "offset": "0",
                            "file_size": str(size),
                        },
                        content=media,
                        timeout=None,
                    )
                    try:
                        uploaded.raise_for_status()
                    except httpx.HTTPStatusError as error:
                        raise _instagram_upload_error(
                            client, self._base, str(container_id), token, error
                        ) from error
                stage = "processing the upload container"
                _wait_for_instagram_container(client, self._base, str(container_id), token)
                stage = "publishing the Reel"
                publish_attempted = True
                published = client.post(
                    f"{self._base}/{account_id}/media_publish",
                    params={"creation_id": container_id, "access_token": token},
                )
                published.raise_for_status()
                media_id = published.json().get("id")
                if not media_id:
                    raise ProviderApiError("Instagram did not return a media ID")
                if request.on_upload_started:
                    request.on_upload_started(str(media_id))
                stage = "loading the published Reel link"
                details = client.get(
                    f"{self._base}/{media_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                details.raise_for_status()
                permalink = details.json().get("permalink")
        except _InstagramUploadRejected:
            raise  # Preserve the existing safe encoding retry before media_publish.
        except ProviderPublishingPermissionError:
            raise
        except httpx.HTTPError as error:
            if media_id:
                return PublishedPost(post_url=None, external_id=str(media_id), status="processing")
            if isinstance(error, httpx.HTTPStatusError) and _is_permission_error(error.response):
                raise ProviderPublishingPermissionError(
                    f"Instagram publishing authorization was denied while {stage} "
                    "(Meta code 10/200). "
                    "Reconnect the intended Instagram account and its linked Facebook Page in "
                    "Accounts. Grant instagram_basic, instagram_content_publish and "
                    "pages_read_engagement for that account in the Meta login configuration. "
                    "The app may also need the appropriate Meta access level. "
                    "No post was published by this rejected request."
                ) from error
            message = str(self.raise_error(f"Instagram failed while {stage}", error))
            if not publish_attempted:
                raise ProviderUploadRejected(message + ". No publish request was sent.") from error
            raise ProviderApiError(
                f"{message}. Publish outcome needs verification; container {container_id}. "
                "Do not upload again until the destination has been checked."
            ) from error
        except ProviderApiError as error:
            if not publish_attempted:
                raise ProviderUploadRejected(
                    str(error) + ". No publish request was sent."
                ) from error
            raise
        return PublishedPost(
            post_url=str(permalink) if permalink else None,
            external_id=str(media_id),
            status="published" if permalink else "processing",
        )

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        del account_username
        _, token = _meta_credentials(connection, "Instagram")
        try:
            with self.client_session() as client:
                response = client.get(
                    f"{self._base}/{external_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise self.raise_error("Instagram status check failed", error) from error
        permalink = response.json().get("permalink")
        return PublishedPost(
            post_url=permalink,
            external_id=external_id,
            status="published" if permalink else "processing",
        )

    def delete_post(
        self, external_id: str | None, post_url: str | None, connection: OAuthConnection
    ) -> None:
        if not external_id:
            raise ProviderApiError("Instagram deletion requires the original published media ID")
        issue = instagram_deletion_issue(connection)
        if issue:
            raise ProviderApiError(issue)
        _delete_meta_media(self, self._base, external_id, connection.management_access_token)

    def metrics(
        self,
        external_id: str | None,
        post_url: str | None,
        connection: OAuthConnection,
    ) -> ProviderMetrics:
        del post_url
        if not external_id:
            raise ProviderApiError("Instagram publication has no media ID")
        _, token = _meta_credentials(connection, "Instagram")
        try:
            with self.client_session() as client:
                media = client.get(
                    f"{self._base}/{external_id}",
                    params={
                        "fields": "like_count,comments_count",
                        "access_token": token,
                    },
                )
                media.raise_for_status()
                insights = client.get(
                    f"{self._base}/{external_id}/insights",
                    params={"metric": "views", "access_token": token},
                )
                insights.raise_for_status()
        except httpx.HTTPStatusError as error:
            if _is_permission_error(error.response):
                raise ProviderApiError(
                    "Instagram metrics sync requires instagram_manage_insights. Add it to the "
                    "Meta login configuration, then reconnect the Instagram account."
                ) from error
            raise self.raise_error("Instagram metrics sync failed", error) from error
        except httpx.HTTPError as error:
            raise self.raise_error("Instagram metrics sync failed", error) from error
        payload = media.json()
        return ProviderMetrics(
            external_id=external_id,
            views=_insight_count(insights.json(), "views"),
            likes=_count(payload.get("like_count")),
            comments=_count(payload.get("comments_count")),
        )


class FacebookPublishingAdapter(PublishingHttpClient):
    def __init__(self, graph_version: str, *, client: httpx.Client | None = None) -> None:
        super().__init__(client)
        self._base = f"https://graph.facebook.com/{graph_version}"

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        page_id, token = _meta_credentials(connection, "Facebook")
        size = local_video_size(request.media_path, "Facebook")
        try:
            with self.client_session() as client:
                started = client.post(
                    f"{self._base}/{page_id}/video_reels",
                    params={"upload_phase": "start", "access_token": token},
                )
                started.raise_for_status()
                payload = started.json()
                video_id = payload.get("video_id")
                upload_url = payload.get("upload_url")
                if not video_id or not upload_url:
                    raise ProviderApiError("Facebook did not return a Reel upload session")
                upload_url = trusted_upload_url(
                    upload_url,
                    provider="Facebook",
                    allowed_host_suffixes=("facebook.com",),
                )
                if request.on_upload_started:
                    request.on_upload_started(str(video_id))
                with request.media_path.open("rb") as media:
                    uploaded = client.post(
                        upload_url,
                        headers={
                            "Authorization": f"OAuth {token}",
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(size),
                            "offset": "0",
                            "file_size": str(size),
                        },
                        content=media,
                        timeout=None,
                    )
                    uploaded.raise_for_status()
                finished = client.post(
                    f"{self._base}/{page_id}/video_reels",
                    params={
                        "upload_phase": "finish",
                        "video_id": video_id,
                        "video_state": "PUBLISHED",
                        "description": request.description,
                        "access_token": token,
                    },
                )
                finished.raise_for_status()
                if finished.json().get("success") is not True:
                    raise ProviderApiError("Facebook did not accept the Reel publish request")
        except httpx.HTTPError as error:
            raise self.raise_error("Facebook Reel publishing failed", error) from error
        # Finish acknowledges the request; Facebook still processes asynchronously.
        # Persist its ID before asking for status or a permalink, which can lag.
        return PublishedPost(post_url=None, external_id=str(video_id), status="processing")

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        del account_username
        _, token = _meta_credentials(connection, "Facebook")
        try:
            with self.client_session() as client:
                response = client.get(
                    f"{self._base}/{external_id}",
                    params={"fields": "status"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise self.raise_error(
                "Facebook status check failed; the existing upload ID is saved. "
                "Do not upload again. If this persists, reconnect the original Page in Accounts",
                error,
            ) from error
        status = response.json().get("status", {})
        publishing = status.get("publishing_phase", {})
        phases = [
            status.get(name, {})
            for name in ("uploading_phase", "processing_phase", "publishing_phase")
        ]
        if (
            status.get("video_status") in {"error", "upload_failed", "expired"}
            or any(phase.get("status") in {"error", "failed"} for phase in phases)
            or publishing.get("publish_status") == "error"
        ):
            return PublishedPost(
                post_url=None,
                external_id=external_id,
                status="failed",
                error="Facebook reported that Reel uploading, processing or publishing failed. "
                "Check the video in the original Page before trying another upload.",
            )
        published = publishing.get("publish_status") == "published" or (
            status.get("video_status") == "ready" and publishing.get("status") == "complete"
        )
        return PublishedPost(
            post_url=f"https://www.facebook.com/reel/{external_id}" if published else None,
            external_id=external_id,
            status="published" if published else "processing",
        )

    def update_post(
        self,
        external_id: str | None,
        post_url: str | None,
        title: str,
        description: str,
        connection: OAuthConnection,
    ) -> None:
        del title  # Reels expose a caption; do not claim an unsupported title edit.
        video_id = external_id or _facebook_reel_id(post_url)
        if not video_id:
            raise ProviderApiError("Facebook post has no recognizable video ID")
        _, token = _meta_credentials(connection, "Facebook")
        try:
            with self.client_session() as client:
                response = client.post(
                    f"{self._base}/{video_id}",
                    data={"description": description},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                verified = client.get(
                    f"{self._base}/{video_id}",
                    params={"fields": "description"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                verified.raise_for_status()
                if verified.json().get("description", "") != description:
                    raise ProviderApiError(
                        "Facebook did not confirm the caption change. Open the post to check it."
                    )
        except httpx.HTTPError as error:
            raise self.raise_error("Facebook update failed", error) from error

    def delete_post(
        self, external_id: str | None, post_url: str | None, connection: OAuthConnection
    ) -> None:
        video_id = external_id or _facebook_reel_id(post_url)
        if not video_id:
            raise ProviderApiError("Facebook post has no recognizable video ID")
        _, token = _meta_credentials(connection, "Facebook")
        _delete_meta_media(self, self._base, video_id, token)

    def metrics(
        self,
        external_id: str | None,
        post_url: str | None,
        connection: OAuthConnection,
    ) -> ProviderMetrics:
        video_id = external_id or _facebook_reel_id(post_url)
        if not video_id:
            raise ProviderApiError("Facebook publication has no recognizable Reel ID")
        _, token = _meta_credentials(connection, "Facebook")
        try:
            with self.client_session() as client:
                response = client.get(
                    f"{self._base}/{video_id}",
                    params={
                        "fields": (
                            "views,likes.limit(0).summary(true),comments.limit(0).summary(true)"
                        ),
                        "access_token": token,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise self.raise_error("Facebook metrics sync failed", error) from error
        payload = response.json()
        resolved_id = str(payload.get("id") or video_id)
        return ProviderMetrics(
            external_id=resolved_id,
            views=_count(payload.get("views")),
            likes=_summary_count(payload, "likes"),
            comments=_summary_count(payload, "comments"),
        )


def _meta_credentials(connection: OAuthConnection, platform: str) -> tuple[str, str]:
    if not connection.external_account_id or not connection.access_token:
        raise ProviderApiError(f"{platform} requires an account ID and access token")
    return connection.external_account_id, connection.access_token


def _facebook_reel_id(post_url: str | None) -> str | None:
    if not post_url:
        return None
    parts = [part for part in urlparse(post_url).path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "reel":
        return parts[1]
    return None


def _count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


def _summary_count(payload: object, field: str) -> int:
    if not isinstance(payload, dict):
        return 0
    item = payload.get(field)
    if not isinstance(item, dict):
        return 0
    summary = item.get("summary")
    if not isinstance(summary, dict):
        return 0
    return _count(summary.get("total_count"))


def _insight_count(payload: object, metric: str) -> int:
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if not isinstance(data, list):
        return 0
    for item in data:
        if not isinstance(item, dict) or item.get("name") != metric:
            continue
        total = item.get("total_value")
        if isinstance(total, dict):
            return _count(total.get("value"))
        values = item.get("values")
        if isinstance(values, list) and values and isinstance(values[-1], dict):
            return _count(values[-1].get("value"))
    return 0


def _is_permission_error(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") in {10, 200}


def _instagram_upload_error(
    client: httpx.Client,
    base_url: str,
    container_id: str,
    token: str,
    error: httpx.HTTPStatusError,
) -> _InstagramUploadRejected:
    """Enrich rupload's generic failure with its unpublished container diagnostics."""
    message = str(
        PublishingHttpClient.raise_error(
            f"Instagram video upload failed (container {container_id})", error
        )
    )
    trace = error.response.headers.get("x-fb-trace-id") or error.response.headers.get(
        "x-fb-request-id"
    )
    if trace:
        message += f"; Meta trace: {trace}"
    compatibility_retry = False
    try:
        status = client.get(
            f"{base_url}/{container_id}",
            params={"fields": "status_code,status,video_status", "access_token": token},
        )
        status.raise_for_status()
        payload = status.json()
        video_status = payload.get("video_status")
        if isinstance(video_status, dict):
            uploading = video_status.get("uploading_phase")
            if isinstance(uploading, dict):
                if "bytes_transferred" in uploading:
                    message += f"; bytes transferred: {uploading['bytes_transferred']}"
                issues = uploading.get("errors")
                if isinstance(issues, list):
                    for issue in issues[:3]:
                        if isinstance(issue, dict):
                            if (
                                issue.get("code") == 1363008
                                and uploading.get("bytes_transferred") == 0
                                and "FILE_NOT_FOUND" in str(issue.get("message", ""))
                            ):
                                compatibility_retry = True
                            message += (
                                f"; Meta {issue.get('code', 'error')}: {issue.get('message', '')}"
                            )
    except (httpx.HTTPError, ValueError, AttributeError):
        # A secondary diagnostic request must never hide the upload failure.
        pass
    return _InstagramUploadRejected(message, compatibility_retry=compatibility_retry)


def _wait_for_instagram_container(
    client: httpx.Client,
    base_url: str,
    container_id: str,
    token: str,
) -> None:
    for _ in range(60):
        status = client.get(
            f"{base_url}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
        )
        status.raise_for_status()
        payload = status.json()
        if payload.get("status_code") == "FINISHED":
            return
        if payload.get("status_code") in {"ERROR", "EXPIRED"}:
            raise ProviderApiError(f"Instagram media processing failed: {payload.get('status')}")
        time.sleep(2)
    raise ProviderApiError("Instagram media processing did not finish within two minutes")


def _delete_meta_media(adapter: PublishingHttpClient, base: str, media_id: str, token: str) -> None:
    try:
        with adapter.client_session() as client:
            response = client.delete(
                f"{base}/{media_id}", headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            if response.json().get("success") is not True:
                raise ProviderApiError("Meta did not confirm deletion; the local post is preserved")
    except httpx.HTTPStatusError as error:
        try:
            detail = error.response.json().get("error", {})
        except ValueError:
            detail = {}
        if detail.get("code") == 100 and detail.get("error_subcode") == 33:
            raise ProviderApiError(
                "Deletion was not confirmed. Meta cannot access this media for deletion "
                "(code 100/33). It may be missing, belong to another account, or require "
                "different permissions or an API version that supports deletion. "
                "Open the original post on its platform to check it. "
                "The local record and metrics were preserved."
            ) from error
        raise adapter.raise_error("Post deletion failed", error) from error
    except httpx.HTTPError as error:
        raise adapter.raise_error("Post deletion failed", error) from error
