from collections.abc import Callable
from pathlib import Path
from typing import Never

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.db import Base, Project, StageRun, StageStatus, now_utc
from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.services.pipeline import Pipeline


class FakeTranscription:
    identity = "fake-transcription:v1"

    def transcribe(self, media: Path, cancelled: Callable[[], bool]) -> Transcript:
        return Transcript(language="en", segments=[], provider="fake", model="fake")


class FakeEditorial:
    identity = "fake-editorial:v1"

    def select_candidates(
        self, transcript: Transcript, target_count: int, cancelled: Callable[[], bool]
    ) -> list[EditingPlanV1]:
        return []


def test_failed_stage_can_retry_without_losing_attempt_history(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    pipeline = Pipeline(
        Settings(data_dir=tmp_path, database_url="sqlite://"),
        FakeTranscription(),
        FakeEditorial(),
    )
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Recovery fixture",
            original_filename="source.mp4",
            source_path=str(source),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()

        def fail() -> Never:
            raise RuntimeError("interrupted worker")

        with pytest.raises(RuntimeError, match="interrupted worker"):
            pipeline._stage(session, project, "transcribe", "cache-v1", fail)
        stage = session.scalar(select(StageRun).where(StageRun.project_id == project.id))
        assert stage is not None
        assert stage.status == StageStatus.FAILED
        assert stage.attempts == 1

        result = pipeline._stage(
            session, project, "transcribe", "cache-v1", lambda: {"recovered": True}
        )
        assert result == {"recovered": True}
        assert stage.status == StageStatus.SUCCEEDED
        assert stage.attempts == 2
