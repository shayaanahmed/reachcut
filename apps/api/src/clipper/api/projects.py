from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.api.dependencies import find_project, media_downloader, run_pipeline
from clipper.api.schemas import (
    ProcessRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    UrlImportRequest,
)
from clipper.config import settings
from clipper.media import MediaError, safe_filename, store_upload, validate_public_media_url
from clipper.persistence import (
    Clip,
    Project,
    Publication,
    PublicationAccountLink,
    get_session,
)
from clipper.projects import ProjectService

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
    created = project_service.create(
        session,
        project_id,
        title,
        filename,
        stored,
    )
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
        target = settings.data_dir.resolve() / "projects" / project_id / "source"
        stored = media_downloader.download(url, target, settings.max_upload_bytes)
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    created = project_service.create(
        session,
        project_id,
        request.title,
        stored.path.name,
        stored,
    )
    return project_or_404(session, created.id)


@router.post("/projects/{project_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: ProcessRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    selected = project_or_404(session, project_id)
    if selected.status == "processing":
        raise HTTPException(status_code=409, detail="project is already processing")
    selected.status = "processing"
    session.commit()
    background_tasks.add_task(run_pipeline, project_id, request.language if request else None)
    return {"status": "queued", "project_id": project_id}


@router.post("/projects/{project_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    selected = project_or_404(session, project_id)
    selected.status = "cancel_requested"
    session.commit()
    return {"status": "cancel_requested"}
