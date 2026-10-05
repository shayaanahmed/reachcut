import threading

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.config import settings
from clipper.discovery import DiscoveryService
from clipper.persistence import (
    Clip,
    Project,
    Publication,
    PublicationAccountLink,
    SessionLocal,
)
from clipper.projects import ClipService, Pipeline, PublishingConnectionService
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.ollama import EditorialGenerationConfig, OllamaEditorialProvider
from clipper.providers.social_oauth import (
    MetaOAuthClient,
    OAuthAppConfig,
    TikTokOAuthClient,
    XOAuthClient,
)
from clipper.providers.tiktok import TikTokPublishingAdapter
from clipper.providers.trend_discovery import GoogleYouTubeDiscoveryProvider
from clipper.providers.whisper import FasterWhisperProvider
from clipper.providers.x import XPublishingAdapter
from clipper.providers.youtube import (
    YouTubeOAuthClient,
    YouTubeOAuthConfig,
    YouTubePublishingAdapter,
)
from clipper.providers.yt_dlp import YtDlpDownloader
from clipper.publishing import (
    MetricsAdapter,
    OAuthClient,
    PublishingAdapter,
    PublishingPlatform,
)


def build_transcription_provider(language: str | None = None) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language_hint=language,
    )


transcription_provider = build_transcription_provider()
editorial_provider = OllamaEditorialProvider(
    settings.editorial_base_url,
    settings.editorial_model,
    timeout_seconds=settings.editorial_timeout_seconds,
    cache_dir=settings.data_dir / "cache" / "editorial",
    generation=EditorialGenerationConfig(
        num_ctx=settings.editorial_num_ctx,
        num_predict=settings.editorial_num_predict,
        retry_num_ctx=settings.editorial_retry_num_ctx,
        retry_num_predict=settings.editorial_retry_num_predict,
    ),
)
pipeline = Pipeline(settings, transcription_provider, editorial_provider)
clip_service = ClipService(pipeline.artifacts, pipeline.renderer)
media_downloader = YtDlpDownloader(
    settings.yt_dlp_repository,
    timeout_seconds=settings.yt_dlp_timeout_seconds,
)
discovery_service = DiscoveryService(
    GoogleYouTubeDiscoveryProvider(
        settings.yt_dlp_repository,
        timeout_seconds=min(settings.yt_dlp_timeout_seconds, 60),
    )
)
credential_store = EncryptedCredentialStore(settings.data_dir)
youtube_oauth = YouTubeOAuthClient(
    YouTubeOAuthConfig(
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        redirect_uri=settings.youtube_redirect_uri,
    )
)
social_oauth_clients: dict[PublishingPlatform, OAuthClient] = {
    "youtube": youtube_oauth,
    "tiktok": TikTokOAuthClient(
        OAuthAppConfig(
            settings.tiktok_client_key,
            settings.tiktok_client_secret,
            settings.tiktok_redirect_uri,
        )
    ),
    "instagram": MetaOAuthClient(
        OAuthAppConfig(
            settings.meta_app_id,
            settings.meta_app_secret,
            settings.meta_redirect_uri,
        ),
        settings.meta_graph_version,
        "instagram",
    ),
    "facebook": MetaOAuthClient(
        OAuthAppConfig(
            settings.meta_app_id,
            settings.meta_app_secret,
            settings.meta_redirect_uri,
        ),
        settings.meta_graph_version,
        "facebook",
    ),
    "x": XOAuthClient(
        OAuthAppConfig(
            settings.x_client_id,
            settings.x_client_secret,
            settings.x_redirect_uri,
        )
    ),
}
youtube_publisher = YouTubePublishingAdapter(youtube_oauth)
publishing_adapters: dict[str, PublishingAdapter] = {
    "youtube": youtube_publisher,
    "tiktok": TikTokPublishingAdapter(settings.tiktok_client_key, settings.tiktok_client_secret),
    "instagram": InstagramPublishingAdapter(settings.meta_graph_version),
    "facebook": FacebookPublishingAdapter(settings.meta_graph_version),
    "x": XPublishingAdapter(settings.x_client_id, settings.x_client_secret),
}
metrics_adapters: dict[str, MetricsAdapter] = {"youtube": youtube_publisher}
publishing_connections = PublishingConnectionService(social_oauth_clients, credential_store)
pipeline_lock = threading.Lock()
logger = structlog.get_logger()


def run_pipeline(project_id: str, language: str | None = None) -> None:
    """Background-task entry point with a fresh database session."""

    with pipeline_lock, SessionLocal() as session:
        try:
            selected_transcription = build_transcription_provider(language)
            selected_pipeline = Pipeline(settings, selected_transcription, editorial_provider)
            selected_pipeline.run(session, project_id)
        except Exception as error:
            logger.exception(
                "pipeline_failed",
                project_id=project_id,
                error_category=type(error).__name__,
            )


def find_project(session: Session, project_id: str) -> Project | None:
    return session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.stages),
            selectinload(Project.clips)
            .selectinload(Clip.publications)
            .selectinload(Publication.metric_snapshots),
            selectinload(Project.clips)
            .selectinload(Clip.publications)
            .selectinload(Publication.account_link)
            .selectinload(PublicationAccountLink.account),
            selectinload(Project.clips)
            .selectinload(Clip.publications)
            .selectinload(Publication.provider_reference),
        )
    )
