from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.api.dependencies import find_project, project_queue
from clipper.api.schemas import (
    ClipTypeSuggestionResponse,
    ProcessRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    UrlImportRequest,
)
from clipper.config import settings
from clipper.domain.editing_plan import ClipType
from clipper.domain.transcript import Transcript
from clipper.editorial import suggest_clip_types
from clipper.media import MediaError, safe_filename, store_upload, validate_public_media_url
from clipper.persistence import (
    Clip,
    Project,
    Publication,
    PublicationAccountLink,
    get_session,
    now_utc,
)
from clipper.persistence.models import ChannelPreset, RuntimeSetting
from clipper.projects import ProjectService
from clipper.projects.publishing_uploads import upload_publishing_video

router = APIRouter()
project_service = ProjectService(settings.data_dir / "projects")


def project_or_404(session: Session, project_id: str) -> Project:
    project = find_project(session, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/projects", response_model=list[ProjectResponse])
def projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
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
            .order_by(Project.created_at.desc())
        )
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def project(project_id: str, session: Session = Depends(get_session)) -> Project:
    return project_or_404(session, project_id)


@router.get(
    "/projects/{project_id}/clip-types",
    response_model=list[ClipTypeSuggestionResponse],
)
def project_clip_types(project_id: str, session: Session = Depends(get_session)) -> list[object]:
    selected = project_or_404(session, project_id)
    if not selected.transcript:
        return []
    return list(suggest_clip_types(Transcript.model_validate(selected.transcript)))


@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    session: Session = Depends(get_session),
) -> Project:
    selected = project_or_404(session, project_id)
    return project_service.rename(session, selected, request.title)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, session: Session = Depends(get_session)) -> Response:
    selected = project_or_404(session, project_id)
    try:
        project_service.delete(session, selected)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/upload", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
def upload_project(
    title: str = Form(min_length=1, max_length=200, pattern=r"\S"),
    authorization_confirmed: bool = Form(),
    media: UploadFile = File(),
    language: str | None = Form(default=None, pattern=r"^(?:[a-z]{2}|ur-en)$"),
    preset_id: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> Project:
    if not authorization_confirmed:
        raise HTTPException(status_code=422, detail="media authorization confirmation is required")
    if preset_id and not session.get(ChannelPreset, preset_id):
        raise HTTPException(422, "Channel preset not found")
    project_id = str(uuid4())
    filename = safe_filename(media.filename or "source.mp4")
    target = settings.data_dir.resolve() / "projects" / project_id / "source" / filename
    try:
        stored = store_upload(media.file, target, settings.max_upload_bytes)
    except MediaError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    created = project_service.create(
        session,
        project_id,
        title,
        filename,
        stored,
    )
    language = save_project_preset(session, created.id, preset_id, language)
    project_queue.enqueue(session, created, language=language)
    return project_or_404(session, created.id)


@router.post(
    "/projects/upload-for-publishing",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_for_publishing(
    title: str = Form(min_length=1, max_length=200, pattern=r"\S"),
    authorization_confirmed: bool = Form(),
    media: UploadFile = File(),
    session: Session = Depends(get_session),
) -> Project:
    if not authorization_confirmed:
        raise HTTPException(status_code=422, detail="media authorization confirmation is required")
    try:
        created = upload_publishing_video(
            session,
            settings.data_dir / "projects",
            title,
            media.filename or "video.mp4",
            media.file,
            settings.max_upload_bytes,
            settings.max_duration_seconds,
        )
    except MediaError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    return project_or_404(session, created.id)


@router.post(
    "/projects/import-url",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_project_url(
    request: UrlImportRequest,
    session: Session = Depends(get_session),
) -> Project:
    if not request.authorization_confirmed:
        raise HTTPException(status_code=422, detail="media authorization confirmation is required")
    try:
        url = validate_public_media_url(request.url, settings.media_import_hosts)
        project_id = str(uuid4())
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    created = Project(
        id=project_id,
        title=request.title.strip(),
        original_filename="Pending URL import",
        source_path=str(
            settings.data_dir.resolve() / "projects" / project_id / "source" / "source.mp4"
        ),
        media_sha256="",
        authorization_confirmed_at=now_utc(),
        status="created",
    )
    session.add(created)
    session.flush()
    language = save_project_preset(session, created.id, request.preset_id, request.language)
    project_queue.enqueue(session, created, language=language, source_url=url)
    return project_or_404(session, created.id)


@router.post("/projects/{project_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_project(
    project_id: str,
    request: ProcessRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    selected = project_or_404(session, project_id)
    try:
        project_queue.enqueue(
            session,
            selected,
            request.language if request else None,
            tuple(request.clip_types) if request else (),
            processing_mode=request.processing_mode if request else "clips",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"status": "queued", "project_id": project_id}


@router.post("/projects/{project_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    selected = project_or_404(session, project_id)
    project_queue.cancel(session, selected)
    return {"status": selected.status}


@router.post("/projects/{project_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    selected = project_or_404(session, project_id)
    if selected.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=409, detail="only failed or cancelled projects can be retried"
        )
    project_queue.enqueue(session, selected, retry=True)
    return {"status": "queued", "project_id": project_id}


@router.get("/projects/{project_id}/source")
def source_media(project_id: str, session: Session = Depends(get_session)) -> FileResponse:
    project = session.get(Project, project_id)
    if not project or not Path(project.source_path).is_file():
        raise HTTPException(404, "Source video is not available yet")
    return FileResponse(project.source_path, media_type="video/mp4")


@router.get("/projects/{project_id}/quality")
def project_quality(project_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    import json

    from clipper.projects.stages import StageRunner

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Source video not found")
    artifact = StageRunner.artifact_path(project, "quality_review")
    if not artifact.is_file():
        return {"version": "1", "clips": [], "limitations": "Rendered review has not run yet."}
    try:
        payload: dict[str, object] = json.loads(artifact.read_text())
        return payload
    except (ValueError, OSError) as error:
        raise HTTPException(409, "Review artifact is unavailable; retry processing") from error


@router.post("/projects/{project_id}/stages/{stage_name}/retry")
def retry_stage(
    project_id: str, stage_name: str, session: Session = Depends(get_session)
) -> dict[str, str]:
    from clipper.projects.pipeline import Pipeline

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Source video not found")
    if project.status in {"queued", "downloading", "processing", "cancel_requested"}:
        raise HTTPException(409, "Stop processing before retrying a stage")
    stages = (*Pipeline.STAGES, "generate_metadata")
    if stage_name not in stages:
        raise HTTPException(422, "Unknown processing stage")
    affected = stages[stages.index(stage_name) :]
    if stage_name == "analyze_visuals":
        affected = tuple(name for name in affected if name != "transcribe")
    for stage in project.stages:
        if stage.name in affected:
            stage.cache_key = None
    session.commit()
    job = project.job
    project_queue.enqueue(
        session,
        project,
        language=job.language if job else None,
        clip_types=tuple(ClipType(value) for value in job.clip_types) if job else (),
        processing_mode=job.processing_mode if job else "clips",
    )
    return {"status": "queued"}


def save_project_preset(
    session: Session, project_id: str, preset_id: str | None, language: str | None
) -> str | None:
    import json

    if not preset_id:
        return language
    preset = session.get(ChannelPreset, preset_id)
    if not preset:
        raise HTTPException(422, "Channel preset not found")
    session.add(
        RuntimeSetting(key=f"project-preset:{project_id}", value=json.dumps(preset.settings))
    )
    inherited = str(preset.settings.get("language", "en"))
    return language or inherited
