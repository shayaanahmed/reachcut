import shutil

from fastapi import APIRouter, HTTPException, status

from clipper.api.schemas import SetupStatusResponse
from clipper.config import settings
from clipper.services.setup import (
    OllamaSetupError,
    OllamaSetupService,
    OllamaUnavailableError,
)

router = APIRouter(prefix="/setup", tags=["setup"])

OLLAMA_INSTALL_URL = "https://ollama.com/download"

setup_service = OllamaSetupService(
    settings.editorial_base_url,
    settings.editorial_model,
    download_timeout_seconds=settings.editorial_model_download_timeout_seconds,
)


def _response() -> SetupStatusResponse:
    ollama = setup_service.status()
    ffmpeg = shutil.which("ffmpeg") is not None
    ffprobe = shutil.which("ffprobe") is not None
    return SetupStatusResponse(
        ready=ffmpeg and ffprobe and ollama.available and ollama.model_installed,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        ollama_available=ollama.available,
        ollama_version=ollama.version,
        ollama_install_url=OLLAMA_INSTALL_URL,
        editorial_model=settings.editorial_model,
        editorial_model_installed=ollama.model_installed,
        editorial_model_size_bytes=ollama.model_size_bytes,
        whisper_model=settings.whisper_model,
        whisper_download_on_first_use=True,
    )


@router.get("/status", response_model=SetupStatusResponse)
def setup_status() -> SetupStatusResponse:
    return _response()


@router.post("/editorial-model", response_model=SetupStatusResponse)
def download_editorial_model() -> SetupStatusResponse:
    try:
        setup_service.pull_model()
    except OllamaUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    except OllamaSetupError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return _response()
