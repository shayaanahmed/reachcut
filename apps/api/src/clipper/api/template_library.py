import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from clipper.api.dependencies import runtime_settings_service
from clipper.config import settings
from clipper.generation.reference_templates import ReferenceTemplate, TemplateMatch
from clipper.media import MediaError
from clipper.persistence import get_session
from clipper.projects.template_library import MAX_TEMPLATE_BYTES, TemplateLibrary
from clipper.providers.ollama_story import OllamaStoryDirector
from clipper.providers.ollama_templates import OllamaTemplateClassifier, match_template

router = APIRouter(prefix="/template-library")
library = TemplateLibrary(settings.data_dir / "reference-templates")


class TemplateImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    name: str = Field(default="Imported clip", min_length=1, max_length=100)


class TemplateMatchRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=8000)


@router.get("", response_model=list[ReferenceTemplate])
def list_templates() -> list[ReferenceTemplate]:
    return library.list()


@router.post("/import", response_model=ReferenceTemplate)
def import_template(request: TemplateImportRequest) -> ReferenceTemplate:
    try:
        return library.import_source(request.url, request.name)
    except MediaError as error:
        raise HTTPException(422, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(502, detail="Could not download the reference clip") from error


@router.post("/upload", response_model=ReferenceTemplate)
def upload_template(
    video: UploadFile = File(...),
    name: str = Form("My reference clip", min_length=1, max_length=100),
) -> ReferenceTemplate:
    try:
        return library.upload(video.file.read(MAX_TEMPLATE_BYTES + 1), name)
    except MediaError as error:
        raise HTTPException(422, detail=str(error)) from error


@router.post("/match", response_model=TemplateMatch)
def select_template(
    request: TemplateMatchRequest, session: Session = Depends(get_session)
) -> TemplateMatch:
    runtime = runtime_settings_service.get(session)
    try:
        return match_template(
            OllamaStoryDirector(runtime.ollama_base_url, runtime.model_for("scripting")),
            request.prompt,
            library.list(),
        )
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(503, detail="Ollama could not choose a template; try again") from error


@router.post("/{template_id}/classify", response_model=ReferenceTemplate)
def classify_template(
    template_id: str, session: Session = Depends(get_session)
) -> ReferenceTemplate:
    runtime = runtime_settings_service.get(session)
    try:
        return library.classify(
            template_id,
            OllamaTemplateClassifier(runtime.ollama_base_url, runtime.model_for("visual_review")),
        )
    except MediaError as error:
        raise HTTPException(404, detail=str(error)) from error


@router.get("/{template_id}/file", response_class=FileResponse)
def template_file(template_id: str) -> FileResponse:
    try:
        return FileResponse(library.video_path(template_id), media_type="video/mp4")
    except MediaError as error:
        raise HTTPException(404, detail=str(error)) from error


@router.get("/{template_id}/poster", response_class=FileResponse)
def template_poster(template_id: str) -> FileResponse:
    try:
        return FileResponse(library.poster_path(template_id), media_type="image/jpeg")
    except MediaError as error:
        raise HTTPException(404, detail=str(error)) from error
