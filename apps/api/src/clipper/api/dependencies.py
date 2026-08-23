import threading

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.config import settings
from clipper.persistence import Project, SessionLocal
from clipper.projects import ClipService, Pipeline
from clipper.providers.ollama import EditorialGenerationConfig, OllamaEditorialProvider
from clipper.providers.whisper import FasterWhisperProvider


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
        .options(selectinload(Project.stages), selectinload(Project.clips))
    )
