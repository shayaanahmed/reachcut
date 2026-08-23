import shutil

from fastapi import APIRouter

from clipper.api.dependencies import editorial_provider, transcription_provider
from clipper.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ffmpeg=shutil.which("ffmpeg") is not None,
        ffprobe=shutil.which("ffprobe") is not None,
        editorial_provider=editorial_provider.identity,
        transcription_provider=transcription_provider.identity,
    )
