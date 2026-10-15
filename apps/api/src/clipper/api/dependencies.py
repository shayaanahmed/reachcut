import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.config import settings
from clipper.domain.editing_plan import ClipType
from clipper.persistence import (
    Clip,
    Project,
    Publication,
    PublicationAccountLink,
    SessionLocal,
    StoryVideo,
)
from clipper.projects import (
    AutomaticPublicationCreate,
    AutomationService,
    ClipService,
    Pipeline,
    PublicationService,
    PublishingConnectionService,
    RuntimeSettingsService,
    StoryReferenceService,
    StoryVideoService,
    ThumbnailService,
)
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.local_video_runtime import LocalVideoEngineSupervisor
from clipper.providers.ltx_desktop import LtxDesktopVideoProvider
from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.ollama import EditorialGenerationConfig, OllamaEditorialProvider
from clipper.providers.ollama_thumbnail import OllamaThumbnailProvider
from clipper.providers.ollama_translation import OllamaCaptionTranslationProvider
from clipper.providers.opencv_tracking import OpenCvVisualTrackingProvider
from clipper.providers.social_oauth import (
    FacebookOAuthClient,
    InstagramOAuthClient,
    OAuthAppConfig,
    TikTokOAuthClient,
    XOAuthClient,
)
from clipper.providers.tiktok import TikTokPublishingAdapter
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
from clipper.rendering import ThumbnailRenderer
from clipper.rendering.story_video import StoryVideoFinisher


def build_transcription_provider(language: str | None = None) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language_hint=language,
    )


transcription_provider = build_transcription_provider()


def build_editorial_provider(
    base_url: str | None = None, model: str | None = None
) -> OllamaEditorialProvider:
    return OllamaEditorialProvider(
        base_url or settings.editorial_base_url,
        model or settings.editorial_model,
        timeout_seconds=settings.editorial_timeout_seconds,
        cache_dir=settings.data_dir / "cache" / "editorial",
        generation=EditorialGenerationConfig(
            num_ctx=settings.editorial_num_ctx,
            num_predict=settings.editorial_num_predict,
            retry_num_ctx=settings.editorial_retry_num_ctx,
            retry_num_predict=settings.editorial_retry_num_predict,
        ),
    )


editorial_provider = build_editorial_provider()


def build_thumbnail_provider(
    base_url: str | None = None, model: str | None = None
) -> OllamaThumbnailProvider:
    return OllamaThumbnailProvider(
        base_url or settings.editorial_base_url,
        model or settings.thumbnail_model,
        timeout_seconds=settings.editorial_timeout_seconds,
    )


caption_translation_provider = OllamaCaptionTranslationProvider(
    settings.editorial_base_url,
    settings.editorial_model,
    timeout_seconds=settings.editorial_timeout_seconds,
)
visual_tracking_provider = (
    OpenCvVisualTrackingProvider(settings.tracking_sample_interval_seconds)
    if settings.tracking_provider == "opencv"
    else None
)
pipeline = Pipeline(
    settings,
    transcription_provider,
    editorial_provider,
    visual_tracking_provider,
)
clip_service = ClipService(
    pipeline.artifacts,
    pipeline.renderer,
    caption_translation_provider,
    visual_tracking_provider,
    settings.max_secondary_media_bytes,
    settings.data_dir / "projects",
)
thumbnail_service = ThumbnailService(
    pipeline.artifacts,
    ThumbnailRenderer(),
    settings.data_dir / "projects",
    logo_path=Path(__file__).parents[1] / "rendering" / "assets" / "siratsoul-symbol.png",
)
local_video_provider = LtxDesktopVideoProvider(
    settings.local_video_engine_url,
    settings.local_video_engine_token,
    settings.local_video_timeout_seconds,
    settings.local_video_engine_data_dir,
)
local_video_supervisor = LocalVideoEngineSupervisor(
    settings.local_video_engine_root,
    settings.local_video_engine_data_dir,
    settings.local_video_engine_url,
    settings.local_video_engine_token,
)
story_video_service = StoryVideoService(
    settings.data_dir / "story-videos",
    local_video_provider,
    StoryVideoFinisher(),
)
story_reference_service = StoryReferenceService(settings.data_dir / "story-video-references")
media_downloader = YtDlpDownloader(
    settings.yt_dlp_repository,
    timeout_seconds=settings.yt_dlp_timeout_seconds,
)
credential_store = EncryptedCredentialStore(settings.data_dir)
runtime_settings_service = RuntimeSettingsService(settings)
automation_service = AutomationService()
publication_service = PublicationService()
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
    "instagram": InstagramOAuthClient(
        OAuthAppConfig(
            settings.instagram_app_id,
            settings.instagram_app_secret,
            settings.instagram_redirect_uri,
            settings.instagram_login_config_id,
        ),
        settings.graph_api_version,
    ),
    "facebook": FacebookOAuthClient(
        OAuthAppConfig(
            settings.facebook_app_id,
            settings.facebook_app_secret,
            settings.facebook_redirect_uri,
            settings.facebook_login_config_id,
        ),
        settings.graph_api_version,
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
instagram_publisher = InstagramPublishingAdapter(settings.graph_api_version)
facebook_publisher = FacebookPublishingAdapter(settings.graph_api_version)
publishing_adapters: dict[str, PublishingAdapter] = {
    "youtube": youtube_publisher,
    "tiktok": TikTokPublishingAdapter(settings.tiktok_client_key, settings.tiktok_client_secret),
    "instagram": instagram_publisher,
    "facebook": facebook_publisher,
    "x": XPublishingAdapter(settings.x_client_id, settings.x_client_secret),
}
metrics_adapters: dict[str, MetricsAdapter] = {
    "youtube": youtube_publisher,
    "instagram": instagram_publisher,
    "facebook": facebook_publisher,
}
publishing_connections = PublishingConnectionService(social_oauth_clients, credential_store)
pipeline_lock = threading.Lock()
automation_lock = threading.Lock()
local_video_lock = threading.Lock()
logger = structlog.get_logger()


def run_publication_batch(
    queued: list[tuple[str, AutomaticPublicationCreate]],
) -> None:
    """Publish queued destinations concurrently without holding the request open."""

    def publish_one(publication_id: str, request: AutomaticPublicationCreate) -> None:
        with SessionLocal() as session:
            publication = session.get(Publication, publication_id)
            adapter = publishing_adapters.get(publication.platform) if publication else None
            if not publication or not adapter:
                publication_service.mark_failed(session, publication_id)
                return
            try:
                publication_service.publish_queued(
                    session,
                    publication_id,
                    request,
                    adapter,
                    credential_store,
                )
            except Exception as error:
                session.rollback()
                publication_service.mark_failed(session, publication_id)
                logger.exception(
                    "background_publication_failed",
                    publication_id=publication_id,
                    platform=publication.platform,
                    error_category=type(error).__name__,
                )

    with ThreadPoolExecutor(max_workers=min(len(queued), 4)) as executor:
        futures = [
            executor.submit(publish_one, publication_id, request)
            for publication_id, request in queued
        ]
        for future in futures:
            future.result()


def run_pipeline(
    project_id: str,
    language: str | None = None,
    clip_types: tuple[ClipType, ...] = (),
) -> None:
    """Background-task entry point with a fresh database session."""

    with pipeline_lock, SessionLocal() as session:
        try:
            runtime = runtime_settings_service.get(session)
            selected_transcription = build_transcription_provider(language)
            selected_pipeline = Pipeline(
                settings,
                selected_transcription,
                build_editorial_provider(runtime.ollama_base_url, runtime.editorial_model),
                visual_tracking_provider,
            )
            selected_pipeline.run(session, project_id, clip_types=clip_types)
        except Exception as error:
            logger.exception(
                "pipeline_failed",
                project_id=project_id,
                error_category=type(error).__name__,
            )


def run_story_video(video_id: str) -> None:
    """Render one local story at a time; model weights are intentionally reused."""

    with local_video_lock, SessionLocal() as session:
        try:
            story_video_service.render(session, video_id)
        except Exception as error:
            logger.exception(
                "story_video_failed",
                video_id=video_id,
                error_category=type(error).__name__,
            )


def run_story_video_cycle() -> str | None:
    """Render the oldest durable story job when the local engine is ready."""

    if not local_video_lock.acquire(blocking=False):
        return None
    try:
        with SessionLocal() as session:
            video_id = session.scalar(
                select(StoryVideo.id)
                .where(
                    StoryVideo.status.in_(("queued", "rendering", "finishing", "cancel_requested"))
                )
                .order_by(StoryVideo.created_at.asc())
                .limit(1)
            )
            if not video_id:
                return None
            video = story_video_service.get(session, video_id)
            if video.status == "cancel_requested":
                story_video_service.render(session, video_id)
                return video_id
            try:
                local_video_provider.health()
                progress = local_video_provider.generation_progress()
                if progress.get("status") == "running":
                    video = story_video_service.get(session, video_id)
                    if video.status in {"cancel_requested", "cancelled"}:
                        story_video_service.render(session, video_id)
                        return None
                    video.status = "queued"
                    video.phase = (
                        f"Waiting for LTX ({progress.get('progress', 0)}%). "
                        "This short will resume automatically; saved scenes kept."
                    )
                    video.error = None
                    session.commit()
                    return None
                recommendation = local_video_provider.model_recommendation()
                if recommendation.get("status") == "download":
                    return None
            except Exception:
                return None
            try:
                story_video_service.render(session, video_id)
            except Exception as error:
                logger.exception(
                    "story_video_failed",
                    video_id=video_id,
                    error_category=type(error).__name__,
                )
            return video_id
    finally:
        local_video_lock.release()


def run_automation_cycle(pipeline_id: str | None = None) -> list[str]:
    """Execute due publishing pipelines with a fresh database session."""

    with automation_lock, SessionLocal() as session:
        return automation_service.execute_due(
            session,
            clip_service,
            publication_service,
            publishing_adapters,
            credential_store,
            pipeline_id=pipeline_id,
            analyze_project=lambda project_id, clip_types: run_pipeline(
                project_id, None, clip_types
            ),
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
