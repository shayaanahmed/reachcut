from typing import cast
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from clipper.api.dependencies import publishing_connections
from clipper.api.schemas import (
    AccountConnectionReadinessResponse,
    OAuthAccountSelectionRequest,
    OAuthAccountSelectionResponse,
    ProviderSetupResponse,
    PublishingCapabilitiesResponse,
    SocialAccountResponse,
    SocialAccountUpdateRequest,
)
from clipper.config import settings
from clipper.persistence import SocialAccount, get_session
from clipper.projects import (
    PublishingConnectionError,
    SocialAccountNotFoundError,
    SocialAccountService,
    SocialAccountUpdate,
)
from clipper.projects.publishing_connections import AccountSelectionRequired
from clipper.providers.credentials import CredentialStoreError
from clipper.publishing import (
    OAuthConfigurationError,
    OAuthProviderError,
    PublishingPlatform,
)

router = APIRouter()
account_service = SocialAccountService()


@router.get("/publishing/capabilities", response_model=PublishingCapabilitiesResponse)
def publishing_capabilities() -> PublishingCapabilitiesResponse:
    configured = publishing_connections.configured_platforms
    return PublishingCapabilitiesResponse(
        configured_platforms=configured,
        provider_setup=[
            ProviderSetupResponse(
                platform=cast(PublishingPlatform, platform),
                configured=platform in configured,
                redirect_uri=redirect_uri,
                credential_fields=fields,
                developer_portal_url=portal,
            )
            for platform, redirect_uri, fields, portal in [
                (
                    "youtube",
                    settings.youtube_redirect_uri,
                    [
                        "CLIPPER_YOUTUBE_CLIENT_ID",
                        "CLIPPER_YOUTUBE_CLIENT_SECRET",
                        "CLIPPER_YOUTUBE_REDIRECT_URI",
                    ],
                    "https://console.cloud.google.com/apis/credentials",
                ),
                (
                    "tiktok",
                    settings.tiktok_redirect_uri,
                    [
                        "CLIPPER_TIKTOK_CLIENT_KEY",
                        "CLIPPER_TIKTOK_CLIENT_SECRET",
                        "CLIPPER_TIKTOK_REDIRECT_URI",
                    ],
                    "https://developers.tiktok.com/apps/",
                ),
                (
                    "instagram",
                    settings.instagram_redirect_uri,
                    [
                        "CLIPPER_INSTAGRAM_APP_ID",
                        "CLIPPER_INSTAGRAM_APP_SECRET",
                        "CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID",
                        "CLIPPER_INSTAGRAM_REDIRECT_URI",
                    ],
                    "https://developers.facebook.com/apps/",
                ),
                (
                    "facebook",
                    settings.facebook_redirect_uri,
                    [
                        "CLIPPER_FACEBOOK_APP_ID",
                        "CLIPPER_FACEBOOK_APP_SECRET",
                        "CLIPPER_FACEBOOK_LOGIN_CONFIG_ID",
                        "CLIPPER_FACEBOOK_REDIRECT_URI",
                    ],
                    "https://developers.facebook.com/apps/",
                ),
                (
                    "x",
                    settings.x_redirect_uri,
                    [
                        "CLIPPER_X_CLIENT_ID",
                        "CLIPPER_X_CLIENT_SECRET",
                        "CLIPPER_X_REDIRECT_URI",
                    ],
                    "https://developer.x.com/en/portal/dashboard",
                ),
            ]
        ],
    )


@router.get(
    "/social-accounts/readiness",
    response_model=list[AccountConnectionReadinessResponse],
)
def social_account_readiness(
    session: Session = Depends(get_session),
) -> list[AccountConnectionReadinessResponse]:
    return [
        AccountConnectionReadinessResponse.model_validate(
            publishing_connections.connection_readiness(session, account.id)
        )
        for account in account_service.list(session)
    ]


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


@router.get("/social-accounts/connect/{platform}")
def connect_social_platform(platform: PublishingPlatform) -> RedirectResponse:
    try:
        url = publishing_connections.authorization_url_for_platform(platform)
    except PublishingConnectionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return RedirectResponse(url)


@router.get("/oauth/{platform}/callback")
def oauth_callback(
    platform: str,
    state: str,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if error or not code:
        message = error_description or error or "Authorization was cancelled"
        return _account_settings_redirect(connection_error=message)
    try:
        account = publishing_connections.complete_authorization(session, platform, state, code)
    except AccountSelectionRequired as selection:
        return _account_settings_redirect(connection_selection=selection.selection_token)
    except PublishingConnectionError as error:
        return _account_settings_redirect(connection_error=str(error))
    except OAuthConfigurationError as error:
        return _account_settings_redirect(connection_error=str(error))
    except (CredentialStoreError, OAuthProviderError) as error:
        return _account_settings_redirect(connection_error=str(error))
    return _account_settings_redirect(connected=account.platform)


@router.get("/social-account-selections/{token}", response_model=OAuthAccountSelectionResponse)
def pending_account_selection(token: str, session: Session = Depends(get_session)) -> object:
    try:
        return publishing_connections.pending_selection(session, token)
    except (PublishingConnectionError, CredentialStoreError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/social-account-selections/{token}", response_model=SocialAccountResponse)
def select_oauth_account(
    token: str,
    request: OAuthAccountSelectionRequest,
    session: Session = Depends(get_session),
) -> SocialAccount:
    try:
        return publishing_connections.select_account(session, token, request.external_account_id)
    except (PublishingConnectionError, CredentialStoreError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _account_settings_redirect(**parameters: str) -> RedirectResponse:
    query = urlencode(parameters)
    return RedirectResponse(
        f"{settings.web_base_url.rstrip('/')}/settings/accounts?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Cache-Control": "no-store"},
    )


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


@router.get("/social-accounts", response_model=list[SocialAccountResponse])
def social_accounts(session: Session = Depends(get_session)) -> list[SocialAccount]:
    return account_service.list(session)


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
