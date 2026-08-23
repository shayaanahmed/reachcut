from __future__ import annotations

import shutil
import threading
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.api.schemas import ApprovalRequest, HealthResponse, ProjectResponse
from clipper.config import settings
from clipper.db import Clip, Project, SessionLocal, get_session, now_utc
from clipper.domain.editing_plan import EditingPlanV1
from clipper.providers.ollama import OllamaEditorialProvider
from clipper.providers.whisper import FasterWhisperProvider
from clipper.services.media import MediaError, safe_filename, store_upload
from clipper.services.pipeline import Pipeline
from clipper.services.render import render_vertical

router = APIRouter(prefix="/api")
transcription_provider = FasterWhisperProvider(settings.whisper_model)
editorial_provider = OllamaEditorialProvider(
    settings.editorial_base_url,
    settings.editorial_model,
    cache_dir=settings.data_dir / "cache" / "editorial",
)
pipeline = Pipeline(settings, transcription_provider, editorial_provider)
pipeline_lock = threading.Lock()
logger = structlog.get_logger()


def _run_pipeline(project_id: str) -> None:
    with pipeline_lock, SessionLocal() as session:
        try:
            pipeline.run(session, project_id)
        except Exception as error:
            logger.exception(
                "pipeline_failed",
                project_id=project_id,
                error_category=type(error).__name__,
            )


def _project_or_404(session: Session, project_id: str) -> Project:
    project = session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.stages), selectinload(Project.clips))
    )
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ffmpeg=shutil.which("ffmpeg") is not None,
        ffprobe=shutil.which("ffprobe") is not None,
        editorial_provider=editorial_provider.identity,
        transcription_provider=transcription_provider.identity,
    )


@router.get("/projects", response_model=list[ProjectResponse])
def projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .options(selectinload(Project.stages), selectinload(Project.clips))
            .order_by(Project.created_at.desc())
        )
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def project(project_id: str, session: Session = Depends(get_session)) -> Project:
    return _project_or_404(session, project_id)


@router.post(
    "/projects/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
def upload_project(
    title: str = Form(min_length=1, max_length=200),
    authorization_confirmed: bool = Form(),
    media: UploadFile = File(),
    session: Session = Depends(get_session),
) -> Project:
    if not authorization_confirmed:
        raise HTTPException(status_code=422, detail="media authorization confirmation is required")
    project_id = str(uuid4())
    filename = safe_filename(media.filename or "source.mp4")
    target = settings.data_dir.resolve() / "projects" / project_id / "source" / filename
    try:
        stored = store_upload(media.file, target, settings.max_upload_bytes)
    except MediaError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    project = Project(
        id=project_id,
        title=title,
        original_filename=filename,
        source_path=str(stored.path),
        media_sha256=stored.sha256,
        authorization_confirmed_at=now_utc(),
    )
    session.add(project)
    session.commit()
    return _project_or_404(session, project.id)


@router.post("/projects/{project_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    project = _project_or_404(session, project_id)
    if project.status == "processing":
        raise HTTPException(status_code=409, detail="project is already processing")
    project.status = "processing"
    session.commit()
    background_tasks.add_task(_run_pipeline, project_id)
    return {"status": "queued", "project_id": project_id}


@router.post("/projects/{project_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    project = _project_or_404(session, project_id)
    project.status = "cancel_requested"
    session.commit()
    return {"status": "cancel_requested"}


@router.put("/clips/{clip_id}/approval", response_model=ProjectResponse)
def approve_clip(
    clip_id: str, request: ApprovalRequest, session: Session = Depends(get_session)
) -> Project:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="clip not found")
    clip.approval_status = "approved" if request.approved else "rejected"
    session.commit()
    return _project_or_404(session, clip.project_id)


@router.get("/clips/{clip_id}/preview", response_class=FileResponse)
def clip_preview(clip_id: str, session: Session = Depends(get_session)) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if not clip or not clip.preview_path or not Path(clip.preview_path).is_file():
        raise HTTPException(status_code=404, detail="preview not found")
    return FileResponse(
        clip.preview_path, media_type="video/mp4", filename=f"{clip.id}-preview.mp4"
    )


@router.post("/clips/{clip_id}/render", status_code=status.HTTP_201_CREATED)
def render_clip(clip_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="clip not found")
    if clip.approval_status != "approved":
        raise HTTPException(
            status_code=409, detail="clip must be explicitly approved before render"
        )
    project = session.get(Project, clip.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    root = Path(project.source_path).parent / "clips" / clip.id
    output = root / "final.mp4"
    try:
        render_vertical(
            Path(project.source_path),
            EditingPlanV1.model_validate(clip.plan),
            root / "captions.srt",
            output,
            preview=False,
        )
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    clip.final_path = str(output)
    session.commit()
    return {
        "status": "rendered",
        "clip_id": clip.id,
        "download_url": f"/api/clips/{clip.id}/final",
    }


@router.get("/clips/{clip_id}/final", response_class=FileResponse)
def clip_final(clip_id: str, session: Session = Depends(get_session)) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if not clip or not clip.final_path or not Path(clip.final_path).is_file():
        raise HTTPException(status_code=404, detail="final render not found")
    return FileResponse(clip.final_path, media_type="video/mp4", filename=f"{clip.id}.mp4")
