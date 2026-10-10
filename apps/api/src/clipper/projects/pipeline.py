from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.domain.editing_plan import ClipType, EditingPlanV1, TrackingConfig
from clipper.domain.transcript import Transcript
from clipper.editorial import (
    EditorialContext,
    EditorialLLMProvider,
    ModeSignals,
    infer_content_mode,
)
from clipper.media import probe_media
from clipper.persistence import Clip, Project, ProjectStatus
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService
from clipper.projects.stages import StageRunner
from clipper.rendering import (
    RenderRequest,
    VideoRenderer,
    VisualAnalysis,
    VisualTrackingProvider,
    keyframes_for_clip,
    strategy_for_mode,
)
from clipper.transcription import ProgressReporter, TranscriptionProvider


class Pipeline:
    """Orchestrate project stages through domain ports and application services."""

    STAGES = (
        "probe",
        "analyze_visuals",
        "transcribe",
        "select_candidates",
        "render_previews",
    )

    def __init__(
        self,
        settings: Settings,
        transcription: TranscriptionProvider,
        editorial: EditorialLLMProvider,
        tracking: VisualTrackingProvider | None = None,
    ) -> None:
        self.settings = settings
        self.transcription = transcription
        self.editorial = editorial
        self.tracking = tracking
        self.stage_runner = StageRunner()
        self.artifacts = ClipArtifactService(
            ArtifactProvenance(transcription.identity, editorial.identity)
        )
        self.renderer = VideoRenderer()

    def run(
        self,
        session: Session,
        project_id: str,
        target_count: int = 5,
        clip_types: tuple[ClipType, ...] = (),
    ) -> None:
        project = session.get(Project, project_id)
        if not project:
            raise LookupError("project not found")
        project.status = ProjectStatus.PROCESSING
        session.commit()
        try:
            media_info = self.stage_runner.run(
                session,
                project,
                "probe",
                project.media_sha256,
                lambda progress: probe_media(
                    Path(project.source_path), self.settings.max_duration_seconds
                ),
            )
            project.media_info = media_info
            project.duration_seconds = float(str(media_info["duration_seconds"]))
            session.commit()
            visual_payload: dict[str, object] = {}
            tracking = self.tracking
            if tracking:
                visual_payload = self.stage_runner.run(
                    session,
                    project,
                    "analyze_visuals",
                    self._key(project.media_sha256, tracking.identity),
                    lambda progress: tracking.analyze(
                        Path(project.source_path),
                        lambda: self._cancelled(session, project.id),
                        progress,
                    ).as_artifact(),
                )
            visual_analysis = VisualAnalysis.from_artifact(visual_payload)
            transcript_payload = self.stage_runner.run(
                session,
                project,
                "transcribe",
                self._key(project.media_sha256, self.transcription.identity),
                lambda progress: self.transcription.transcribe(
                    Path(project.source_path),
                    lambda: self._cancelled(session, project.id),
                    progress,
                ).model_dump(mode="json"),
            )
            project.transcript = transcript_payload
            session.commit()
            transcript = Transcript.model_validate(transcript_payload)
            motion_confidence = (
                sum(point.confidence for point in visual_analysis.action_points)
                / len(visual_analysis.action_points)
                if visual_analysis.action_points
                else 0
            )
            inferred_mode = infer_content_mode(
                project.title,
                project.original_filename,
                transcript,
                ModeSignals(visual_analysis.face_coverage, motion_confidence),
            )
            editorial_context = EditorialContext(
                project.title,
                project.original_filename,
                inferred_mode,
                visual_analysis.face_coverage,
                motion_confidence,
                clip_types,
            )
            plans_payload = self.stage_runner.run(
                session,
                project,
                "select_candidates",
                self._key(
                    project.media_sha256,
                    self.transcription.identity,
                    self.editorial.identity,
                    self.tracking.identity if self.tracking else "tracking:none",
                    inferred_mode,
                    str(target_count),
                    *(item.value for item in clip_types),
                ),
                lambda progress: self._select_and_track(
                    transcript,
                    target_count,
                    lambda: self._cancelled(session, project.id),
                    progress,
                    editorial_context,
                    visual_analysis,
                ),
            )
            session.query(Clip).filter(Clip.project_id == project.id).delete()
            for plan_payload in plans_payload:
                plan = EditingPlanV1.model_validate(plan_payload)
                clip = Clip(project_id=project.id, plan=plan.model_dump(mode="json"))
                session.add(clip)
                session.flush()
                self.artifacts.write(project, clip, plan, transcript)
            session.commit()
            clips = list(session.scalars(select(Clip).where(Clip.project_id == project.id)))
            self.stage_runner.run(
                session,
                project,
                "render_previews",
                self._key(*(clip.id for clip in clips), project.media_sha256),
                lambda progress: self._render_previews(session, project, clips, progress),
            )
            project.status = ProjectStatus.REVIEW
            session.commit()
        except InterruptedError:
            project.status = ProjectStatus.CREATED
            session.commit()
            raise
        except Exception:
            project.status = ProjectStatus.FAILED
            session.commit()
            raise

    def _render_previews(
        self,
        session: Session,
        project: Project,
        clips: list[Clip],
        progress: ProgressReporter,
    ) -> list[str]:
        outputs: list[str] = []
        project_root = Path(project.source_path).parent
        for index, clip in enumerate(clips):
            root = project_root / "clips" / clip.id
            output = root / "preview.mp4"
            self.renderer.render(
                RenderRequest(
                    Path(project.source_path),
                    EditingPlanV1.model_validate(clip.plan),
                    root / "captions.ass",
                    output,
                    preview=True,
                )
            )
            clip.preview_path = str(output)
            outputs.append(str(output.relative_to(project_root)))
            session.commit()
            progress((index + 1) / len(clips))
        return outputs

    def _select_and_track(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: Callable[[], bool],
        progress: ProgressReporter,
        context: EditorialContext,
        visual_analysis: VisualAnalysis,
    ) -> list[dict[str, object]]:
        plans = self.editorial.select_candidates(
            transcript,
            target_count,
            cancelled,
            progress,
            context,
        )
        payloads: list[dict[str, object]] = []
        for plan in plans:
            mode = context.content_mode if plan.content_mode.value == "auto" else plan.content_mode
            slices = plan.source_slices or [plan.source]
            keyframes = keyframes_for_clip(visual_analysis, mode, slices)
            payload = plan.model_dump(mode="json")
            payload.update(
                {
                    "content_mode": mode,
                    "tracking": TrackingConfig(
                        enabled=bool(keyframes),
                        strategy=strategy_for_mode(mode),
                        keyframes=keyframes,
                    ).model_dump(mode="json"),
                }
            )
            payloads.append(EditingPlanV1.model_validate(payload).model_dump(mode="json"))
        return payloads

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    @staticmethod
    def _cancelled(session: Session, project_id: str) -> bool:
        session.expire_all()
        project = session.get(Project, project_id)
        return project is None or project.status == "cancel_requested"
