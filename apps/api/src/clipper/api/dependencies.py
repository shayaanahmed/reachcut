import fcntl
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.config import settings
from clipper.domain.editing_plan import ClipType
from clipper.media import StoredUpload, validate_public_media_url
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
    PublicationStateError,
    PublishingConnectionService,
    RuntimeSettingsService,
    StoryReferenceService,
    StoryVideoService,
    ThumbnailService,
)
from clipper.projects.metadata_pipeline import MetadataPipeline
from clipper.projects.queue import ProjectQueue
from clipper.providers.credentials import EncryptedCredentialStore
from clipper.providers.local_video_runtime import LocalVideoEngineSupervisor
from clipper.providers.ltx_desktop import LtxDesktopVideoProvider
from clipper.providers.meta import FacebookPublishingAdapter, InstagramPublishingAdapter
from clipper.providers.ollama import EditorialGenerationConfig, OllamaEditorialProvider
from clipper.providers.ollama_metadata import OllamaMetadataProvider
from clipper.providers.ollama_thumbnail import OllamaThumbnailProvider
from clipper.providers.ollama_translation import OllamaCaptionTranslationProvider
from clipper.providers.opencv_tracking import OpenCvVisualTrackingProvider
from clipper.providers.publishing_http import safe_provider_error
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


def build_transcription_provider(
    language: str | None = None, model: str | None = None
) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        model or settings.whisper_model,
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
growth_lock = threading.Lock()
pipeline_lock = threading.Lock()
automation_lock = threading.Lock()
local_video_lock = threading.Lock()
logger = structlog.get_logger()


publication_upload_slots = threading.BoundedSemaphore(4)


def run_publication_batch(
    queued: list[tuple[str, AutomaticPublicationCreate]],
) -> None:
    """Publish queued destinations concurrently without holding the request open."""
    if not queued:
        return

    def publish_one(publication_id: str, request: AutomaticPublicationCreate) -> None:
        with publication_upload_slots, SessionLocal() as session:
            publication = session.get(Publication, publication_id)
            adapter = publishing_adapters.get(publication.platform) if publication else None
            if not publication or not adapter:
                publication_service.mark_failed(
                    session,
                    publication_id,
                    "No publishing adapter is configured for this platform.",
                )
                return
            if publication.status != "queued":
                return
            if publication.clip.project.status in {
                "queued",
                "downloading",
                "processing",
                "cancel_requested",
                "failed",
            }:
                return  # A queued upload must use the completed pipeline's latest growth copy.
            try:
                from clipper.persistence.models import ClipGrowthBrief, GrowthPreparation
                from clipper.projects.growth import capture_growth_context
                from clipper.projects.growth_automation import automatic_copy, request_preparation

                runtime = runtime_settings_service.get(session)
                saved = session.get(ClipGrowthBrief, publication.clip_id)
                manual = saved is not None and saved.payload.get("automatic") is False
                if runtime.automatic_growth and not manual:
                    job = session.get(GrowthPreparation, publication.clip_id)
                    if job is None or job.status not in {"ready", "manual"}:
                        if job is None:
                            request_preparation(session, publication.clip)
                        return  # Durable queue resumes after automatic preparation completes.
                copy = automatic_copy(session, publication.clip_id, publication.platform)
                if copy:
                    request = AutomaticPublicationCreate(
                        request.social_account_id, copy[0], copy[1], request.privacy_status
                    )
                    publication.title, publication.description = copy
                    capture_growth_context(session, publication, publication.clip_id)
                    session.commit()
                publication_service.publish_queued(
                    session,
                    publication_id,
                    request,
                    adapter,
                    credential_store,
                )
            except PublicationStateError as error:
                session.rollback()
                session.refresh(publication)
                if publication.status == "queued":
                    publication_service.mark_failed(session, publication_id, str(error))
                    if publication.social_account_id:
                        from clipper.projects.account_health import record_account_issue

                        record_account_issue(session, publication.social_account_id, error)
                return  # A different worker may own an upload already in progress.
            except Exception as error:
                session.rollback()
                publication_service.mark_failed(session, publication_id, str(error))
                if publication.social_account_id:
                    from clipper.projects.account_health import record_account_issue

                    record_account_issue(session, publication.social_account_id, error)
                logger.error(
                    "background_publication_failed",
                    error=safe_provider_error(str(error)),
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


project_queue = ProjectQueue()


def analyze_project(
    session: Session,
    project_id: str,
    language: str | None,
    clip_types: tuple[ClipType, ...],
) -> None:
    runtime = runtime_settings_service.get(session)
    project = session.get(Project, project_id)
    from clipper.projects.source_evidence import visual_evidence

    metadata_pipeline = MetadataPipeline(
        settings,
        build_transcription_provider(language, runtime.transcription_model),
        OllamaMetadataProvider(
            runtime.ollama_base_url,
            runtime.model_for("metadata"),
            settings.editorial_timeout_seconds,
        ),
        lambda db, clip: visual_evidence(db, clip, runtime),
    )
    if project and project.job and project.job.processing_mode == "language":
        from clipper.projects.language_versions import localize_project
        from clipper.projects.source_workflows import active_workflow

        run = active_workflow(session, project.id)
        original_copy = (
            {
                clip.id: {
                    key: clip.plan.get(key)
                    for key in ("suggested_title", "suggested_description", "hashtags")
                }
                for clip in project.clips
            }
            if run and "metadata" not in run.scopes
            else {}
        )
        metadata_pipeline.run(session, project, final_status="processing")
        for clip in project.clips:
            if clip.id in original_copy:
                clip.plan = {**clip.plan, **original_copy[clip.id]}
        session.commit()
        localize_project(session, project, runtime, clip_service)
        return
    if project and project.job and project.job.processing_mode == "metadata":
        from clipper.projects.source_workflows import active_workflow

        run = active_workflow(session, project.id)
        if run and run.clip_ids:
            metadata_pipeline.run(
                session, project, final_status="processing", clip_ids=run.clip_ids
            )
            optimize_pipeline_growth(session, project, metadata_only=True, clip_ids=run.clip_ids)
        else:
            metadata_pipeline.run(session, project, final_status="processing")
            optimize_pipeline_growth(session, project, metadata_only=True)
        project.status = "complete"
        session.commit()
        return
    selected_pipeline = Pipeline(
        settings,
        build_transcription_provider(language, runtime.transcription_model),
        build_editorial_provider(runtime.ollama_base_url, runtime.model_for("clip_selection")),
        visual_tracking_provider,
    )
    selected_pipeline.run(session, project_id, clip_types=clip_types)
    if project:
        metadata_pipeline.run(session, project, final_status="processing")
        optimize_pipeline_growth(session, project, metadata_only=False)
        project.status = "review"
        session.commit()


def download_project_media(url: str, target: Path) -> StoredUpload:
    validated = validate_public_media_url(url, settings.media_import_hosts)
    return media_downloader.download(validated, target, settings.max_upload_bytes)


def run_project_cycle(*, recover: bool = False) -> str | None:
    """One worker across threads and API processes, with durable FIFO ordering."""
    if not pipeline_lock.acquire(blocking=False):
        return None
    try:
        with (settings.data_dir / "project-worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            with SessionLocal() as session:
                # Owning the process lock proves any running row is interrupted work.
                # This also recovers a crashed worker when another API process stays up.
                project_queue.recover(session)
                if recover:
                    return None
                return project_queue.run_next(
                    session,
                    download_project_media,
                    analyze_project,
                )
    finally:
        pipeline_lock.release()


def queue_project(project_id: str, clip_types: tuple[ClipType, ...]) -> None:
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        if not project:
            raise LookupError("project not found")
        project_queue.enqueue(session, project, clip_types=clip_types)


def run_story_video(video_id: str) -> None:
    """Render one local story at a time; model weights are intentionally reused."""

    with (
        local_video_lock,
        (settings.data_dir / "hardware-worker.lock").open("a") as lock,
        SessionLocal() as session,
    ):
        fcntl.flock(lock, fcntl.LOCK_EX)
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
        with (settings.data_dir / "hardware-worker.lock").open("a") as hardware_lock:
            try:
                fcntl.flock(hardware_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            return _run_story_cycle_locked()
    finally:
        local_video_lock.release()


def _run_story_cycle_locked() -> str | None:
    with SessionLocal() as session:
        video_id = session.scalar(
            select(StoryVideo.id)
            .where(StoryVideo.status.in_(("queued", "rendering", "finishing", "cancel_requested")))
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
            prepare_growth=growth_ready_for_render,
            analyze_project=queue_project,
        )


def find_project(session: Session, project_id: str) -> Project | None:
    return session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.clips)
            .selectinload(Clip.publications)
            .selectinload(Publication.failure),
            selectinload(Project.job),
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


def run_informative_cycle() -> str | None:
    from clipper.api.informative import short_service
    from clipper.shorts.queue import run_next

    if not local_video_lock.acquire(blocking=False):
        return None
    try:
        with (settings.data_dir / "hardware-worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            with SessionLocal() as session:
                return run_next(session, short_service)
    finally:
        local_video_lock.release()


def run_publication_cycle() -> None:
    from clipper.persistence.models import PublicationOptions

    with SessionLocal() as session:
        rows = session.execute(
            select(Publication, PublicationOptions)
            .join(PublicationOptions)
            .where(Publication.status == "queued")
            .order_by(Publication.created_at)
            .limit(20)
        ).all()
        queued = [
            (
                publication.id,
                AutomaticPublicationCreate(
                    social_account_id=publication.social_account_id or "",
                    title=publication.title,
                    description=publication.description,
                    privacy_status=options.privacy_status,
                ),
            )
            for publication, options in rows
        ]
    run_publication_batch(queued)


def run_growth_cycle() -> str | None:
    from clipper.projects.growth_automation import run_next
    from clipper.providers.ollama_growth import OllamaGrowthProvider

    if not growth_lock.acquire(blocking=False):
        return None
    try:
        with (settings.data_dir / "growth-worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            with SessionLocal() as session:
                runtime = runtime_settings_service.get(session)
                if runtime.automatic_growth:
                    from clipper.projects.growth_metrics import refresh_growth_metrics

                    refresh_growth_metrics(
                        session, publication_service, metrics_adapters, credential_store
                    )
                return run_next(
                    session,
                    runtime,
                    OllamaGrowthProvider(
                        runtime.ollama_base_url,
                        runtime.model_for("growth"),
                        min(settings.editorial_timeout_seconds, 180),
                    ),
                    clip_service.apply_growth_plan,
                )
    finally:
        growth_lock.release()


def growth_ready_for_render(session: Session, clip: Clip) -> bool:
    from clipper.persistence.models import ClipGrowthBrief, GrowthPreparation
    from clipper.projects.growth_automation import request_preparation

    if not runtime_settings_service.get(session).automatic_growth:
        return True
    saved = session.get(ClipGrowthBrief, clip.id)
    if saved and saved.payload.get("automatic") is False:
        return True
    job = session.get(GrowthPreparation, clip.id)
    if job is None:
        request_preparation(session, clip)
        return False
    return job.status in {"ready", "manual"}


def optimize_pipeline_growth(
    session: Session, project: Project, *, metadata_only: bool, clip_ids: list[str] | None = None
) -> None:
    from clipper.projects.growth_pipeline import optimize_project
    from clipper.providers.ollama_growth import OllamaGrowthProvider

    runtime = runtime_settings_service.get(session)
    # The project worker owns this project; background growth skips processing projects.
    if project.job:
        project.job.phase = "Waiting for audience and growth analysis"
        session.commit()
    with growth_lock, (settings.data_dir / "growth-worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        optimize_project(
            session,
            project,
            runtime,
            OllamaGrowthProvider(
                runtime.ollama_base_url,
                runtime.model_for("growth"),
                min(settings.editorial_timeout_seconds, 180),
            ),
            None if metadata_only else clip_service.apply_growth_plan,
            clip_ids=clip_ids,
        )
