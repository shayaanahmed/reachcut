from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clipper.api.dependencies import credential_store, metrics_adapters, publishing_adapters
from clipper.api.projects import project_or_404
from clipper.api.schemas import (
    AutomaticPublicationRequest,
    MetricCreateRequest,
    ProjectResponse,
    PublicationCreateRequest,
)
from clipper.persistence import SocialAccount, get_session
from clipper.projects import (
    AutomaticPublicationCreate,
    MetricCreate,
    PublicationCreate,
    PublicationNotFoundError,
    PublicationService,
    PublicationStateError,
)
from clipper.providers.credentials import CredentialStoreError
from clipper.providers.publishing_http import ProviderApiError
from clipper.providers.youtube import YouTubeApiError, YouTubeConfigurationError

router = APIRouter()
publication_service = PublicationService()


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
    return project_or_404(session, project_id)
