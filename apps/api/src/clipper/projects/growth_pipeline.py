"""Run growth optimization as a visible, retryable project stage."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1
from clipper.persistence import Clip, Project, now_utc
from clipper.persistence.models import GrowthPreparation
from clipper.projects.growth_automation import GrowthInference, prepare_clip, request_preparation
from clipper.projects.pipeline import Pipeline
from clipper.projects.runtime_settings import RuntimeConfiguration
from clipper.projects.stages import StageRunner
from clipper.transcription import ProgressReporter


def optimize_project(
    session: Session,
    project: Project,
    runtime: RuntimeConfiguration,
    provider: GrowthInference,
    apply_edit: Callable[[Session, Clip, EditingPlanV1], None] | None = None,
    clip_ids: list[str] | None = None,
) -> None:
    request_key = project.job.enqueued_at.isoformat() if project.job else "manual"

    def optimize(progress: ProgressReporter) -> dict[str, object]:
        if not runtime.automatic_growth:
            return {"skipped": "Automatic growth is disabled in Settings"}
        clips = [clip for clip in project.clips if clip_ids is None or clip.id in clip_ids]
        for index, clip in enumerate(clips):
            if Pipeline._cancelled(session, project.id):
                raise InterruptedError("Project stopped")
            if project.job:
                project.job.phase = (
                    f"Analyzing audience and growth · clip {index + 1} of {len(clips)}"
                )
                session.commit()
            job = request_preparation(session, clip, force=True)
            job.status = "working"
            job.attempts += 1
            session.commit()
            try:
                prepare_clip(session, clip, runtime, provider, apply_edit, pipeline=True)
            except Exception as error:
                session.rollback()
                failed = session.get(GrowthPreparation, clip.id)
                if failed:
                    failed.status = "failed"
                    failed.error = str(error)[:1000]
                    failed.updated_at = now_utc()
                    session.commit()
                raise
            progress((index + 1) / len(clips))
        return {"clips": [clip.id for clip in clips], "model": runtime.model_for("growth")}

    StageRunner().run(
        session,
        project,
        "optimize_growth",
        Pipeline._key("growth-pipeline-v1", request_key, runtime.model_for("growth")),
        optimize,
        # Metadata generation may have refreshed copy since the previous attempt.
        validate_cached=lambda result: False,
    )
