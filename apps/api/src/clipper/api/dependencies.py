import threading

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.config import settings
from clipper.persistence import Project, SessionLocal
from clipper.projects import ClipService, Pipeline
from clipper.providers.ollama import OllamaEditorialProvider
from clipper.providers.whisper import FasterWhisperProvider

transcription_provider = FasterWhisperProvider(settings.whisper_model)
editorial_provider = OllamaEditorialProvider(
    settings.editorial_base_url,
    settings.editorial_model,
    cache_dir=settings.data_dir / "cache" / "editorial",
)
pipeline = Pipeline(settings, transcription_provider, editorial_provider)
clip_service = ClipService(pipeline.artifacts, pipeline.renderer)
pipeline_lock = threading.Lock()
logger = structlog.get_logger()


def run_pipeline(project_id: str, language: str | None = None) -> None:
    """Background-task entry point with a fresh database session."""

    with pipeline_lock, SessionLocal() as session:
        try:
            selected_transcription = FasterWhisperProvider(
                settings.whisper_model, language_hint=language
            )
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
