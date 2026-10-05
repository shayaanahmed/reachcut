from __future__ import annotations

import httpx

from clipper.providers.publishing_http import ProviderApiError, PublishingHttpClient
from clipper.publishing import OAuthConnection, PublishedPost, PublishRequest


class TikTokPublishingAdapter(PublishingHttpClient):
    def __init__(
        self,
        client_key: str = "",
        client_secret: str = "",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client)
        self._client_key = client_key
        self._client_secret = client_secret

    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost:
        connection = self._refresh_connection(connection)
        if not connection.access_token:
            raise ProviderApiError("TikTok requires a user access token")
        privacy = {
            "public": "PUBLIC_TO_EVERYONE",
            "friends": "MUTUAL_FOLLOW_FRIENDS",
            "private": "SELF_ONLY",
        }.get(request.privacy_status)
        if not privacy:
            raise ProviderApiError("unsupported TikTok privacy status")
        size = request.media_path.stat().st_size
        chunk_size = min(size, 32 * 1024 * 1024)
        total_chunks = (size + chunk_size - 1) // chunk_size
        headers = {
            "Authorization": f"Bearer {connection.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        body = {
            "post_info": {
                "title": request.description[:2200] or request.title[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        try:
            with self.client_session() as client:
                creator = client.post(
                    "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
                    headers=headers,
                )
                creator.raise_for_status()
                creator_payload = creator.json()
                self._check_error(creator_payload)
                creator_info = creator_payload.get("data", {})
                if privacy not in creator_info.get("privacy_level_options", []):
                    raise ProviderApiError(
                        "the selected TikTok privacy level is not available for this account"
                    )
                maximum_duration = creator_info.get("max_video_post_duration_sec")
                if (
                    request.duration_seconds is not None
                    and isinstance(maximum_duration, int | float)
                    and request.duration_seconds > maximum_duration
                ):
                    raise ProviderApiError(
                        f"TikTok allows at most {maximum_duration} seconds for this account"
                    )
                initialized = client.post(
                    "https://open.tiktokapis.com/v2/post/publish/video/init/",
                    headers=headers,
                    json=body,
                )
                initialized.raise_for_status()
                payload = initialized.json()
                self._check_error(payload)
                upload_url = payload.get("data", {}).get("upload_url")
                publish_id = payload.get("data", {}).get("publish_id")
                if not upload_url or not publish_id:
                    raise ProviderApiError("TikTok did not return an upload URL and publish ID")
                with request.media_path.open("rb") as media:
                    offset = 0
                    while chunk := media.read(chunk_size):
                        final_byte = offset + len(chunk) - 1
                        uploaded = client.put(
                            str(upload_url),
                            headers={
                                "Content-Type": "video/mp4",
                                "Content-Length": str(len(chunk)),
                                "Content-Range": f"bytes {offset}-{final_byte}/{size}",
                            },
                            content=chunk,
                            timeout=None,
                        )
                        uploaded.raise_for_status()
                        offset = final_byte + 1
        except httpx.HTTPError as error:
            raise self.raise_error("TikTok upload failed", error) from error
        return PublishedPost(
            post_url=None,
            external_id=str(publish_id),
            status="processing",
            updated_connection=connection,
        )

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost:
        try:
            with self.client_session() as client:
                response = client.post(
                    "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                    headers={
                        "Authorization": f"Bearer {connection.access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                    },
                    json={"publish_id": external_id},
                )
                response.raise_for_status()
                payload = response.json()
                self._check_error(payload)
        except httpx.HTTPError as error:
            raise self.raise_error("TikTok status check failed", error) from error
        data = payload.get("data", {})
        if data.get("status") == "FAILED":
            return PublishedPost(post_url=None, external_id=external_id, status="failed")
        post_ids = data.get("publicaly_available_post_id") or []
        if data.get("status") == "PUBLISH_COMPLETE" and post_ids:
            username = account_username.lstrip("@")
            return PublishedPost(
                post_url=f"https://www.tiktok.com/@{username}/video/{post_ids[0]}",
                external_id=str(post_ids[0]),
            )
        return PublishedPost(post_url=None, external_id=external_id, status="processing")

    @staticmethod
    def _check_error(payload: dict[str, object]) -> None:
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code") not in {None, "ok"}:
            raise ProviderApiError(f"TikTok API rejected the request: {error.get('message')}")

    def _refresh_connection(self, connection: OAuthConnection) -> OAuthConnection:
        if not connection.refresh_token:
            return connection
        if not self._client_key or not self._client_secret:
            raise ProviderApiError(
                "TikTok token refresh requires CLIPPER_TIKTOK_CLIENT_KEY and "
                "CLIPPER_TIKTOK_CLIENT_SECRET"
            )
        try:
            with self.client_session() as client:
                response = client.post(
                    "https://open.tiktokapis.com/v2/oauth/token/",
                    data={
                        "client_key": self._client_key,
                        "client_secret": self._client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": connection.refresh_token,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as error:
            raise self.raise_error("TikTok token refresh failed", error) from error
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not access_token or not refresh_token:
            raise ProviderApiError("TikTok token refresh returned incomplete credentials")
        return OAuthConnection(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            external_account_id=connection.external_account_id,
        )
