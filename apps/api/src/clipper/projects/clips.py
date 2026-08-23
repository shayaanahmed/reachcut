from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from clipper.domain.editing_plan import CaptionConfig, EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.persistence import Clip, Project
from clipper.projects.artifacts import ClipArtifactService
from clipper.rendering import RenderRequest, VideoRenderer


class ClipNotFoundError(LookupError):
    pass


class ClipStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClipStyleUpdate:
    caption_config: CaptionConfig
    frame_style: Literal["blurred_background", "center_crop"]


class ClipService:
    """Manage clip approval, style artifacts, previews, and final renders."""

    def __init__(self, artifacts: ClipArtifactService, renderer: VideoRenderer) -> None:
        self._artifacts = artifacts
        self._renderer = renderer

    def set_approval(self, session: Session, clip_id: str, approved: bool) -> str:
        clip = self._clip(session, clip_id)
        clip.approval_status = "approved" if approved else "rejected"
        session.commit()
        return clip.project_id

    def update_style(self, session: Session, clip_id: str, update: ClipStyleUpdate) -> str:
        clip = self._clip(session, clip_id)
        project = session.get(Project, clip.project_id)
        if not project or not project.transcript:
            raise ClipStateError("project transcript is not available")
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        plan = previous_plan.model_copy(
            update={
                "caption_config": update.caption_config,
                "frame_style": update.frame_style,
                "caption_style": (
                    "karaoke"
                    if update.caption_config.animation == "karaoke"
                    else "kinetic_highlight"
                ),
            }
        )
        transcript = Transcript.model_validate(project.transcript)
        root = self._artifacts.write(project, clip, plan, transcript)
        pending_preview = root / "preview.pending.mp4"
        pending_manifest = pending_preview.with_suffix(".manifest.json")
        try:
            self._renderer.render(
                RenderRequest(
                    Path(project.source_path),
                    plan,
                    root / "captions.ass",
                    pending_preview,
                    preview=True,
                )
            )
        except Exception:
            pending_preview.unlink(missing_ok=True)
            pending_manifest.unlink(missing_ok=True)
            self._artifacts.write(project, clip, previous_plan, transcript)
            raise
        pending_preview.replace(root / "preview.mp4")
        pending_manifest.replace(root / "preview.manifest.json")
        clip.plan = plan.model_dump(mode="json")
        clip.preview_path = str(root / "preview.mp4")
        clip.final_path = None
        session.commit()
        return clip.project_id

    def render_final(self, session: Session, clip_id: str) -> Path:
        clip = self._clip(session, clip_id)
        if clip.approval_status != "approved":
            raise ClipStateError("clip must be explicitly approved before render")
        project = session.get(Project, clip.project_id)
        if not project:
            raise ClipNotFoundError("project not found")
        root = Path(project.source_path).parent / "clips" / clip.id
        output = root / "final.mp4"
        plan = EditingPlanV1.model_validate(clip.plan)
        if not (root / "captions.ass").exists() and project.transcript:
            self._artifacts.write(
                project, clip, plan, Transcript.model_validate(project.transcript)
            )
        subtitles = root / "captions.ass"
        if not subtitles.exists():
            subtitles = root / "captions.srt"
        self._renderer.render(
            RenderRequest(Path(project.source_path), plan, subtitles, output, preview=False)
        )
        clip.final_path = str(output)
        session.commit()
        return output

    @staticmethod
    def _clip(session: Session, clip_id: str) -> Clip:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ClipNotFoundError("clip not found")
        return clip
