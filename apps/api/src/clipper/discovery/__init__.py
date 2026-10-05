"""Country-aware trend and source discovery public API."""

from clipper.discovery.contracts import DiscoveryProvider
from clipper.discovery.models import CountryOption, DiscoveryResult, SourceCandidate, TrendTopic
from clipper.discovery.service import DiscoveryService, DiscoveryUnavailableError

__all__ = [
    "CountryOption",
    "DiscoveryProvider",
    "DiscoveryResult",
    "DiscoveryService",
    "DiscoveryUnavailableError",
    "SourceCandidate",
    "TrendTopic",
]
