from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from clipper.api.dependencies import (
    credential_store,
    metrics_adapters,
    publication_service,
    publishing_adapters,
    run_publication_batch,
)
from clipper.api.projects import project_or_404
from clipper.api.schemas import (
    AutomaticPublicationBatchRequest,
    AutomaticPublicationRequest,
    MetricCreateRequest,
    ProjectResponse,
    PublicationCreateRequest,
)
from clipper.persistence import Clip, Publication, SocialAccount, get_session
from clipper.persistence.models import PostChange
from clipper.projects import (
    AutomaticPublicationCreate,
    MetricCreate,
    PublicationCreate,
    PublicationNotFoundError,
    PublicationStateError,
)
from clipper.projects.post_management import (
    capabilities,
    clip_copy,
    connection_issue,
    deletion_issue,
    manage_post,
    suggested_copy,
)
from clipper.providers.credentials import CredentialStoreError
from clipper.providers.publishing_http import ProviderApiError, safe_provider_error
from clipper.providers.youtube import YouTubeApiError, YouTubeConfigurationError

router = APIRouter()


@router.post(
    "/clips/{clip_id}/publish-batch",
    response_model=ProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def publish_clip_batch(
    clip_id: str,
    request: AutomaticPublicationBatchRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id, queued = publication_service.queue_many(
            session,
            clip_id,
            [AutomaticPublicationCreate(**item.model_dump()) for item in request.publications],
            credential_store,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CredentialStoreError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    background_tasks.add_task(run_publication_batch, queued)
    return project_or_404(session, project_id)


@router.post("/clips/{clip_id}/publish", response_model=ProjectResponse)
def publish_clip(
    clip_id: str,
    request: AutomaticPublicationRequest,
    session: Session = Depends(get_session),
) -> object:
    try:
        account = session.get(SocialAccount, request.social_account_id)
        if not account:
            raise PublicationNotFoundError("social account not found")
        adapter = publishing_adapters.get(account.platform)
        if not adapter:
            raise PublicationStateError(
                f"automatic publishing is not configured for {account.platform}"
            )
        project_id = publication_service.publish(
            session,
            clip_id,
            AutomaticPublicationCreate(**request.model_dump()),
            adapter,
            credential_store,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except YouTubeConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (CredentialStoreError, ProviderApiError, YouTubeApiError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/publications/{publication_id}/refresh", response_model=ProjectResponse)
def refresh_publication(
    publication_id: str,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = publication_service.refresh_publication(
            session,
            publication_id,
            publishing_adapters,
            credential_store,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CredentialStoreError, ProviderApiError, YouTubeApiError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/clips/{clip_id}/publications", response_model=ProjectResponse)
def create_publication(
    clip_id: str,
    request: PublicationCreateRequest,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = publication_service.create(
            session,
            clip_id,
            PublicationCreate(**request.model_dump()),
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/publications/{publication_id}/metrics", response_model=ProjectResponse)
def record_publication_metrics(
    publication_id: str,
    request: MetricCreateRequest,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = publication_service.record_metrics(
            session,
            publication_id,
            MetricCreate(**request.model_dump()),
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/publications/{publication_id}/metrics/sync", response_model=ProjectResponse)
def sync_publication_metrics(
    publication_id: str,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = publication_service.sync_metrics(
            session,
            publication_id,
            metrics_adapters,
            credential_store,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (CredentialStoreError, ProviderApiError, YouTubeApiError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.delete("/publications/{publication_id}", response_model=ProjectResponse)
def delete_publication(
    publication_id: str,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = publication_service.delete(session, publication_id)
    except PublicationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return project_or_404(session, project_id)


class PostEdit(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)


class RemoteDelete(BaseModel):
    confirm: bool


@router.get("/publications/{publication_id}/management")
def post_management(publication_id: str, session: Session = Depends(get_session)) -> object:
    post = session.get(Publication, publication_id)
    if not post:
        raise HTTPException(404, "Publication not found")
    title, description = suggested_copy(session, post)
    actions = capabilities(publishing_adapters.get(post.platform), post.platform)
    issue = (
        connection_issue(session, post, credential_store) if post.status == "published" else None
    )
    delete_issue = (
        deletion_issue(session, post, credential_store) if post.status == "published" else None
    )
    if delete_issue:
        actions["delete"] = False
    actions["deletion_issue"] = delete_issue
    actions["deletion_reconnect_required"] = bool(delete_issue and post.provider_publication_id)
    actions["reconnect_required"] = bool(issue)
    actions["connection_issue"] = issue
    actions["reconnect_url"] = (
        f"/api/social-accounts/{post.social_account_id}/connect" if post.social_account_id else None
    )
    if post.platform in {"instagram", "x"} and not post.provider_publication_id:
        actions["delete"] = False
        actions["explanation"] = str(actions["explanation"]) + (
            " No original media ID is saved; delete this post on its platform."
        )
    return {
        "capabilities": actions,
        "suggested": {"title": title, "description": description},
        "hashtag_notice": None
        if "#" in description
        else (
            "No relevant hashtags are available. "
            "Refresh publishing details to generate source-based tags."
        ),
        "draft_revision": post.clip.project.updated_at.isoformat(),
        "needs_update": description != post.description
        or (post.platform == "youtube" and title != post.title),
        "operation": {
            "state": post.management.state,
            "action": post.management.action,
            "error": post.management.error,
        }
        if post.management
        else None,
        "history": [
            {
                "action": change.action,
                "before": change.before,
                "after": change.after,
                "created_at": change.created_at,
            }
            for change in sorted(post.changes, key=lambda c: c.created_at, reverse=True)
        ],
    }


def perform_post_action(
    session: Session,
    publication_id: str,
    action: Literal["update", "delete"],
    title: str = "",
    description: str = "",
) -> object:
    try:
        project_id = manage_post(
            session,
            publication_id,
            action,
            publishing_adapters,
            credential_store,
            title=title,
            description=description,
        )
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except PublicationStateError as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(502, safe_provider_error(str(error))) from error
    return project_or_404(session, project_id)


@router.put("/publications/{publication_id}/remote", response_model=ProjectResponse)
def update_remote_post(
    publication_id: str, request: PostEdit, session: Session = Depends(get_session)
) -> object:
    return perform_post_action(
        session, publication_id, "update", request.title, request.description
    )


@router.post("/publications/{publication_id}/delete-remote", response_model=ProjectResponse)
def delete_remote_post(
    publication_id: str, request: RemoteDelete, session: Session = Depends(get_session)
) -> object:
    if not request.confirm:
        raise HTTPException(422, "Confirm deletion of the actual platform post")
    return perform_post_action(session, publication_id, "delete")


@router.post(
    "/publications/{publication_id}/publish-new", response_model=ProjectResponse, status_code=202
)
def publish_as_new(
    publication_id: str,
    request: RemoteDelete,
    tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> object:
    post = session.get(Publication, publication_id)
    if not post or not post.social_account_id:
        raise HTTPException(404, "Original publication or account not found")
    if not request.confirm:
        raise HTTPException(422, "Confirm creating a separate new platform post")
    if post.status != "published":
        raise HTTPException(409, "Only a published post can be duplicated explicitly")
    if post.management and post.management.state == "working":
        raise HTTPException(409, "Wait for the existing platform action to finish")
    title, description = suggested_copy(session, post)
    from clipper.projects import AutomaticPublicationCreate

    try:
        project_id, queued = publication_service.queue_many(
            session,
            post.clip_id,
            [AutomaticPublicationCreate(post.social_account_id, title, description)],
            credential_store,
            allow_new=True,
            commit=False,
        )
        session.add(
            PostChange(
                publication_id=post.id,
                action="publish_new",
                before={"original_publication_id": post.id, "post_url": post.post_url},
                after={"new_publication_ids": [item[0] for item in queued]},
            )
        )
        session.commit()
    except PublicationStateError as error:
        raise HTTPException(409, str(error)) from error
    except PublicationNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except CredentialStoreError as error:
        raise HTTPException(502, safe_provider_error(str(error))) from error
    tasks.add_task(run_publication_batch, queued)
    return project_or_404(session, project_id)


@router.get("/clips/{clip_id}/publishing-copy")
def publishing_copy(clip_id: str, session: Session = Depends(get_session)) -> object:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    packages: list[dict[str, object]] = []
    for platform in ("youtube", "instagram", "facebook", "tiktok", "x"):
        title, caption = clip_copy(session, clip, platform)
        packages.append(
            {
                "platform": platform,
                "title": title,
                "caption": caption,
                "hashtags": [],
                "cover_text": title,
            }
        )
    return {
        "packages": packages,
        "hashtag_notice": None
        if any("#" in str(item["caption"]) for item in packages)
        else (
            "No relevant hashtags are available. "
            "Refresh publishing details to generate source-based tags."
        ),
    }
