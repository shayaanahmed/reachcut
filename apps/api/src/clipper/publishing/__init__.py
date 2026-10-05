"""Public contracts for first-party social publishing adapters."""

from clipper.publishing.contracts import (
    CredentialStore,
    MetricsAdapter,
    OAuthClient,
    OAuthConfigurationError,
    OAuthConnection,
    OAuthProviderError,
    ProviderMetrics,
    PublishedPost,
    PublishingAdapter,
    PublishingPlatform,
    PublishRequest,
)

__all__ = [
    "CredentialStore",
    "MetricsAdapter",
    "OAuthClient",
    "OAuthConfigurationError",
    "OAuthConnection",
    "OAuthProviderError",
    "ProviderMetrics",
    "PublishRequest",
    "PublishedPost",
    "PublishingAdapter",
    "PublishingPlatform",
]
