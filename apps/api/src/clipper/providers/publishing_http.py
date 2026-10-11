from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class ProviderApiError(RuntimeError):
    pass


def local_video_size(path: Path, provider: str) -> int:
    """Validate a rendered file before starting a provider upload."""

    if not path.is_file():
        raise ProviderApiError(f"{provider} cannot publish because the rendered video is missing")
    size = path.stat().st_size
    if size <= 0:
        raise ProviderApiError(f"{provider} cannot publish an empty rendered video")
    return size


def trusted_upload_url(
    value: object,
    *,
    provider: str,
    allowed_host_suffixes: tuple[str, ...],
) -> str:
    """Validate a provider-issued URL before sending credentials or media to it."""

    if not isinstance(value, str) or not value:
        raise ProviderApiError(f"{provider} did not return a valid upload URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ProviderApiError(f"{provider} returned an invalid upload URL") from error
    hostname = (parsed.hostname or "").rstrip(".").lower()
    trusted_host = any(
        hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed_host_suffixes
    )
    if (
        parsed.scheme.lower() != "https"
        or not trusted_host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ProviderApiError(f"{provider} returned an untrusted upload URL")
    return value


class PublishingHttpClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @contextmanager
    def client_session(self) -> Iterator[httpx.Client]:
        if self._client:
            yield self._client
        else:
            with httpx.Client(timeout=60) as client:
                yield client

    @staticmethod
    def raise_error(prefix: str, error: httpx.HTTPError) -> ProviderApiError:
        if isinstance(error, httpx.HTTPStatusError):
            return ProviderApiError(f"{prefix}: {error.response.text[:500]}")
        return ProviderApiError(f"{prefix}: {error}")
