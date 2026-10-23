from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.config import Settings
from clipper.domain.transcript import Transcript
from clipper.editorial.publishing_metadata import PublishingMetadata
from clipper.persistence import Base, Clip, Project, now_utc
from clipper.projects import metadata_pipeline
from clipper.projects.metadata_pipeline import MetadataPipeline
from clipper.projects.queue import ProjectQueue


@pytest.mark.parametrize("existing_master", [False, True])
def test_metadata_pipeline_keeps_full_video_and_refreshes_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_master: bool,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = tmp_path / "source" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"original video")
    monkeypatch.setattr(
        metadata_pipeline, "probe_media", lambda *_: {"duration_seconds": 42, "has_audio": True}
    )
    transcription = Mock(identity="test:transcript")
    transcription.transcribe.return_value = Transcript.model_validate(
        {
            "language": "en",
            "provider": "test",
            "model": "test",
            "segments": [
                {
                    "id": 1,
                    "text": "How to grow tomatoes.",
                    "start_seconds": 0,
                    "end_seconds": 42,
                    "words": [],
                }
            ],
        }
    )
    provider = Mock(identity="test:metadata")
    provider.generate.return_value = PublishingMetadata(
        suggested_title="Grow better tomatoes",
        suggested_description="Learn to grow tomatoes at home.",
        hashtags=["#Tomatoes", "#Gardening", "#Homegrown"],
    )
    pipeline = MetadataPipeline(Settings(), transcription, provider)
    with Session(engine) as session:
        project = Project(
            title="Video",
            original_filename=source.name,
            source_path=str(source),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()
        queue = ProjectQueue()
        queue.enqueue(session, project, processing_mode="metadata")
        if existing_master:
            from clipper.domain.editing_plan import EditingPlanV1

            plan = EditingPlanV1.model_validate(
                {
                    "source": {"start_seconds": 0, "end_seconds": 42},
                    "scores": dict.fromkeys(
                        ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                    ),
                    "rationale": "Uploaded master",
                    "caption_config": {"enabled": False},
                }
            )
            final = source.parent / "clips" / "master" / "final.mp4"
            final.parent.mkdir(parents=True)
            final.write_bytes(b"existing finished video")
            session.add(
                Clip(
                    id="master",
                    project=project,
                    plan=plan.model_dump(mode="json"),
                    final_path=str(final),
                    approval_status="approved",
                )
            )
            session.commit()
        pipeline.run(session, project)
        assert project.status == "complete"
        assert project.title == "Grow better tomatoes"
        assert len(project.clips) == 1
        clip = project.clips[0]
        original_id, original_path = clip.id, clip.final_path
        assert original_path
        expected = b"existing finished video" if existing_master else b"original video"
        assert Path(original_path).read_bytes() == expected
        assert clip.approval_status == "approved"
        assert clip.plan["source"] == {"start_seconds": 0, "end_seconds": 42}
        assert clip.plan["suggested_description"] == "Learn to grow tomatoes at home."
        assert clip.plan["hashtags"] == ["#Tomatoes", "#Gardening", "#Homegrown"]
        assert {stage.name for stage in project.stages} == {
            "probe",
            "transcribe",
            "generate_metadata",
        }
        project.job.status = "completed"
        session.commit()
        queue.enqueue(session, project, processing_mode="metadata")
        pipeline.run(session, project)
        assert len(project.clips) == 1
        assert project.clips[0].id == original_id
        assert project.clips[0].final_path == original_path
        assert Path(original_path).read_bytes() == expected
        assert transcription.transcribe.call_count == 1
        assert provider.generate.call_count == 2
        project.job.status = "failed"
        project.status = "failed"
        session.commit()
        queue.enqueue(session, project, retry=True)
        assert project.job.processing_mode == "metadata"
        assert source.read_bytes() == b"original video"


def test_existing_database_defaults_jobs_to_clipping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import inspect, text

    from clipper.persistence import session as database

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE project_jobs (project_id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO project_jobs (project_id) VALUES ('saved-job')"))
    monkeypatch.setattr(database, "engine", engine)
    database.create_schema()
    database.create_schema()
    assert "processing_mode" in {
        column["name"] for column in inspect(engine).get_columns("project_jobs")
    }
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT processing_mode FROM project_jobs")).scalar() == "clips"
        )
    engine.dispose()


@pytest.mark.parametrize("mode", ["clips", "metadata"])
def test_worker_runs_publishing_metadata_with_or_without_clipping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    from clipper.api import dependencies
    from clipper.projects.runtime_settings import RuntimeConfiguration

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(
            title="Source",
            original_filename="video.mp4",
            source_path=str(tmp_path / "source.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()
        ProjectQueue().enqueue(session, project, processing_mode=mode)
        clips = Mock()
        metadata = Mock()
        monkeypatch.setattr(dependencies, "Pipeline", Mock(return_value=clips))
        monkeypatch.setattr(dependencies, "MetadataPipeline", Mock(return_value=metadata))
        monkeypatch.setattr(
            dependencies.runtime_settings_service,
            "get",
            lambda _: RuntimeConfiguration(
                ollama_base_url="http://local",
                editorial_model="test",
                thumbnail_model="vision",
                task_models={"metadata": "copy-model", "clip_selection": "selector-model"},
                transcription_model="small",
            ),
        )
        growth = Mock()
        monkeypatch.setattr(dependencies, "optimize_pipeline_growth", growth)
        dependencies.analyze_project(session, project.id, None, ())
        growth.assert_called_once_with(session, project, metadata_only=mode == "metadata")
        assert dependencies.MetadataPipeline.call_args.args[1].model_name == "small"
        assert dependencies.MetadataPipeline.call_args.args[2].model == "copy-model"
        if mode == "clips":
            clips.run.assert_called_once_with(session, project.id, clip_types=())
            assert dependencies.Pipeline.call_args.args[2].model == "selector-model"
            metadata.run.assert_called_once_with(session, project, final_status="processing")
            assert project.status == "review"
        else:
            clips.run.assert_not_called()
            metadata.run.assert_called_once_with(session, project, final_status="processing")
            assert project.status == "complete"
    engine.dispose()


def test_silent_video_metadata_uses_frames_instead_of_generated_title(
    tmp_path, monkeypatch, make_plan
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        metadata_pipeline, "probe_media", lambda *_: {"duration_seconds": 30, "has_audio": False}
    )
    transcription = Mock(identity="silent")
    metadata = Mock(identity="grounded-copy")
    metadata.generate.return_value = PublishingMetadata(
        suggested_title="VoiceStudio local voice cloning",
        suggested_description="A presentation of the VoiceStudio repository.",
        hashtags=["#VoiceStudio", "#GitHub", "#VoiceCloning"],
    )
    evidence = Mock(
        return_value="Observed frames: VoiceStudio repository and local voice cloning labels"
    )
    with Session(engine) as session:
        project = Project(
            title="Unrelated old generated topic",
            original_filename="VoiceStudio_30s.mp4",
            source_path=str(tmp_path / "video.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        clip = Clip(
            project=project,
            plan=make_plan(0, 30).model_dump(mode="json"),
            approval_status="approved",
            final_path="original-final.mp4",
        )
        session.add_all([project, clip])
        session.commit()
        MetadataPipeline(Settings(), transcription, metadata, evidence).run(session, project)
        evidence.assert_called_once_with(session, clip)
        metadata.generate.assert_called_once_with(
            "VoiceStudio_30s.mp4",
            "Observed video frames (not spoken transcript): " + evidence.return_value,
        )
        transcription.transcribe.assert_not_called()
        assert clip.final_path == "original-final.mp4"
        assert clip.plan["suggested_title"] == "VoiceStudio local voice cloning"
    engine.dispose()
