from collections.abc import Callable
from pathlib import Path
from typing import Never

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from clipper.persistence import Base, Project, StageRun, StageStatus, now_utc
from clipper.projects import StageRunner


def test_failed_stage_can_retry_without_losing_attempt_history(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    runner = StageRunner()
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

        def fail(progress: Callable[[float], None]) -> Never:
            raise RuntimeError("interrupted worker")

        with pytest.raises(RuntimeError, match="interrupted worker"):
            runner.run(session, project, "transcribe", "cache-v1", fail)
        stage = session.scalar(select(StageRun).where(StageRun.project_id == project.id))
        assert stage is not None
        assert stage.status == StageStatus.FAILED
        assert stage.attempts == 1

        result = runner.run(
            session, project, "transcribe", "cache-v1", lambda progress: {"recovered": True}
        )
        assert result == {"recovered": True}
        assert stage.status == StageStatus.SUCCEEDED
        assert stage.attempts == 2


def test_stage_persists_monotonic_progress(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    runner = StageRunner()
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Progress fixture",
            original_filename="source.mp4",
            source_path=str(source),
            media_sha256="b" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()

        def operation(progress: Callable[[float], None]) -> dict[str, bool]:
            progress(0.2)
            progress(0.1)
            progress(0.75)
            stage = session.scalar(select(StageRun).where(StageRun.project_id == project.id))
            assert stage is not None
            assert stage.progress == 0.75
            return {"complete": True}

        runner.run(session, project, "transcribe", "cache-v2", operation)
        stage = session.scalar(select(StageRun).where(StageRun.project_id == project.id))
        assert stage is not None
        assert stage.progress == 1
