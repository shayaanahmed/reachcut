from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clipper.api.dependencies import credential_store, publication_service, run_publication_batch
from clipper.api.projects import project_or_404
from clipper.api.schemas import ProjectResponse, SocialPlatform
from clipper.persistence import get_session
from clipper.projects.distribution import (
    AccountGroupService,
    approve_clips,
    queue_project_publications,
)
from clipper.projects.publications import PublicationNotFoundError, PublicationStateError
from clipper.providers.credentials import CredentialStoreError

router = APIRouter()
groups = AccountGroupService()


class GroupWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    account_ids: list[str] = Field(default_factory=list, max_length=200)


class GroupResponse(GroupWrite):
    model_config = ConfigDict(from_attributes=True)
    id: str


class ClipSelection(BaseModel):
    # Null means all; an empty list is rejected rather than accidentally targeting all.
    clip_ids: list[str] | None = Field(default=None, min_length=1, max_length=200)


class ProjectPublishRequest(ClipSelection):
    account_ids: list[str] = Field(default_factory=list, max_length=200)
    group_id: str | None = None
    platform: SocialPlatform | None = None


@router.get("/social-account-groups", response_model=list[GroupResponse])
def list_groups(session: Session = Depends(get_session)) -> object:
    return groups.list_groups(session)


def save_group(session: Session, request: GroupWrite, group_id: str | None = None) -> object:
    try:
        return groups.save(session, group_id, **request.model_dump())
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "A group with this name already exists") from error


@router.post("/social-account-groups", response_model=GroupResponse, status_code=201)
def create_group(request: GroupWrite, session: Session = Depends(get_session)) -> object:
    return save_group(session, request)


@router.put("/social-account-groups/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: str, request: GroupWrite, session: Session = Depends(get_session)
) -> object:
    return save_group(session, request, group_id)


@router.delete("/social-account-groups/{group_id}", status_code=204)
def delete_group(group_id: str, session: Session = Depends(get_session)) -> Response:
    try:
        groups.delete(session, group_id)
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    return Response(status_code=204)


@router.post("/projects/{project_id}/clips/approve-batch", response_model=ProjectResponse)
def approve_batch(
    project_id: str, request: ClipSelection, session: Session = Depends(get_session)
) -> object:
    try:
        approve_clips(session, project_id, request.clip_ids)
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(409, str(error)) from error
    return project_or_404(session, project_id)


@router.post("/projects/{project_id}/publish-batch", status_code=202)
def publish_batch(
    project_id: str,
    request: ProjectPublishRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> object:
    try:
        queued, skipped = queue_project_publications(
            session,
            project_id,
            request.clip_ids,
            request.account_ids,
            request.group_id,
            request.platform,
            credential_store,
            publication_service,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except (PublicationStateError, CredentialStoreError) as error:
        session.rollback()
        raise HTTPException(409, str(error)) from error
    background_tasks.add_task(run_publication_batch, queued)
    return {
        "project": ProjectResponse.model_validate(project_or_404(session, project_id)),
        "queued": len(queued),
        "skipped": [
            {"clip_id": item.clip_id, "account_id": item.account_id, "reason": item.reason}
            for item in skipped
        ],
    }
