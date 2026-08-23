import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.persistence import Project, StageRun, StageStatus
from clipper.transcription import ProgressReporter

StageResult = TypeVar("StageResult")


class StageRunner:
    """Persist and resume a named project operation through one public method."""

    def run(
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
            artifact = self.artifact_path(project, name)
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
            artifact = self.artifact_path(project, name)
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

    @staticmethod
    def artifact_path(project: Project, name: str) -> Path:
        return Path(project.source_path).parent / "stages" / f"{name}.json"
