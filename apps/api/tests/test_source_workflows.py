from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.persistence import Base, Clip, Project, now_utc
from clipper.persistence.models import SourceWorkflowRun
from clipper.projects.language_versions import localize_project
from clipper.projects.queue import ProjectQueue
from clipper.projects.runtime_settings import RuntimeConfiguration
from clipper.projects.source_workflows import WorkflowRequest, create_workflow
from clipper.providers.localization import LocalizedCopy


@pytest.fixture
def source_session(tmp_path, make_plan):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = tmp_path / "source" / "source.mp4"
        source.parent.mkdir()
        source.write_bytes(b"immutable-source")
        project = Project(
            title="VoiceStudio",
            original_filename="source.mp4",
            source_path=str(source),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
            status="complete",
            duration_seconds=30,
            transcript={
                "language": "en",
                "provider": "test",
                "model": "test",
                "segments": [
                    {
                        "id": 1,
                        "text": "Local voice cloning",
                        "start_seconds": 0,
                        "end_seconds": 30,
                        "words": [{"text": "Local", "start_seconds": 0, "end_seconds": 1}],
                    }
                ],
            },
        )
        clip = Clip(
            project=project,
            plan=make_plan(0, 30).model_dump(mode="json"),
            approval_status="approved",
        )
        session.add_all([project, clip])
        session.flush()
        final = source.parent / "clips" / clip.id / "final.mp4"
        final.parent.mkdir(parents=True)
        final.write_bytes(b"original-export")
        clip.final_path = str(final)
        session.commit()
        yield session, project, clip, tmp_path / "outputs"
    engine.dispose()


def request(kind="language", **kwargs):
    return WorkflowRequest(idempotency_key=uuid4(), kind=kind, **kwargs)


def test_language_versions_have_independent_exports_and_ids(source_session):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request(target_language="ar"), root)
    output = session.get(Project, run.target_project_id)
    assert output.id != project.id
    assert output.job.processing_mode == "language"
    assert output.clips[0].id != clip.id
    assert not output.clips[0].publications
    assert Path(output.clips[0].final_path).stat().st_ino != Path(clip.final_path).stat().st_ino
    Path(output.clips[0].final_path).write_bytes(b"new-render")
    assert Path(clip.final_path).read_bytes() == b"original-export"
    assert output.source_path != project.source_path
    assert Path(project.source_path).read_bytes() == b"immutable-source"


def test_retrying_submission_is_idempotent_and_different_options_are_rejected(source_session):
    session, project, clip, root = source_session
    options = request(target_language="vi")
    first = create_workflow(session, project, options, root)
    second = create_workflow(session, project, options, root)
    assert first.id == second.id
    assert session.query(SourceWorkflowRun).count() == 1
    with pytest.raises(ValueError, match="different workflow"):
        create_workflow(
            session, project, options.model_copy(update={"target_language": "ar"}), root
        )


def test_metadata_refresh_tracks_selected_existing_clips_and_cancellation(source_session):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request("metadata", clip_ids=[clip.id]), root)
    assert run.target_project_id == project.id and run.clip_ids == [clip.id]
    assert project.job.processing_mode == "metadata"
    ProjectQueue().cancel(session, project)
    assert run.status == "cancelled"
    assert Path(clip.final_path).read_bytes() == b"original-export"


def test_queue_records_success_and_failure_in_workflow_history(source_session):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request("clips"), root)

    def analyze(db, id, language, types):
        assert run.status == "running"
        db.get(Project, id).status = "review"

    ProjectQueue().run_next(session, Mock(), analyze)
    assert run.status == "completed" and run.finished_at
    other = create_workflow(session, project, request("full"), root)
    ProjectQueue().run_next(session, Mock(), Mock(side_effect=ValueError("Source issue")))
    assert other.status == "failed" and "Source issue" in other.error


def test_metadata_only_localization_changes_copy_without_rendering_or_touching_source(
    source_session, monkeypatch
):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request(target_language="ar"), root)
    output = session.get(Project, run.target_project_id)
    output.status = "processing"
    session.commit()
    monkeypatch.setattr(
        "clipper.projects.language_versions.localize_copy",
        lambda *args: LocalizedCopy(
            title="استنساخ الصوت محليًا",
            description="عرض لمشروع VoiceStudio",
            hashtags=["#VoiceStudio", "#صوت"],
        ),
    )
    service = Mock()
    localize_project(
        session, output, RuntimeConfiguration("http://local", "text", "vision"), service
    )
    assert output.status == "review"
    assert output.clips[0].plan["suggested_title"] == "استنساخ الصوت محليًا"
    assert Path(output.clips[0].final_path).read_bytes() == b"original-export"
    service.apply_language_plan.assert_not_called()
    assert clip.plan.get("suggested_title") != output.clips[0].plan["suggested_title"]
    assert output.clips[0].growth_preparation.status == "manual"


def test_invalid_selection_and_missing_narration_are_rejected_without_outputs(source_session):
    session, project, clip, root = source_session
    with pytest.raises(ValueError, match="belonging"):
        create_workflow(session, project, request("metadata", clip_ids=["missing"]), root)
    with pytest.raises(ValueError, match="Upload translated narration"):
        create_workflow(session, project, request(target_language="ur", scopes=["narration"]), root)
    assert session.query(SourceWorkflowRun).count() == 0


def test_interrupted_workflow_recovery_requeues_or_finishes_cancellation(source_session):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request("clips"), root)
    target = session.get(Project, run.target_project_id)
    target.job.status, target.status, run.status = "running", "processing", "running"
    session.commit()
    ProjectQueue().recover(session)
    assert (target.job.status, run.status) == ("queued", "queued")
    target.job.status, target.status, run.status = "running", "cancel_requested", "running"
    session.commit()
    ProjectQueue().recover(session)
    assert (target.job.status, run.status) == ("cancelled", "cancelled")
    assert run.finished_at


def test_localization_reapplies_after_metadata_is_restored_on_recovery(source_session, monkeypatch):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request(target_language="vi"), root)
    target = session.get(Project, run.target_project_id)
    translator = Mock(
        return_value=LocalizedCopy(
            title="Tiếng Việt", description="Mô tả", hashtags=["#VoiceStudio"]
        )
    )
    monkeypatch.setattr("clipper.projects.language_versions.localize_copy", translator)
    runtime = RuntimeConfiguration("http://local", "text", "vision")
    localize_project(session, target, runtime, Mock())
    target.clips[0].plan = {**target.clips[0].plan, "suggested_title": "English source"}
    session.commit()
    localize_project(session, target, runtime, Mock())
    assert target.clips[0].plan["suggested_title"] == "Tiếng Việt"
    assert translator.call_count == 2


def test_legacy_retry_preserves_workflow_selection(source_session):
    session, project, clip, root = source_session
    run = create_workflow(session, project, request("metadata", clip_ids=[clip.id]), root)
    ProjectQueue().cancel(session, project)
    ProjectQueue().enqueue(session, project, retry=True)
    assert run.status == "queued"
    assert run.clip_ids == [clip.id]


def test_workflow_http_contract_creates_once_and_retries_same_output(source_session, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from clipper.api import source_workflows as routes
    from clipper.main import app
    from clipper.persistence import get_session

    session, project, clip, root = source_session
    app.dependency_overrides[get_session] = lambda: session
    monkeypatch.setattr(routes, "settings", SimpleNamespace(data_dir=root))
    try:
        with TestClient(app) as client:
            url = f"/api/projects/{project.id}/workflows"
            assert client.get(url).json() == {"speech_available": True, "runs": []}
            assert client.post(url, data={"payload": "invalid"}).status_code == 422
            payload = request("full").model_dump_json()
            response = client.post(url, data={"payload": payload})
            assert response.status_code == 202
            run = response.json()
            assert client.post(url, data={"payload": payload}).json()["id"] == run["id"]
            assert len(client.get(url).json()["runs"]) == 1
            target = session.get(Project, run["target_project_id"])
            ProjectQueue().cancel(session, target)
            response = client.post(f"/api/workflow-runs/{run['id']}/retry")
            assert response.status_code == 202
            assert response.json()["target_project_id"] == target.id
            assert response.json()["status"] == "queued"
    finally:
        app.dependency_overrides.pop(get_session, None)
