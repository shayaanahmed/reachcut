from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.db import Clip, Project, ProjectStatus, StageRun, StageStatus
from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript, Word
from clipper.providers.base import EditorialLLMProvider, ProgressReporter, TranscriptionProvider
from clipper.services.captions import phrase_cues, serialize_srt, serialize_vtt
from clipper.services.media import probe_media
from clipper.services.render import render_vertical

StageResult = TypeVar("StageResult")


class Pipeline:
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

    def run(self, session: Session, project_id: str, target_count: int = 5) -> None:
        project = session.get(Project, project_id)
        if not project:
            raise LookupError("project not found")
        project.status = ProjectStatus.PROCESSING
        session.commit()
        try:
            media_info = self._stage(
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
            transcript_payload = self._stage(
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
            plans_payload = self._stage(
                session,
                project,
                "select_candidates",
                self._key(project.media_sha256, self.editorial.identity, str(target_count)),
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
                self._write_clip_artifacts(project, clip, plan, transcript)
            session.commit()
            clips = list(session.scalars(select(Clip).where(Clip.project_id == project.id)))
            self._stage(
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

    def _stage(
        self,
        session: Session,
        project: Project,
        name: str,
        cache_key: str,
        operation: Callable[[ProgressReporter], StageResult],
    ) -> StageResult:
        stage = session.scalar(
            select(StageRun).where(StageRun.project_id == project.id, StageRun.name == name)
        )
        if stage and stage.status == StageStatus.SUCCEEDED and stage.cache_key == cache_key:
            artifact = self._stage_artifact(project, name)
            if artifact.exists():
                return json.loads(artifact.read_text())  # type: ignore[no-any-return]
        if not stage:
            stage = StageRun(project_id=project.id, name=name, attempts=0, progress=0)
            session.add(stage)
        stage.status = StageStatus.RUNNING
        stage.progress = 0
        stage.attempts += 1
        stage.cache_key = cache_key
        stage.error = None
        stage.started_at = datetime.now(UTC)
        session.commit()
        last_progress = 0.0

        def report_progress(value: float) -> None:
            nonlocal last_progress
            clamped = min(max(value, last_progress, 0.0), 0.99)
            if clamped - last_progress < 0.01 and clamped < 0.99:
                return
            last_progress = clamped
            stage.progress = clamped
            session.commit()

        try:
            result = operation(report_progress)
            artifact = self._stage_artifact(project, name)
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(json.dumps(result, indent=2) + "\n")
            stage.status = StageStatus.SUCCEEDED
            stage.progress = 1
            stage.finished_at = datetime.now(UTC)
            session.commit()
            return result
        except InterruptedError as error:
            stage.status = StageStatus.CANCELLED
            stage.error = {"category": "cancelled", "message": str(error)}
            stage.finished_at = datetime.now(UTC)
            session.commit()
            raise
        except Exception as error:
            stage.status = StageStatus.FAILED
            stage.error = {"category": type(error).__name__, "message": str(error)[:1000]}
            stage.finished_at = datetime.now(UTC)
            session.commit()
            raise

    def _write_clip_artifacts(
        self, project: Project, clip: Clip, plan: EditingPlanV1, transcript: Transcript
    ) -> None:
        root = Path(project.source_path).parent / "clips" / clip.id
        root.mkdir(parents=True, exist_ok=True)
        (root / "editing-plan.json").write_text(plan.model_dump_json(indent=2) + "\n")
        words = self._relative_words(transcript, plan.source.start_seconds, plan.source.end_seconds)
        cues = phrase_cues(words)
        (root / "captions.srt").write_text(serialize_srt(cues))
        (root / "captions.vtt").write_text(serialize_vtt(cues))
        provenance = {
            "transcription": self.transcription.identity,
            "editorial": self.editorial.identity,
            "media_sha256": project.media_sha256,
            "assets": [],
        }
        (root / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    @staticmethod
    def _render_previews(
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
            render_vertical(
                Path(project.source_path),
                EditingPlanV1.model_validate(clip.plan),
                root / "captions.srt",
                output,
                preview=True,
            )
            clip.preview_path = str(output)
            outputs.append(str(output.relative_to(project_root)))
            session.commit()
            progress((index + 1) / len(clips))
        return outputs

    @staticmethod
    def _relative_words(transcript: Transcript, start: float, end: float) -> list[Word]:
        words: list[Word] = []
        for segment in transcript.segments:
            for word in segment.words:
                if word.end_seconds > start and word.start_seconds < end:
                    words.append(
                        word.model_copy(
                            update={
                                "start_seconds": max(0, word.start_seconds - start),
                                "end_seconds": min(end - start, word.end_seconds - start),
                            }
                        )
                    )
        return words

    @staticmethod
    def _stage_artifact(project: Project, name: str) -> Path:
        return Path(project.source_path).parent / "stages" / f"{name}.json"

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    @staticmethod
    def _cancelled(session: Session, project_id: str) -> bool:
        session.expire_all()
        project = session.get(Project, project_id)
        return project is None or project.status == "cancel_requested"
