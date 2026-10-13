from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from clipper.providers.publishing_http import (
    ProviderApiError,
    PublishingHttpClient,
    local_video_size,
    trusted_upload_url,
)
from clipper.publishing import OAuthConnection, ProviderMetrics, PublishedPost, PublishRequest


class InstagramPublishingAdapter(PublishingHttpClient):
    def __init__(self, graph_version: str, *, client: httpx.Client | None = None) -> None:
        super().__init__(client)
        self._base = f"https://graph.facebook.com/{graph_version}"

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        if connection.refresh_token and connection.refresh_token == connection.access_token:
            raise ProviderApiError(
                "Instagram is connected with the old direct-login credentials. Reconnect the "
                "account through Facebook Login to enable local video upload."
            )
        account_id, token = _meta_credentials(connection, "Instagram")
        size = local_video_size(request.media_path, "Instagram")
        try:
            with self.client_session() as client:
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
                    uploaded.raise_for_status()
                _wait_for_instagram_container(client, self._base, str(container_id), token)
                published = client.post(
                    f"{self._base}/{account_id}/media_publish",
                    params={"creation_id": container_id, "access_token": token},
                )
                published.raise_for_status()
                media_id = published.json().get("id")
                if not media_id:
                    raise ProviderApiError("Instagram did not return a media ID")
                details = client.get(
                    f"{self._base}/{media_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                details.raise_for_status()
                permalink = details.json().get("permalink")
        except httpx.HTTPError as error:
            raise self.raise_error("Instagram Reel publishing failed", error) from error
        if not permalink:
            raise ProviderApiError("Instagram published the Reel without returning a permalink")
        return PublishedPost(post_url=str(permalink), external_id=str(media_id))

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
        return PublishedPost(post_url=response.json().get("permalink"), external_id=external_id)

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
                details = client.get(
                    f"{self._base}/{video_id}",
                    params={"fields": "permalink_url", "access_token": token},
                )
                details.raise_for_status()
                permalink = details.json().get("permalink_url")
        except httpx.HTTPError as error:
            raise self.raise_error("Facebook Reel publishing failed", error) from error
        return PublishedPost(
            post_url=str(permalink or f"https://www.facebook.com/reel/{video_id}"),
            external_id=str(video_id),
        )

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        del connection, account_username
        return PublishedPost(
            post_url=f"https://www.facebook.com/reel/{external_id}",
            external_id=external_id,
        )

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
