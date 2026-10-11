from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from clipper.publishing import (
    OAuthConfigurationError,
    OAuthConnection,
    OAuthProviderError,
)


@dataclass(frozen=True)
class OAuthAppConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


class _OAuthHttpClient:
    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    @contextmanager
    def client_session(self) -> Iterator[httpx.Client]:
        if self._client:
            yield self._client
        else:
            with httpx.Client(timeout=30) as client:
                yield client

    @staticmethod
    def provider_error(platform: str, error: httpx.HTTPError) -> OAuthProviderError:
        if isinstance(error, httpx.HTTPStatusError):
            detail = error.response.text[:500]
            return OAuthProviderError(f"{platform} authorization failed: {detail}")
        return OAuthProviderError(f"{platform} authorization failed: {error}")


class TikTokOAuthClient(_OAuthHttpClient):
    def __init__(
        self,
        config: OAuthAppConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client=client)
        self._config = config

    @property
    def configured(self) -> bool:
        return self._config.configured

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        query = urlencode(
            {
                "client_key": self._config.client_id,
                "response_type": "code",
                "scope": "user.info.basic,video.publish,video.upload",
                "redirect_uri": self._config.redirect_uri,
                "state": state,
            }
        )
        return f"https://www.tiktok.com/v2/auth/authorize/?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        del state
        self._require_configured()
        try:
            with self.client_session() as client:
                response = client.post(
                    "https://open.tiktokapis.com/v2/oauth/token/",
                    data={
                        "client_key": self._config.client_id,
                        "client_secret": self._config.client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": self._config.redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                payload = response.json()
                access_token = payload.get("access_token")
                refresh_token = payload.get("refresh_token")
                if not access_token or not refresh_token:
                    raise OAuthProviderError("TikTok authorization returned incomplete credentials")
                profile_response = client.get(
                    "https://open.tiktokapis.com/v2/user/info/",
                    params={"fields": "open_id,union_id,avatar_url,display_name"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                profile_response.raise_for_status()
        except httpx.HTTPError as error:
            raise self.provider_error("TikTok", error) from error
        profile_payload = profile_response.json()
        profile = profile_payload.get("data", {}).get("user", {})
        open_id = str(profile.get("open_id") or payload.get("open_id") or "")
        return OAuthConnection(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            external_account_id=open_id,
            display_name=str(profile.get("display_name") or "TikTok account"),
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise OAuthConfigurationError("TikTok OAuth is not configured")


class MetaOAuthClient(_OAuthHttpClient):
    def __init__(
        self,
        config: OAuthAppConfig,
        graph_version: str,
        platform: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client=client)
        if platform not in {"instagram", "facebook"}:
            raise ValueError("Meta OAuth platform must be instagram or facebook")
        self._config = config
        self._base = f"https://graph.facebook.com/{graph_version}"
        self._platform = platform

    @property
    def configured(self) -> bool:
        return self._config.configured

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        scopes = ["pages_show_list", "pages_read_engagement"]
        if self._platform == "instagram":
            scopes.extend(["instagram_basic", "instagram_content_publish"])
        else:
            scopes.append("pages_manage_posts")
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "response_type": "code",
                "scope": ",".join(scopes),
                "state": state,
            }
        )
        return f"https://www.facebook.com/{self._base.rsplit('/', 1)[-1]}/dialog/oauth?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        del state
        self._require_configured()
        try:
            with self.client_session() as client:
                token_response = client.get(
                    f"{self._base}/oauth/access_token",
                    params={
                        "client_id": self._config.client_id,
                        "client_secret": self._config.client_secret,
                        "redirect_uri": self._config.redirect_uri,
                        "code": code,
                    },
                )
                token_response.raise_for_status()
                user_token = token_response.json().get("access_token")
                if not user_token:
                    raise OAuthProviderError("Meta did not return an access token")
                accounts_response = client.get(
                    f"{self._base}/me/accounts",
                    params={
                        "fields": (
                            "id,name,access_token,tasks,"
                            "instagram_business_account{id,username,name,profile_picture_url}"
                        ),
                        "access_token": user_token,
                    },
                )
                accounts_response.raise_for_status()
                accounts_payload = accounts_response.json()
                accounts = (
                    accounts_payload.get("data") if isinstance(accounts_payload, dict) else None
                )
        except httpx.HTTPError as error:
            raise self.provider_error("Meta", error) from error
        connection = self._connection_from_pages(accounts)
        if connection is None:
            raise self._missing_connection_error(accounts)
        return connection

    def _connection_from_pages(self, pages: object) -> OAuthConnection | None:
        if not isinstance(pages, list):
            return None
        for page in pages:
            if not isinstance(page, dict) or not page.get("access_token"):
                continue
            if self._platform == "facebook" and page.get("id"):
                return OAuthConnection(
                    access_token=str(page["access_token"]),
                    external_account_id=str(page["id"]),
                    display_name=str(page.get("name") or "Facebook Page"),
                    profile_url=f"https://www.facebook.com/{page['id']}",
                )
            instagram = page.get("instagram_business_account")
            if isinstance(instagram, dict) and instagram.get("id"):
                username = str(instagram.get("username") or "").lstrip("@")
                return OAuthConnection(
                    access_token=str(page["access_token"]),
                    external_account_id=str(instagram["id"]),
                    display_name=str(instagram.get("name") or username or "Instagram account"),
                    username=username,
                    profile_url=(f"https://www.instagram.com/{username}/" if username else ""),
                )
        return None

    def _missing_connection_error(self, pages: object) -> OAuthProviderError:
        if not isinstance(pages, list):
            return OAuthProviderError("Meta returned an invalid Facebook Page list")
        if not pages:
            return OAuthProviderError(
                "Meta returned no Facebook Pages for this login. Confirm the Facebook user "
                "has Page access and granted pages_show_list and pages_read_engagement."
            )
        pages_with_tokens = [
            page for page in pages if isinstance(page, dict) and page.get("access_token")
        ]
        if not pages_with_tokens:
            return OAuthProviderError(
                "Meta returned Facebook Pages without Page access tokens. Reconnect and grant "
                "pages_show_list and pages_read_engagement."
            )
        if self._platform == "instagram":
            return OAuthProviderError(
                f"Meta returned {len(pages_with_tokens)} accessible Facebook Page(s), but none "
                "has a linked Instagram professional account. Link the Instagram account to "
                "one of those Pages in Meta Business Suite, then reconnect."
            )
        return OAuthProviderError("Meta could not find a Facebook Page available to this login")

    def _require_configured(self) -> None:
        if not self.configured:
            raise OAuthConfigurationError(f"{self._platform.title()} OAuth is not configured")


class XOAuthClient(_OAuthHttpClient):
    def __init__(
        self,
        config: OAuthAppConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client=client)
        self._config = config

    @property
    def configured(self) -> bool:
        return self._config.configured

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        verifier = _pkce_verifier(state)
        challenge = _base64url(hashlib.sha256(verifier.encode()).digest())
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "scope": "tweet.read tweet.write users.read media.write offline.access",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"https://x.com/i/oauth2/authorize?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        self._require_configured()
        data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "code_verifier": _pkce_verifier(state),
        }
        try:
            with self.client_session() as client:
                response = client.post(
                    "https://api.x.com/2/oauth2/token",
                    data=data,
                    auth=httpx.BasicAuth(
                        self._config.client_id,
                        self._config.client_secret,
                    ),
                )
                response.raise_for_status()
                payload = response.json()
                access_token = payload.get("access_token")
                if not access_token:
                    raise OAuthProviderError("X did not return an access token")
                profile_response = client.get(
                    "https://api.x.com/2/users/me",
                    params={"user.fields": "id,name,username"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                profile_response.raise_for_status()
        except httpx.HTTPError as error:
            raise self.provider_error("X", error) from error
        profile = profile_response.json().get("data", {})
        username = str(profile.get("username") or "").lstrip("@")
        return OAuthConnection(
            access_token=str(access_token),
            refresh_token=str(payload.get("refresh_token") or ""),
            external_account_id=str(profile.get("id") or ""),
            display_name=str(profile.get("name") or username or "X account"),
            username=username,
            profile_url=(f"https://x.com/{username}" if username else ""),
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise OAuthConfigurationError("X OAuth is not configured")


def _pkce_verifier(state: str) -> str:
    return _base64url(hashlib.sha256(f"clipper:{state}".encode()).digest())


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")
