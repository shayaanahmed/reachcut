from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from clipper.discovery.contracts import DiscoveryProvider
from clipper.discovery.models import CountryOption, DiscoveryResult


class DiscoveryUnavailableError(RuntimeError):
    pass


SUPPORTED_COUNTRIES = tuple(
    CountryOption(code=code, name=name)
    for code, name in (
        ("AU", "Australia"),
        ("BR", "Brazil"),
        ("CA", "Canada"),
        ("DE", "Germany"),
        ("ES", "Spain"),
        ("FR", "France"),
        ("GB", "United Kingdom"),
        ("ID", "Indonesia"),
        ("IN", "India"),
        ("IT", "Italy"),
        ("JP", "Japan"),
        ("KR", "South Korea"),
        ("MX", "Mexico"),
        ("NG", "Nigeria"),
        ("NL", "Netherlands"),
        ("PK", "Pakistan"),
        ("PL", "Poland"),
        ("SE", "Sweden"),
        ("TR", "Türkiye"),
        ("US", "United States"),
        ("ZA", "South Africa"),
    )
)

DISCOVERY_CATEGORIES = frozenset(
    {"trending", "news", "movies", "sports", "technology", "podcasts", "gaming"}
)


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: datetime
    result: DiscoveryResult


class DiscoveryService:
    """Validate country selection and cache short-lived external discovery results."""

    def __init__(self, provider: DiscoveryProvider, ttl: timedelta = timedelta(minutes=15)) -> None:
        self._provider = provider
        self._ttl = ttl
        self._cache: dict[tuple[str, int, str, str], _CacheEntry] = {}

    @staticmethod
    def countries() -> tuple[CountryOption, ...]:
        return SUPPORTED_COUNTRIES

    def discover(
        self,
        country_code: str = "US",
        limit: int = 8,
        *,
        query: str | None = None,
        category: str = "trending",
    ) -> DiscoveryResult:
        country = next(
            (item for item in SUPPORTED_COUNTRIES if item.code == country_code.upper()), None
        )
        if country is None:
            raise ValueError("country is not supported")
        normalized_query = " ".join((query or "").split()).strip() or None
        if normalized_query and len(normalized_query) > 120:
            raise ValueError("query must be 120 characters or fewer")
        normalized_category = category.casefold().strip()
        if normalized_category not in DISCOVERY_CATEGORIES:
            raise ValueError("category is not supported")
        now = datetime.now(UTC)
        key = (country.code, limit, normalized_category, normalized_query or "")
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            return cached.result
        try:
            result = self._provider.discover(
                country,
                limit,
                query=normalized_query,
                category=normalized_category,
            )
        except DiscoveryUnavailableError:
            raise
        except Exception as error:
            raise DiscoveryUnavailableError("trend discovery is temporarily unavailable") from error
        self._cache[key] = _CacheEntry(now + self._ttl, result)
        return result
