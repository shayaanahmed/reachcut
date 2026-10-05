from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx


class ProviderApiError(RuntimeError):
    pass


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
