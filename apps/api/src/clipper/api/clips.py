from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from clipper.api.dependencies import clip_service
from clipper.api.projects import project_or_404
from clipper.api.schemas import ApprovalRequest, ClipStyleRequest, ProjectResponse
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
            session, clip_id, ClipStyleUpdate(request.caption_config, request.frame_style)
        )
    except ClipNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ClipStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except MediaError as error:
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
