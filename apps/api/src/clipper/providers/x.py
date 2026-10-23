from __future__ import annotations

import time
from dataclasses import replace

import httpx

from clipper.providers.publishing_http import (
    ProviderApiError,
    PublishingHttpClient,
    local_video_size,
)
from clipper.publishing import OAuthConnection, PublishedPost, PublishRequest


class XPublishingAdapter(PublishingHttpClient):
    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client)
        self._client_id = client_id
        self._client_secret = client_secret

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        connection = self.refresh_connection(connection)
        if not connection.access_token:
            raise ProviderApiError("X requires a user access token")
        headers = {"Authorization": f"Bearer {connection.access_token}"}
        size = local_video_size(request.media_path, "X")
        try:
            with self.client_session() as client:
                initialized = client.post(
                    "https://api.x.com/2/media/upload/initialize",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "media_type": "video/mp4",
                        "total_bytes": size,
                        "media_category": "tweet_video",
                    },
                )
                initialized.raise_for_status()
                media_id = initialized.json().get("data", {}).get("id")
                if not media_id:
                    raise ProviderApiError("X did not return a media ID")
                with request.media_path.open("rb") as media:
                    segment = 0
                    while chunk := media.read(5 * 1024 * 1024):
                        appended = client.post(
                            f"https://api.x.com/2/media/upload/{media_id}/append",
                            headers=headers,
                            data={"segment_index": str(segment)},
                            files={"media": ("chunk.mp4", chunk, "video/mp4")},
                            timeout=None,
                        )
                        appended.raise_for_status()
                        segment += 1
                finalized = client.post(
                    f"https://api.x.com/2/media/upload/{media_id}/finalize",
                    headers=headers,
                )
                finalized.raise_for_status()
                _wait_for_x_media(client, str(media_id), headers, finalized.json())
                text = request.description[:280] or request.title[:280]
                posted = client.post(
                    "https://api.x.com/2/tweets",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"text": text, "media": {"media_ids": [media_id]}},
                )
                posted.raise_for_status()
                post_id = posted.json().get("data", {}).get("id")
        except httpx.HTTPError as error:
            raise self.raise_error("X publishing failed", error) from error
        if not post_id:
            raise ProviderApiError("X did not return a post ID")
        username = request.account_username.lstrip("@") or "i/web"
        return PublishedPost(
            post_url=f"https://x.com/{username}/status/{post_id}",
            external_id=str(post_id),
            updated_connection=connection,
        )

    def delete_post(
        self, external_id: str | None, post_url: str | None, connection: OAuthConnection
    ) -> None:
        del post_url
        if not external_id:
            raise ProviderApiError("X deletion requires the original post ID")
        try:
            with self.client_session() as client:
                response = client.delete(
                    f"https://api.x.com/2/tweets/{external_id}",
                    headers={"Authorization": f"Bearer {connection.access_token}"},
                )
                response.raise_for_status()
                if response.json().get("data", {}).get("deleted") is not True:
                    raise ProviderApiError("X did not confirm deletion")
        except httpx.HTTPError as error:
            raise self.raise_error("X deletion failed", error) from error

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        del connection
        username = account_username.lstrip("@") or "i/web"
        return PublishedPost(
            post_url=f"https://x.com/{username}/status/{external_id}",
            external_id=external_id,
        )

    def refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
        if not connection.refresh_token or (
            connection.access_token
            and connection.access_token_expires_at is not None
            and connection.access_token_expires_at > time.time() + 300
        ):
            return connection
        if not self._client_id:
            raise ProviderApiError("X token refresh requires CLIPPER_X_CLIENT_ID")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": self._client_id,
        }
        try:
            with self.client_session() as client:
                if self._client_secret:
                    response = client.post(
                        "https://api.x.com/2/oauth2/token",
                        auth=httpx.BasicAuth(self._client_id, self._client_secret),
                        data=data,
                    )
                else:
                    response = client.post("https://api.x.com/2/oauth2/token", data=data)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as error:
            raise self.raise_error("X token refresh failed", error) from error
        access_token = payload.get("access_token")
        if not access_token:
            raise ProviderApiError("X token refresh did not return an access token")
        return replace(
            connection,
            access_token=str(access_token),
            refresh_token=str(payload.get("refresh_token") or connection.refresh_token),
            access_token_expires_at=time.time() + float(payload.get("expires_in") or 7200),
        )


def _wait_for_x_media(
    client: httpx.Client,
    media_id: str,
    headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    for _ in range(30):
        data = payload.get("data", {})
        processing = data.get("processing_info", {}) if isinstance(data, dict) else {}
        state = processing.get("state") if isinstance(processing, dict) else None
        if state in {None, "succeeded"}:
            return
        if state == "failed":
            raise ProviderApiError("X rejected the uploaded video during processing")
        delay = processing.get("check_after_secs", 1)
        time.sleep(min(max(int(delay), 1), 5))
        response = client.get(
            "https://api.x.com/2/media/upload",
            headers=headers,
            params={"command": "STATUS", "media_id": media_id},
        )
        response.raise_for_status()
        payload = response.json()
    raise ProviderApiError("X media processing did not finish within the polling window")
