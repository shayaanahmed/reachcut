import shutil

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clipper.api.dependencies import runtime_settings_service, transcription_provider
from clipper.api.schemas import HealthResponse
from clipper.persistence import get_session

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_session)) -> HealthResponse:
    runtime = runtime_settings_service.get(session)
    return HealthResponse(
        status="ok",
        ffmpeg=shutil.which("ffmpeg") is not None,
        ffprobe=shutil.which("ffprobe") is not None,
        editorial_provider=f"ollama:{runtime.editorial_model}",
        transcription_provider=transcription_provider.identity,
    )
