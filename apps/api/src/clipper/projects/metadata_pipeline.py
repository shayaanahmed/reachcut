import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.editorial.publishing_metadata import PublishingMetadataProvider
from clipper.media import probe_media
from clipper.media.publishing import prepare_full_video
from clipper.persistence import Clip, Project
from clipper.projects.pipeline import Pipeline
from clipper.projects.stages import StageRunner
from clipper.transcription import ProgressReporter, TranscriptionProvider


class MetadataPipeline:
    """Refresh publishing copy while retaining every edit and rendered video."""

    def __init__(
        self,
        settings: Settings,
        transcription: TranscriptionProvider,
        metadata: PublishingMetadataProvider,
        source_evidence: Callable[[Session, Clip], str] | None = None,
    ) -> None:
        self.settings = settings
        self.transcription = transcription
        self.source_evidence = source_evidence
        self.metadata = metadata
        self.stages = StageRunner()

    def run(
        self,
        session: Session,
        project: Project,
        *,
        final_status: str = "complete",
        clip_ids: list[str] | None = None,
    ) -> None:
        started = session.execute(
            update(Project)
            .where(
                Project.id == project.id, Project.status.not_in(["cancel_requested", "cancelled"])
            )
            .values(status="processing")
        )
        if started.rowcount != 1:  # type: ignore[attr-defined]
            session.rollback()
            raise InterruptedError("Project stopped")
        session.commit()
        source = Path(project.source_path)
        info = self.stages.run(
            session,
            project,
            "probe",
            Pipeline._key(project.media_sha256, "inspection-v2"),
            lambda progress: probe_media(source, self.settings.max_duration_seconds),
        )
        project.media_info = info
        project.duration_seconds = float(str(info["duration_seconds"]))
        session.commit()
        transcript_payload = self.stages.run(
            session,
            project,
            "transcribe",
            Pipeline._key(project.media_sha256, self.transcription.identity),
            lambda progress: self.transcription.transcribe(
                source,
                lambda: Pipeline._cancelled(session, project.id),
                progress,
            ).model_dump(mode="json")
            if info.get("has_audio", True)
            else Transcript(
                language="und",
                segments=[],
                provider="none",
                model="silent-source",
            ).model_dump(mode="json"),
        )
        project.transcript = transcript_payload
        session.commit()
        transcript = Transcript.model_validate(transcript_payload)
        # Each queued request can refresh publishing copy independently of transcription.
        request_key = project.job.enqueued_at.isoformat() if project.job else "manual"

        def generate(progress: ProgressReporter) -> list[dict[str, object]]:
            clips = [clip for clip in project.clips if clip_ids is None or clip.id in clip_ids]
            if clip_ids is not None and len(clips) != len(set(clip_ids)):
                raise ValueError(
                    "Selected clips are no longer available; choose existing clips again"
                )
            if not clips:
                plan = EditingPlanV1.model_validate(
                    {
                        "source": {"start_seconds": 0, "end_seconds": project.duration_seconds},
                        "scores": dict.fromkeys(
                            ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                        ),
                        "rationale": "Full video prepared for publishing without clipping.",
                        "caption_config": {"enabled": False},
                    }
                )
                clip_id = str(uuid4())
                final = source.parent / "clips" / clip_id / "final.mp4"
                prepare_full_video(source, final)
                clip = Clip(
                    id=clip_id,
                    project=project,
                    plan=plan.model_dump(mode="json"),
                    approval_status="approved",
                    final_path=str(final),
                )
                session.add(clip)
                session.commit()
                clips = [clip]
            results: list[dict[str, object]] = []
            for index, clip in enumerate(clips):
                if Pipeline._cancelled(session, project.id):
                    raise InterruptedError("Project stopped")
                plan = EditingPlanV1.model_validate(clip.plan)
                ranges = plan.source_slices or [plan.source]
                text = " ".join(
                    segment.text
                    for segment in transcript.segments
                    if any(
                        segment.end_seconds > span.start_seconds
                        and segment.start_seconds < span.end_seconds
                        for span in ranges
                    )
                )
                if not text.strip() and self.source_evidence:
                    if project.job:
                        project.job.phase = "Inspecting source frames · no speech detected"
                        session.commit()
                    text = "Observed video frames (not spoken transcript): " + self.source_evidence(
                        session, clip
                    )
                copy = self.metadata.generate(project.original_filename, text)
                results.append({"clip_id": clip.id, **copy.model_dump(mode="json")})
                progress((index + 1) / len(clips))
            return results

        results = self.stages.run(
            session,
            project,
            "generate_metadata",
            Pipeline._key(
                project.media_sha256,
                self.metadata.identity,
                request_key,
                json.dumps(transcript_payload, sort_keys=True),
            ),
            generate,
        )
        by_id = {clip.id: clip for clip in project.clips}
        for result in results:
            clip = by_id[str(result["clip_id"])]
            payload = {
                **clip.plan,
                **{key: value for key, value in result.items() if key != "clip_id"},
            }
            plan = EditingPlanV1.model_validate(payload)
            clip.plan = plan.model_dump(mode="json")
            root = source.parent / "clips" / clip.id
            root.mkdir(parents=True, exist_ok=True)
            (root / "editing-plan.json").write_text(plan.model_dump_json(indent=2) + "\n")
        if len(project.clips) == 1:
            plan = EditingPlanV1.model_validate(project.clips[0].plan)
            if (
                plan.source.start_seconds == 0
                and plan.source.end_seconds == project.duration_seconds
            ):
                project.title = plan.suggested_title or project.title
        project.status = final_status
        session.commit()
