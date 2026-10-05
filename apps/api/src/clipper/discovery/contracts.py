from typing import Protocol

from clipper.discovery.models import CountryOption, DiscoveryResult


class DiscoveryProvider(Protocol):
    def discover(
        self,
        country: CountryOption,
        limit: int,
        *,
        query: str | None = None,
        category: str = "trending",
    ) -> DiscoveryResult:
        """Fetch current topics and relevant public video sources."""
