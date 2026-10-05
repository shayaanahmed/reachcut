from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from clipper.api.dependencies import publishing_connections
from clipper.api.schemas import (
    ApiConnectionRequest,
    PublishingCapabilitiesResponse,
    SocialAccountCreateRequest,
    SocialAccountResponse,
    SocialAccountUpdateRequest,
)
from clipper.config import settings
from clipper.persistence import SocialAccount, get_session
from clipper.projects import (
    PublishingConnectionError,
    SocialAccountCreate,
    SocialAccountNotFoundError,
    SocialAccountService,
    SocialAccountUpdate,
)
from clipper.providers.credentials import CredentialStoreError
from clipper.publishing import (
    OAuthConfigurationError,
    OAuthConnection,
    OAuthProviderError,
)

router = APIRouter()
account_service = SocialAccountService()


@router.get("/publishing/capabilities", response_model=PublishingCapabilitiesResponse)
def publishing_capabilities() -> PublishingCapabilitiesResponse:
    return PublishingCapabilitiesResponse(
        youtube_configured=publishing_connections.youtube_configured,
        automatic_platforms=["youtube", "tiktok", "instagram", "facebook", "x"],
        configured_platforms=publishing_connections.configured_platforms,
    )


@router.get("/social-accounts/{account_id}/connect")
def connect_social_account(
    account_id: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        url = publishing_connections.authorization_url(session, account_id)
    except PublishingConnectionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return RedirectResponse(url)


@router.get("/social-accounts/{account_id}/connect/youtube")
def connect_youtube_compatibility(
    account_id: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    return connect_social_account(account_id, session)


@router.get("/oauth/{platform}/callback")
def oauth_callback(
    platform: str,
    code: str,
    state: str,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        account = publishing_connections.complete_authorization(session, platform, state, code)
    except PublishingConnectionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (CredentialStoreError, OAuthProviderError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    query = urlencode({"connected": account.platform})
    return RedirectResponse(f"{settings.web_base_url.rstrip('/')}/settings/accounts?{query}")


@router.delete(
    "/social-accounts/{account_id}/connection",
    response_model=SocialAccountResponse,
)
def disconnect_social_account(
    account_id: str,
    session: Session = Depends(get_session),
) -> SocialAccount:
    try:
        return publishing_connections.disconnect(session, account_id)
    except PublishingConnectionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/social-accounts/{account_id}/connection",
    response_model=SocialAccountResponse,
)
def save_social_account_connection(
    account_id: str,
    request: ApiConnectionRequest,
    session: Session = Depends(get_session),
) -> SocialAccount:
    try:
        return publishing_connections.save_api_connection(
            session,
            account_id,
            OAuthConnection(**request.model_dump()),
        )
    except PublishingConnectionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/social-accounts", response_model=list[SocialAccountResponse])
def social_accounts(session: Session = Depends(get_session)) -> list[SocialAccount]:
    return account_service.list(session)


@router.post(
    "/social-accounts",
    response_model=SocialAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_social_account(
    request: SocialAccountCreateRequest,
    session: Session = Depends(get_session),
) -> SocialAccount:
    return account_service.create(session, SocialAccountCreate(**request.model_dump()))


@router.put("/social-accounts/{account_id}", response_model=SocialAccountResponse)
def update_social_account(
    account_id: str,
    request: SocialAccountUpdateRequest,
    session: Session = Depends(get_session),
) -> SocialAccount:
    try:
        return account_service.update(
            session,
            account_id,
            SocialAccountUpdate(**request.model_dump()),
        )
    except SocialAccountNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/social-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_social_account(
    account_id: str,
    session: Session = Depends(get_session),
) -> Response:
    try:
        account = session.get(SocialAccount, account_id)
        if account and account.connection_status == "connected":
            publishing_connections.disconnect(session, account_id)
        account_service.archive(session, account_id)
    except SocialAccountNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
