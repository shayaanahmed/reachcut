from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.domain.editing_plan import ClipType
from clipper.media import StoredUpload
from clipper.persistence import Base, Project, now_utc
from clipper.projects.queue import ProjectQueue


def make_project(session: Session, root: Path, project_id: str, *, url: bool = False) -> Project:
    source = root / project_id / "source" / "source.mp4"
    if not url:
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source")
    project = Project(
        id=project_id,
        title=project_id,
        original_filename=source.name,
        source_path=str(source),
        media_sha256="" if url else "a" * 64,
        authorization_confirmed_at=now_utc(),
        status="created",
    )
    session.add(project)
    session.commit()
    return project


def no_download(url: str, target: Path) -> StoredUpload:
    raise AssertionError("Existing media must not be downloaded again")


def complete(
    session: Session, project_id: str, language: str | None, types: tuple[ClipType, ...]
) -> None:
    project = session.get(Project, project_id)
    assert project
    project.status = "review"
    session.commit()


def test_fifo_duplicate_requests_and_failure_do_not_block_other_projects(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        first = make_project(session, tmp_path, "first")
        second = make_project(session, tmp_path, "second")
        job = queue.enqueue(session, first, "ur", (ClipType.STORY,))
        original_time = job.enqueued_at
        queue.enqueue(session, second)
        assert queue.enqueue(session, first, "en") is job
        assert job.enqueued_at == original_time
        assert job.language == "ur"

        def fail(
            session: Session, project_id: str, language: str | None, types: tuple[ClipType, ...]
        ) -> None:
            assert project_id == first.id
            assert language == "ur" and types == (ClipType.STORY,)
            raise RuntimeError("Transcription unavailable")

        assert queue.run_next(session, no_download, fail) == first.id
        assert first.status == "failed"
        assert job.error == "Transcription unavailable"
        assert queue.run_next(session, no_download, complete) == second.id
        assert second.status == "review"
        assert queue.run_next(session, no_download, complete) is None


def test_restart_preserves_inputs_and_cancellation_removes_waiting_jobs(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        first = make_project(session, tmp_path, "first")
        second = make_project(session, tmp_path, "second")
        job = queue.enqueue(session, first, "de", (ClipType.ADVICE,))
        job.status = "running"
        first.status = "processing"
        queue.enqueue(session, second)
        queue.cancel(session, second)
        session.commit()
    with Session(engine) as session:
        queue.recover(session)
        first = session.get(Project, "first")
        assert first and first.job
        assert first.job.status == "queued"
        assert first.job.language == "de"
        assert first.job.clip_types == ["advice"]
        assert queue.run_next(session, no_download, complete) == "first"
        assert queue.run_next(session, no_download, complete) is None
        second = session.get(Project, "second")
        assert second and second.status == "cancelled"


def test_url_download_is_deferred_and_retry_reuses_saved_media(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        project = make_project(session, tmp_path, "url", url=True)
        job = queue.enqueue(session, project, "en", source_url="https://example.com/video")
        assert not Path(project.source_path).exists()

        def download(url: str, target: Path) -> StoredUpload:
            assert url == job.source_url
            assert project.status == "downloading"
            target.mkdir(parents=True)
            source = target / "source.webm"
            source.write_bytes(b"downloaded")
            return StoredUpload(source, "b" * 64, 10)

        def fail(
            session: Session, project_id: str, language: str | None, types: tuple[ClipType, ...]
        ) -> None:
            raise RuntimeError("Model offline")

        queue.run_next(session, download, fail)
        assert project.status == "failed"
        assert Path(project.source_path).read_bytes() == b"downloaded"
        queue.enqueue(session, project, retry=True)
        assert job.language == "en" and job.error is None
        queue.run_next(session, no_download, complete)
        assert project.status == "review" and job.status == "completed"


def test_cancel_during_work_stops_job_and_advances_queue(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        project = make_project(session, tmp_path, "first")
        queue.enqueue(session, project)

        def cancel(
            session: Session, project_id: str, language: str | None, types: tuple[ClipType, ...]
        ) -> None:
            queue.cancel(session, project)
            raise InterruptedError("Project stopped")

        queue.run_next(session, no_download, cancel)
        assert project.status == "cancelled"
        assert project.job and project.job.status == "cancelled"


def test_recover_legacy_project_stuck_stopping_can_resume(tmp_path: Path) -> None:
    from clipper.persistence import StageRun

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        project = make_project(session, tmp_path, "legacy")
        project.status = "cancel_requested"
        session.add_all(
            [
                StageRun(project_id=project.id, name="transcribe", status="succeeded", progress=1),
                StageRun(
                    project_id=project.id, name="select_candidates", status="running", progress=0.2
                ),
            ]
        )
        session.commit()
        queue.recover(session)
        assert project.status == "cancelled"
        assert {stage.name: stage.status for stage in project.stages} == {
            "transcribe": "succeeded",
            "select_candidates": "cancelled",
        }
        queue.recover(session)
        queue.enqueue(session, project, retry=True)
        assert queue.run_next(session, no_download, complete) == project.id
        assert project.status == "review"


def test_pause_resume_preserves_settings_and_completed_artifacts(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    queue = ProjectQueue()
    with Session(engine) as session:
        project = make_project(session, tmp_path, "paused")
        artifact = Path(project.source_path).parent / "stages" / "transcribe.json"
        artifact.parent.mkdir()
        artifact.write_text('{"text": "saved transcript"}')
        job = queue.enqueue(session, project, "ur", (ClipType.ADVICE,))
        queue.cancel(session, project)
        assert project.status == "cancelled"
        queue.enqueue(session, project, retry=True)

        def resume(
            session: Session, project_id: str, language: str | None, types: tuple[ClipType, ...]
        ) -> None:
            assert language == "ur"
            assert types == (ClipType.ADVICE,)
            assert artifact.read_text() == '{"text": "saved transcript"}'
            complete(session, project_id, language, types)

        queue.run_next(session, no_download, resume)
        assert job.status == "completed"
