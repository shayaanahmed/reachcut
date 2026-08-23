from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.editorial import EditorialLLMProvider
from clipper.media import probe_media
from clipper.persistence import Clip, Project, ProjectStatus
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService
from clipper.projects.stages import StageRunner
from clipper.rendering import RenderRequest, VideoRenderer
from clipper.transcription import ProgressReporter, TranscriptionProvider


class Pipeline:
    """Orchestrate project stages through domain ports and application services."""

    STAGES = ("probe", "transcribe", "select_candidates", "render_previews")

    def __init__(
        self,
        settings: Settings,
        transcription: TranscriptionProvider,
        editorial: EditorialLLMProvider,
    ) -> None:
        self.settings = settings
        self.transcription = transcription
        self.editorial = editorial
        self.stage_runner = StageRunner()
        self.artifacts = ClipArtifactService(
            ArtifactProvenance(transcription.identity, editorial.identity)
        )
        self.renderer = VideoRenderer()

    def run(self, session: Session, project_id: str, target_count: int = 5) -> None:
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
            plans_payload = self.stage_runner.run(
                session,
                project,
                "select_candidates",
                self._key(
                    project.media_sha256,
                    self.transcription.identity,
                    self.editorial.identity,
                    str(target_count),
                ),
                lambda progress: [
                    plan.model_dump(mode="json")
                    for plan in self.editorial.select_candidates(
                        transcript,
                        target_count,
                        lambda: self._cancelled(session, project.id),
                        progress,
                    )
                ],
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

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    @staticmethod
    def _cancelled(session: Session, project_id: str) -> bool:
        session.expire_all()
        project = session.get(Project, project_id)
        return project is None or project.status == "cancel_requested"
