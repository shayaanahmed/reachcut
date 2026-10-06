from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from clipper.api.dependencies import clip_service
from clipper.api.projects import project_or_404
from clipper.api.schemas import (
    ApprovalRequest,
    CaptionTranslationRequest,
    ClipStyleRequest,
    ProjectResponse,
)
from clipper.domain.editing_plan import SecondaryMediaKind
from clipper.media import MediaError
from clipper.persistence import Clip, get_session
from clipper.projects.clips import ClipNotFoundError, ClipStateError, ClipStyleUpdate

router = APIRouter()


@router.put("/clips/{clip_id}/approval", response_model=ProjectResponse)
def approve_clip(
    clip_id: str, request: ApprovalRequest, session: Session = Depends(get_session)
) -> object:
    try:
        project_id = clip_service.set_approval(session, clip_id, request.approved)
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.put("/clips/{clip_id}/style", response_model=ProjectResponse)
def update_clip_style(
    clip_id: str, request: ClipStyleRequest, session: Session = Depends(get_session)
) -> object:
    try:
        project_id = clip_service.update_style(
            session,
            clip_id,
            ClipStyleUpdate(
                caption_config=request.caption_config,
                frame_style=request.frame_style,
                crop_focus_x=request.crop_focus_x,
                crop_focus_y=request.crop_focus_y,
                source_slices=tuple(request.source_slices) if request.source_slices else None,
                hook_text=request.hook_text,
                hook_render=request.hook_render,
                content_mode=request.content_mode,
                enhancement_level=request.enhancement_level,
                tracking_enabled=request.tracking_enabled,
                tracking_strategy=request.tracking_strategy,
                transition_style=request.transition_style,
                transition_duration_seconds=request.transition_duration_seconds,
                cta_text=request.cta_text,
                cta_render=request.cta_render,
                cta_style=request.cta_style,
                effects=tuple(request.effects) if request.effects is not None else None,
                audio_track_index=request.audio_track_index,
            ),
        )
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ClipStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (MediaError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/clips/{clip_id}/translate", response_model=ProjectResponse)
def translate_clip_captions(
    clip_id: str,
    request: CaptionTranslationRequest,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = clip_service.translate_captions(
            session,
            clip_id,
            request.target_language.lower(),
            request.mode,
        )
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ClipStateError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/clips/{clip_id}/tracking", response_model=ProjectResponse)
def analyze_clip_tracking(
    clip_id: str,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = clip_service.analyze_tracking(session, clip_id)
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ClipStateError, MediaError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.post("/clips/{clip_id}/secondary-media", response_model=ProjectResponse)
def add_clip_secondary_media(
    clip_id: str,
    kind: SecondaryMediaKind = Form(),
    authorization_confirmed: bool = Form(),
    placement: Literal["bottom", "pip", "fullscreen", "audio"] = Form(default="bottom"),
    start_seconds: float | None = Form(default=None, ge=0),
    end_seconds: float | None = Form(default=None, ge=0),
    media: UploadFile = File(),
    session: Session = Depends(get_session),
) -> object:
    if not authorization_confirmed:
        raise HTTPException(status_code=422, detail="media authorization confirmation is required")
    try:
        project_id = clip_service.add_secondary_media(
            session,
            clip_id,
            media.file,
            media.filename or "secondary.mp4",
            kind,
            start_seconds,
            end_seconds,
            placement,
        )
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ClipStateError, MediaError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.delete("/clips/{clip_id}/secondary-media/{asset_id}", response_model=ProjectResponse)
def remove_clip_secondary_media(
    clip_id: str,
    asset_id: str,
    session: Session = Depends(get_session),
) -> object:
    try:
        project_id = clip_service.remove_secondary_media(session, clip_id, asset_id)
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ClipStateError, MediaError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return project_or_404(session, project_id)


@router.get("/clips/{clip_id}/preview", response_class=FileResponse)
def clip_preview(clip_id: str, session: Session = Depends(get_session)) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if not clip or not clip.preview_path or not Path(clip.preview_path).is_file():
        raise HTTPException(status_code=404, detail="preview not found")
    return FileResponse(
        clip.preview_path, media_type="video/mp4", filename=f"{clip.id}-preview.mp4"
    )


@router.post("/clips/{clip_id}/render", status_code=status.HTTP_201_CREATED)
def render_clip(clip_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        clip_service.render_final(session, clip_id)
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ClipStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "rendered",
        "clip_id": clip_id,
        "download_url": f"/api/clips/{clip_id}/final",
    }


@router.get("/clips/{clip_id}/final", response_class=FileResponse)
def clip_final(clip_id: str, session: Session = Depends(get_session)) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if not clip or not clip.final_path or not Path(clip.final_path).is_file():
        raise HTTPException(status_code=404, detail="final render not found")
    return FileResponse(clip.final_path, media_type="video/mp4", filename=f"{clip.id}.mp4")
