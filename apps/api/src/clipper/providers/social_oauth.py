from __future__ import annotations

import base64
import hashlib
import hmac
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
    configuration_id: str = ""

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

    @staticmethod
    def meta_permission_statuses(
        client: httpx.Client,
        base_url: str,
        access_token: str,
    ) -> dict[str, str] | None:
        """Return Meta's permission statuses without masking the primary OAuth error."""
        try:
            response = client.get(
                f"{base_url}/me/permissions",
                params={"access_token": access_token},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        payload = response.json()
        permissions = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(permissions, list):
            return None
        return {
            str(permission["permission"]): str(permission.get("status") or "")
            for permission in permissions
            if isinstance(permission, dict) and permission.get("permission")
        }

    @staticmethod
    def meta_pages(
        client: httpx.Client,
        base_url: str,
        user_token: str,
        response: httpx.Response,
    ) -> object:
        """Follow cursor pagination on a fixed Meta endpoint; never trust paging URLs."""
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return None
        pages = list(payload["data"])
        seen: set[str] = set()
        original = dict(response.request.url.params)
        original["access_token"] = user_token
        for _ in range(100):
            paging = payload.get("paging")
            if not isinstance(paging, dict) or not paging.get("next"):
                return pages
            cursors = paging.get("cursors")
            after = cursors.get("after") if isinstance(cursors, dict) else None
            if not isinstance(after, str) or not after or after in seen:
                raise OAuthProviderError(
                    "Meta returned incomplete Page pagination. Please reconnect."
                )
            seen.add(after)
            response = client.get(f"{base_url}/me/accounts", params={**original, "after": after})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise OAuthProviderError("Meta returned an invalid Facebook Page list")
            pages.extend(payload["data"])
        raise OAuthProviderError("Meta returned too many Page result pages")


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
        verifier = _pkce_verifier(state, self._config.client_secret)
        challenge = hashlib.sha256(verifier.encode()).hexdigest()
        query = urlencode(
            {
                "client_key": self._config.client_id,
                "response_type": "code",
                "scope": "user.info.basic,video.publish,video.upload",
                "redirect_uri": self._config.redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"https://www.tiktok.com/v2/auth/authorize/?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
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
                        "code_verifier": _pkce_verifier(state, self._config.client_secret),
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


class InstagramOAuthClient(_OAuthHttpClient):
    def __init__(
        self,
        config: OAuthAppConfig,
        graph_version: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client=client)
        self._config = config
        self._base = f"https://graph.facebook.com/{graph_version}"

    @property
    def configured(self) -> bool:
        return self._config.configured and bool(self._config.configuration_id)

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "response_type": "code",
                "config_id": self._config.configuration_id,
                "override_default_response_type": "true",
                "state": state,
                "auth_type": "rerequest",
                "return_scopes": "true",
            }
        )
        version = self._base.rsplit("/", 1)[-1]
        return f"https://www.facebook.com/{version}/dialog/oauth?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        connections = self.exchange_code_candidates(code, state)
        if len(connections) != 1:
            raise OAuthProviderError(
                "Multiple Instagram accounts are available. Choose one in ReachCut."
            )
        return connections[0]

    def exchange_code_candidates(self, code: str, state: str = "") -> list[OAuthConnection]:
        del state
        self._require_configured()
        permission_statuses: dict[str, str] | None = None
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
                pages = self.meta_pages(client, self._base, str(user_token), accounts_response)
                if pages == []:
                    permission_statuses = self.meta_permission_statuses(
                        client,
                        self._base,
                        str(user_token),
                    )
        except httpx.HTTPError as error:
            raise self.provider_error("Meta", error) from error
        connections: dict[str, OAuthConnection] = {}
        if isinstance(pages, list):
            for page in pages:
                if not isinstance(page, dict) or not page.get("access_token"):
                    continue
                instagram = page.get("instagram_business_account")
                if not isinstance(instagram, dict) or not instagram.get("id"):
                    continue
                external_id = str(instagram["id"])
                username = str(instagram.get("username") or "").lstrip("@")
                connections.setdefault(
                    external_id,
                    OAuthConnection(
                        access_token=str(user_token),
                        external_account_id=external_id,
                        display_name=str(instagram.get("name") or username or "Instagram account"),
                        username=username,
                        profile_url=f"https://www.instagram.com/{username}/" if username else "",
                        parent_page_id=str(page.get("id") or ""),
                        parent_page_name=str(page.get("name") or "Facebook Page"),
                    ),
                )
        if not connections:
            raise self._missing_connection_error(pages, permission_statuses)
        return list(connections.values())

    @staticmethod
    def _missing_connection_error(
        pages: object,
        permission_statuses: dict[str, str] | None = None,
    ) -> OAuthProviderError:
        if not isinstance(pages, list):
            return OAuthProviderError("Meta returned an invalid Facebook Page list")
        if not pages:
            required = {
                "business_management",
                "instagram_basic",
                "instagram_content_publish",
                "instagram_manage_insights",
                "pages_read_engagement",
                "pages_show_list",
            }
            if permission_statuses is not None:
                missing = sorted(
                    permission
                    for permission in required
                    if permission_statuses.get(permission) != "granted"
                )
                if missing:
                    return OAuthProviderError(
                        "Meta login did not grant the required permission(s): "
                        f"{', '.join(missing)}. In Facebook Login for Business > "
                        "Configurations, edit the Configuration ID used by ReachCut, choose a "
                        "User access token, add those permissions, save it, remove ReachCut from "
                        "Facebook Settings > Business Integrations, and reconnect."
                    )
                return OAuthProviderError(
                    "Meta granted the required Instagram and Page permissions, but /me/accounts "
                    "returned no Facebook Pages even with business_management. Confirm the "
                    "token belongs to the personal Facebook profile that manages the Page and "
                    "that the destination is a true Facebook Page, not an additional or "
                    "professional-mode profile."
                )
            return OAuthProviderError(
                "Meta returned no Facebook Pages for this login. App administrator access is "
                "not Page access: give this Facebook user direct Facebook access to the Page, "
                "remove ReachCut from Facebook Settings > Business Integrations if it was "
                "previously authorized, then reconnect and select the Page while granting "
                "pages_show_list and pages_read_engagement."
            )
        pages_with_tokens = [
            page for page in pages if isinstance(page, dict) and page.get("access_token")
        ]
        if not pages_with_tokens:
            return OAuthProviderError(
                "Meta returned Facebook Pages without Page access tokens. Reconnect and grant "
                "pages_show_list and pages_read_engagement."
            )
        return OAuthProviderError(
            f"Meta returned {len(pages_with_tokens)} accessible Facebook Page(s), but none has "
            "a linked Instagram professional account. Link the Instagram account to one of "
            "those Pages in Meta Business Suite, then reconnect."
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise OAuthConfigurationError("Instagram OAuth is not configured")


class FacebookOAuthClient(_OAuthHttpClient):
    def __init__(
        self,
        config: OAuthAppConfig,
        graph_version: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client=client)
        self._config = config
        self._base = f"https://graph.facebook.com/{graph_version}"

    @property
    def configured(self) -> bool:
        return self._config.configured and bool(self._config.configuration_id)

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        query = urlencode(
            {
                "client_id": self._config.client_id,
                "redirect_uri": self._config.redirect_uri,
                "response_type": "code",
                "config_id": self._config.configuration_id,
                "override_default_response_type": "true",
                "state": state,
                "auth_type": "rerequest",
                "return_scopes": "true",
            }
        )
        return f"https://www.facebook.com/{self._base.rsplit('/', 1)[-1]}/dialog/oauth?{query}"

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
        connections = self.exchange_code_candidates(code, state)
        if len(connections) != 1:
            raise OAuthProviderError(
                "Multiple Facebook Pages are available. Choose one in ReachCut."
            )
        return connections[0]

    def exchange_code_candidates(self, code: str, state: str = "") -> list[OAuthConnection]:
        del state
        self._require_configured()
        permission_statuses: dict[str, str] | None = None
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
                        "fields": ("id,name,access_token,tasks"),
                        "access_token": user_token,
                    },
                )
                accounts_response.raise_for_status()
                accounts = self.meta_pages(client, self._base, str(user_token), accounts_response)
                if accounts == []:
                    permission_statuses = self.meta_permission_statuses(
                        client,
                        self._base,
                        str(user_token),
                    )
        except httpx.HTTPError as error:
            raise self.provider_error("Meta", error) from error
        connections: dict[str, OAuthConnection] = {}
        if isinstance(accounts, list):
            for page in accounts:
                if not isinstance(page, dict) or not page.get("access_token") or not page.get("id"):
                    continue
                external_id = str(page["id"])
                connections.setdefault(
                    external_id,
                    OAuthConnection(
                        access_token=str(page["access_token"]),
                        external_account_id=external_id,
                        display_name=str(page.get("name") or "Facebook Page"),
                        profile_url=f"https://www.facebook.com/{external_id}",
                    ),
                )
        if not connections:
            raise self._missing_connection_error(accounts, permission_statuses)
        return list(connections.values())

    def _missing_connection_error(
        self,
        pages: object,
        permission_statuses: dict[str, str] | None = None,
    ) -> OAuthProviderError:
        if not isinstance(pages, list):
            return OAuthProviderError("Meta returned an invalid Facebook Page list")
        if not pages:
            required = {
                "business_management",
                "pages_manage_posts",
                "pages_read_engagement",
                "pages_show_list",
            }
            if permission_statuses is not None:
                missing = sorted(
                    permission
                    for permission in required
                    if permission_statuses.get(permission) != "granted"
                )
                if missing:
                    return OAuthProviderError(
                        "Meta login did not grant the required permission(s): "
                        f"{', '.join(missing)}. In Facebook Login for Business > "
                        "Configurations, edit the Configuration ID used by ReachCut, choose a "
                        "User access token, add those permissions, save it, remove ReachCut from "
                        "Facebook Settings > Business Integrations, and reconnect."
                    )
                return OAuthProviderError(
                    "Meta granted the required Facebook Page permissions, but /me/accounts "
                    "returned no Facebook Pages even with business_management. Confirm the "
                    "token belongs to the personal Facebook profile that manages the Page and "
                    "that the destination is a true Facebook Page, not an additional or "
                    "professional-mode profile."
                )
            return OAuthProviderError(
                "Meta returned no Facebook Pages for this login. App administrator access is "
                "not Page access: give this Facebook user direct Facebook access to the Page, "
                "remove ReachCut from Facebook Settings > Business Integrations if it was "
                "previously authorized, then reconnect and select the Page while granting "
                "pages_show_list and pages_read_engagement."
            )
        pages_with_tokens = [
            page for page in pages if isinstance(page, dict) and page.get("access_token")
        ]
        if not pages_with_tokens:
            return OAuthProviderError(
                "Meta returned Facebook Pages without Page access tokens. Reconnect and grant "
                "pages_show_list and pages_read_engagement."
            )
        return OAuthProviderError("Meta could not find a Facebook Page available to this login")

    def _require_configured(self) -> None:
        if not self.configured:
            raise OAuthConfigurationError("Facebook OAuth is not configured")


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
        verifier = _pkce_verifier(state, self._config.client_secret)
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
            "code_verifier": _pkce_verifier(state, self._config.client_secret),
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


def _pkce_verifier(state: str, client_secret: str) -> str:
    return _base64url(hmac.new(client_secret.encode(), state.encode(), hashlib.sha256).digest())


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")
