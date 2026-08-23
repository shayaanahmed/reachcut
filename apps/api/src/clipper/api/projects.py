from uuid import uuid4

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
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.api.dependencies import find_project, run_pipeline
from clipper.api.schemas import ProcessRequest, ProjectResponse
from clipper.config import settings
from clipper.media import MediaError, safe_filename, store_upload
from clipper.persistence import Project, get_session, now_utc

router = APIRouter()


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
            .options(selectinload(Project.stages), selectinload(Project.clips))
            .order_by(Project.created_at.desc())
        )
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def project(project_id: str, session: Session = Depends(get_session)) -> Project:
    return project_or_404(session, project_id)


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
    created = Project(
        id=project_id,
        title=title,
        original_filename=filename,
        source_path=str(stored.path),
        media_sha256=stored.sha256,
        authorization_confirmed_at=now_utc(),
    )
    session.add(created)
    session.commit()
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
