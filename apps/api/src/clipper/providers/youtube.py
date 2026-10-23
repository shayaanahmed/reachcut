from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from clipper.providers.publishing_http import (
    ProviderApiError,
    local_video_size,
    trusted_upload_url,
)
from clipper.publishing import (
    OAuthConfigurationError,
    OAuthConnection,
    OAuthProviderError,
    ProviderMetrics,
    PublishedPost,
    PublishRequest,
)

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_SCOPES = (YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE, YOUTUBE_MANAGE_SCOPE)


class YouTubeConfigurationError(OAuthConfigurationError):
    pass


class YouTubeApiError(OAuthProviderError):
    pass


@dataclass(frozen=True)
class YouTubeOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


class YouTubeOAuthClient:
    def __init__(
        self,
        config: YouTubeOAuthConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._client = client

    @property
    def configured(self) -> bool:
        return self._config.configured

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "response_type": "code",
                "scope": " ".join(YOUTUBE_SCOPES),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        del state
        self._require_configured()
        try:
            with self._client_session() as client:
                response = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": self._config.client_id,
                        "client_secret": self._config.client_secret,
                        "redirect_uri": self._config.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                access_token = payload.get("access_token")
                refresh_token = payload.get("refresh_token")
                if not access_token or not refresh_token:
                    raise YouTubeApiError(
                        "Google did not return complete credentials; reconnect the account"
                    )
                channel_response = client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "id,snippet", "mine": "true"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                channel_response.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(_http_error("YouTube authorization failed", error)) from error
        channels = channel_response.json().get("items", [])
        if not channels:
            raise YouTubeApiError("Google did not return a YouTube channel for this account")
        channel = channels[0]
        snippet = channel.get("snippet", {})
        channel_id = str(channel.get("id") or "")
        custom_url = str(snippet.get("customUrl") or "").lstrip("@")
        return OAuthConnection(
            granted_scopes=tuple(str(payload["scope"]).split()) if payload.get("scope") else None,
            refresh_token=str(refresh_token),
            access_token=str(access_token),
            external_account_id=channel_id,
            display_name=str(snippet.get("title") or "YouTube channel"),
            username=custom_url,
            profile_url=(f"https://www.youtube.com/channel/{channel_id}" if channel_id else ""),
        )

    def access_token(self, connection: OAuthConnection) -> str:
        return self.refresh_connection(connection).access_token

    def refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
        self._require_configured()
        if (
            connection.access_token
            and connection.access_token_expires_at is not None
            and connection.access_token_expires_at > time.time() + 300
        ):
            return connection
        try:
            with self._client_session() as client:
                response = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self._config.client_id,
                        "client_secret": self._config.client_secret,
                        "refresh_token": connection.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(_http_error("YouTube authorization failed", error)) from error
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise YouTubeApiError("Google did not return an access token")
        return replace(
            connection,
            granted_scopes=tuple(str(payload["scope"]).split())
            if payload.get("scope")
            else connection.granted_scopes,
            access_token=str(token),
            refresh_token=str(payload.get("refresh_token") or connection.refresh_token),
            access_token_expires_at=time.time() + float(payload.get("expires_in") or 3600),
        )

    @contextmanager
    def _client_session(self) -> Iterator[httpx.Client]:
        if self._client:
            yield self._client
        else:
            with httpx.Client(timeout=30) as client:
                yield client

    def _require_configured(self) -> None:
        if not self.configured:
            raise YouTubeConfigurationError(
                "YouTube OAuth is not configured; set CLIPPER_YOUTUBE_CLIENT_ID and "
                "CLIPPER_YOUTUBE_CLIENT_SECRET"
            )


class YouTubePublishingAdapter:
    def __init__(
        self,
        oauth: YouTubeOAuthClient,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._oauth = oauth
        self._client = client

    def refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
        return self._oauth.refresh_connection(connection)

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        if request.privacy_status not in {"public", "unlisted", "private"}:
            raise YouTubeApiError("unsupported YouTube privacy status")
        access_token = self._oauth.access_token(connection)
        size = local_video_size(request.media_path, "YouTube")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        }
        body = {
            "snippet": {
                "title": request.title[:100],
                "description": request.description[:5000],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": request.privacy_status,
            },
        }
        try:
            with self._client_session() as client:
                initialize = client.post(
                    "https://www.googleapis.com/upload/youtube/v3/videos",
                    params={"uploadType": "resumable", "part": "snippet,status"},
                    headers=headers,
                    json=body,
                )
                initialize.raise_for_status()
                upload_url = initialize.headers.get("Location")
                if not upload_url:
                    raise YouTubeApiError("YouTube did not return a resumable upload URL")
                try:
                    upload_url = trusted_upload_url(
                        upload_url,
                        provider="YouTube",
                        allowed_host_suffixes=("googleapis.com",),
                    )
                except ProviderApiError as error:
                    raise YouTubeApiError(str(error)) from error

                with request.media_path.open("rb") as media:
                    uploaded = client.put(
                        upload_url,
                        headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                        content=media,
                        timeout=None,
                    )
                    uploaded.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(_http_error("YouTube upload failed", error)) from error
        video_id = uploaded.json().get("id")
        if not video_id:
            raise YouTubeApiError("YouTube upload completed without a video ID")
        return PublishedPost(
            post_url=_watch_url(str(video_id)),
            external_id=str(video_id),
            status="processing",
        )

    def update_post(
        self,
        external_id: str | None,
        post_url: str | None,
        title: str,
        description: str,
        connection: OAuthConnection,
    ) -> None:
        video_id = external_id or _video_id_from_url(post_url)
        if not video_id:
            raise YouTubeApiError("This post has no recognizable YouTube video ID")
        headers = {"Authorization": f"Bearer {self._oauth.access_token(connection)}"}
        try:
            with self._client_session() as client:
                current = client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "snippet", "id": video_id},
                    headers=headers,
                )
                current.raise_for_status()
                items = current.json().get("items", [])
                if not items:
                    raise YouTubeApiError("YouTube could not find this video")
                snippet = {
                    key: value
                    for key, value in items[0]["snippet"].items()
                    if key
                    in {
                        "title",
                        "description",
                        "categoryId",
                        "tags",
                        "defaultLanguage",
                        "defaultAudioLanguage",
                    }
                }
                snippet.update(title=title, description=description)
                response = client.put(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "snippet"},
                    headers=headers,
                    json={"id": video_id, "snippet": snippet},
                )
                response.raise_for_status()
                if response.json().get("id") != video_id:
                    raise YouTubeApiError("YouTube did not confirm the existing video's update")
        except httpx.HTTPError as error:
            raise YouTubeApiError(
                _http_error(
                    "YouTube update failed; reconnect for post-management permission", error
                )
            ) from error

    def delete_post(
        self, external_id: str | None, post_url: str | None, connection: OAuthConnection
    ) -> None:
        video_id = external_id or _video_id_from_url(post_url)
        if not video_id:
            raise YouTubeApiError("This post has no recognizable YouTube video ID")
        try:
            with self._client_session() as client:
                response = client.delete(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"id": video_id},
                    headers={"Authorization": f"Bearer {self._oauth.access_token(connection)}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(
                _http_error(
                    "YouTube deletion failed; reconnect for post-management permission", error
                )
            ) from error

    def metrics(
        self,
        external_id: str | None,
        post_url: str | None,
        connection: OAuthConnection,
    ) -> ProviderMetrics:
        video_id = external_id or _video_id_from_url(post_url)
        if not video_id:
            raise YouTubeApiError("YouTube publication has no recognizable video ID")
        access_token = self._oauth.access_token(connection)
        try:
            with self._client_session() as client:
                response = client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "statistics", "id": video_id},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(_http_error("YouTube metrics sync failed", error)) from error
        items = response.json().get("items", [])
        if not items:
            raise YouTubeApiError("YouTube could not find this video")
        statistics = items[0].get("statistics", {})
        return ProviderMetrics(
            external_id=video_id,
            views=_metric_count(statistics, "viewCount"),
            likes=_metric_count(statistics, "likeCount"),
            comments=_metric_count(statistics, "commentCount"),
        )

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        del account_username
        access_token = self._oauth.access_token(connection)
        try:
            with self._client_session() as client:
                response = client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "status,processingDetails",
                        "id": external_id,
                    },
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise YouTubeApiError(_http_error("YouTube status refresh failed", error)) from error
        items = response.json().get("items", [])
        if not items:
            raise YouTubeApiError("YouTube could not find the uploaded video")
        return PublishedPost(
            post_url=_watch_url(external_id),
            external_id=external_id,
            status=_upload_status(items[0]),
        )

    @contextmanager
    def _client_session(self) -> Iterator[httpx.Client]:
        if self._client:
            yield self._client
        else:
            with httpx.Client() as client:
                yield client


def _http_error(prefix: str, error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            reasons = {
                str(item.get("reason", ""))
                for item in error.response.json().get("error", {}).get("errors", [])
            }
        except (ValueError, AttributeError, TypeError):
            reasons = set()
        if "uploadLimitExceeded" in reasons:
            return (
                f"{prefix}: uploadLimitExceeded — this YouTube channel has an upload restriction. "
                "Pause uploads and check YouTube Studio. This is separate from Google Cloud API "
                "quota. YouTube did not supply a reset time; retry manually after it clears."
            )
        if reasons & {"quotaExceeded", "dailyLimitExceeded"}:
            return (
                f"{prefix}: quotaExceeded — Google Cloud API quota exhausted. "
                "Check the project's quota dashboard before retrying."
            )
        return f"{prefix}: {error.response.text[:500]}"
    return f"{prefix}: {error}"


def _video_id_from_url(post_url: str | None) -> str | None:
    if not post_url:
        return None
    parsed = urlparse(post_url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0] or None
    if parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"shorts", "embed"}:
        return parts[1]
    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _upload_status(item: object) -> str:
    if not isinstance(item, dict):
        return "processing"
    status = item.get("status")
    processing = item.get("processingDetails")
    upload_status = status.get("uploadStatus") if isinstance(status, dict) else None
    processing_status = processing.get("processingStatus") if isinstance(processing, dict) else None
    if upload_status in {"failed", "rejected", "deleted"} or processing_status == "terminated":
        return "failed"
    if upload_status == "processed" or processing_status == "succeeded":
        return "published"
    return "processing"


def _metric_count(statistics: object, name: str) -> int:
    if not isinstance(statistics, dict):
        return 0
    value = statistics.get(name, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
