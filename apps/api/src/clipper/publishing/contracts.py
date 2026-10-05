from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

PublishingPlatform = Literal["youtube", "tiktok", "instagram", "facebook", "x"]


@dataclass(frozen=True)
class OAuthConnection:
    refresh_token: str = ""
    access_token: str = ""
    external_account_id: str = ""


class OAuthConfigurationError(RuntimeError):
    pass


class OAuthProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishRequest:
    media_path: Path
    title: str
    description: str
    privacy_status: str = "public"
    account_username: str = ""
    duration_seconds: float | None = None


@dataclass(frozen=True)
class PublishedPost:
    post_url: str | None
    external_id: str | None = None
    status: str = "published"
    updated_connection: OAuthConnection | None = None


@dataclass(frozen=True)
class ProviderMetrics:
    external_id: str
    views: int
    likes: int
    comments: int


class CredentialStore(Protocol):
    def save(self, account_id: str, connection: OAuthConnection) -> None: ...

    def load(self, account_id: str) -> OAuthConnection | None: ...

    def delete(self, account_id: str) -> None: ...


class OAuthClient(Protocol):
    @property
    def configured(self) -> bool: ...

    def authorization_url(self, state: str) -> str: ...

    def exchange_code(self, code: str, state: str = "") -> OAuthConnection: ...


class PublishingAdapter(Protocol):
    def publish(self, request: PublishRequest, connection: OAuthConnection) -> PublishedPost: ...

    def refresh(
        self,
        external_id: str,
        connection: OAuthConnection,
        account_username: str,
    ) -> PublishedPost: ...


class MetricsAdapter(Protocol):
    def metrics(
        self,
        external_id: str | None,
        post_url: str | None,
        connection: OAuthConnection,
    ) -> ProviderMetrics: ...
