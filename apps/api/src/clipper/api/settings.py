from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from clipper.api.dependencies import runtime_settings_service
from clipper.api.schemas import (
    OllamaModelsResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from clipper.persistence import get_session
from clipper.projects import RuntimeSettingsError

router = APIRouter()


@router.get("/settings", response_model=RuntimeSettingsResponse)
def runtime_settings(session: Session = Depends(get_session)) -> RuntimeSettingsResponse:
    return RuntimeSettingsResponse.model_validate(runtime_settings_service.get(session).__dict__)


@router.put("/settings", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    request: RuntimeSettingsUpdateRequest,
    session: Session = Depends(get_session),
) -> RuntimeSettingsResponse:
    try:
        updated = runtime_settings_service.update(session, **request.model_dump())
    except RuntimeSettingsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RuntimeSettingsResponse.model_validate(updated.__dict__)


@router.get("/settings/ollama/models", response_model=OllamaModelsResponse)
def ollama_models(
    base_url: str = Query(min_length=8, max_length=2_048),
) -> OllamaModelsResponse:
    try:
        return OllamaModelsResponse(models=runtime_settings_service.ollama_models(base_url))
    except RuntimeSettingsError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
