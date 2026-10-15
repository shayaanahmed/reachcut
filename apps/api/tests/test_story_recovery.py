from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_video_generation import sample_plan

from clipper.generation import SceneGenerationResult, StoryPlan
from clipper.media import MediaError
from clipper.persistence import Base
from clipper.projects.story_videos import StoryVideoCreate, StoryVideoService


def setup_job(tmp_path: Path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = Mock(identity="test")

    def generate(request, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"valid")
        return SceneGenerationResult(output, "test", 576, 1024)

    def extract(video, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"frame")
        return output

    def stitch(scenes, output, **_):
        output.write_bytes(b"valid")
        return output

    provider.generate_scene.side_effect = generate
    finisher = Mock()
    finisher.validate_video.side_effect = (
        lambda path, *_: path.is_file() and path.read_bytes() == b"valid"
    )
    finisher.valid_frame.side_effect = lambda path: path.is_file() and path.read_bytes() == b"frame"
    finisher.extract_last_frame.side_effect = extract
    finisher.stitch.side_effect = stitch
    service = StoryVideoService(tmp_path / "stories", provider, finisher)
    payload = sample_plan()
    scene = payload["scenes"][0]
    payload["scenes"] = [{**scene, "index": index, "seed": 4200 + index} for index in range(1, 4)]
    with Session(engine) as session:
        video = service.create(
            session,
            StoryVideoCreate(
                story="A clockmaker rescues a child with the help of a mechanical bird.",
                template="cinematic_story",
                aspect_ratio="9:16",
                quality="draft",
                plan=StoryPlan.model_validate(payload),
            ),
        )
        video_id = video.id
    return engine, service, provider, finisher, video_id


def test_resume_preserves_completed_scene_across_sessions(tmp_path: Path) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    generate = provider.generate_scene.side_effect

    def fail_second(request, output):
        if request.seed == 4202:
            raise MediaError("LTX unavailable")
        return generate(request, output)

    provider.generate_scene.side_effect = fail_second
    with Session(engine) as session:
        with pytest.raises(MediaError):
            service.render(session, video_id)
        video = service.get(session, video_id)
        assert [scene.status for scene in video.scenes] == ["complete", "failed", "queued"]
        first_path = Path(video.scenes[0].output_path)
        first_mtime = first_path.stat().st_mtime_ns
    provider.generate_scene.reset_mock(side_effect=False)
    provider.generate_scene.side_effect = generate
    finisher.extract_last_frame.reset_mock(side_effect=False)
    with Session(engine) as session:
        queued = service.requeue(session, video_id)
        assert "scene 2" in queued.phase
        assert queued.scenes[0].status == "complete"
        video = service.render(session, video_id)
        assert video.status == "complete"
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [
            4202,
            4203,
        ]
        assert first_path.stat().st_mtime_ns == first_mtime
        assert finisher.extract_last_frame.call_count == 1


def test_continuity_failure_keeps_render_checkpoint(tmp_path: Path) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    extract = finisher.extract_last_frame.side_effect
    finisher.extract_last_frame.side_effect = MediaError("Frame extraction failed")
    with Session(engine) as session:
        with pytest.raises(MediaError):
            service.render(session, video_id)
        failed = service.get(session, video_id)
        assert failed.scenes[0].output_path is not None
        assert failed.scenes[0].progress == 0.9
        assert "continuity" in failed.phase
        assert provider.generate_scene.call_count == 1
    provider.generate_scene.reset_mock(side_effect=False)
    finisher.extract_last_frame.side_effect = extract
    with Session(engine) as session:
        service.requeue(session, video_id)
        assert service.render(session, video_id).status == "complete"
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [
            4202,
            4203,
        ]


def test_corrupt_nonempty_scene_is_replaced_without_regenerating_other_scenes(
    tmp_path: Path,
) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    with Session(engine) as session:
        video = service.render(session, video_id)
        corrupted = Path(video.scenes[1].output_path)
        corrupted.write_bytes(b"x" * 48)
        video.status = "failed"
        video.scenes[1].status = "failed"
        session.commit()
    provider.generate_scene.reset_mock(side_effect=False)
    with Session(engine) as session:
        service.requeue(session, video_id)
        assert service.render(session, video_id).status == "complete"
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [4202]
        assert corrupted.read_bytes() == b"valid"


def test_stitch_failure_retries_only_final_export(tmp_path: Path) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    stitch = finisher.stitch.side_effect
    finisher.stitch.side_effect = MediaError("Export failed")
    with Session(engine) as session:
        with pytest.raises(MediaError):
            service.render(session, video_id)
        failed = service.get(session, video_id)
        assert all(scene.status == "complete" for scene in failed.scenes)
    provider.generate_scene.reset_mock(side_effect=False)
    finisher.extract_last_frame.reset_mock(side_effect=False)
    finisher.stitch.side_effect = stitch
    with Session(engine) as session:
        assert "final stitching" in service.requeue(session, video_id).phase
        assert service.render(session, video_id).status == "complete"
        provider.generate_scene.assert_not_called()
        finisher.extract_last_frame.assert_not_called()


def test_resume_promotes_valid_pending_render_after_interruption(tmp_path: Path) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    pending = tmp_path / "stories" / video_id / "scenes" / "scene-01.pending.mp4"
    pending.parent.mkdir(parents=True)
    pending.write_bytes(b"valid")
    with Session(engine) as session:
        assert service.render(session, video_id).status == "complete"
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [
            4202,
            4203,
        ]
        assert not pending.exists()


def test_engine_conflict_waits_in_queue_and_preserves_completed_scenes(tmp_path: Path) -> None:
    from clipper.generation import VideoGenerationBusyError

    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    generate = provider.generate_scene.side_effect

    def busy_second(request, output):
        if request.seed == 4202:
            raise VideoGenerationBusyError("Generation already in progress")
        return generate(request, output)

    provider.generate_scene.side_effect = busy_second
    with Session(engine) as session:
        waiting = service.render(session, video_id)
        assert waiting.status == "queued"
        assert waiting.error is None
        assert "automatically" in waiting.phase
        assert [scene.status for scene in waiting.scenes] == ["complete", "queued", "queued"]
    provider.generate_scene.reset_mock(side_effect=False)
    provider.generate_scene.side_effect = generate
    with Session(engine) as session:
        assert service.render(session, video_id).status == "complete"
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [
            4202,
            4203,
        ]


def test_scheduler_checks_engine_busy_before_submitting_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipper.api import dependencies

    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(dependencies, "story_video_service", service)
    monkeypatch.setattr(dependencies, "local_video_provider", provider)
    provider.generation_progress.return_value = {"status": "running", "progress": 42}
    assert dependencies.run_story_video_cycle() is None
    provider.generate_scene.assert_not_called()
    with Session(engine) as session:
        waiting = service.get(session, video_id)
        assert waiting.status == "queued"
        assert "42%" in waiting.phase
    provider.generation_progress.return_value = {"status": "complete", "progress": 100}
    provider.model_recommendation.return_value = {"status": "ready"}
    assert dependencies.run_story_video_cycle() == video_id
    with Session(engine) as session:
        assert service.get(session, video_id).status == "complete"


def test_editing_saved_shots_reexports_without_gpu_render(tmp_path: Path) -> None:
    engine, service, provider, finisher, video_id = setup_job(tmp_path)
    with Session(engine) as session:
        video = service.render(session, video_id)
        updated = dict(video.plan)
        updated["scenes"] = [dict(scene) for scene in updated["scenes"]]
        updated["scenes"][1]["trim_start_seconds"] = 2.5
        video.plan = updated
        video.status = "finishing"
        session.commit()
    provider.generate_scene.reset_mock(side_effect=False)
    finisher.stitch.reset_mock(side_effect=False)
    with Session(engine) as session:
        assert service.render(session, video_id).status == "complete"
        provider.generate_scene.assert_not_called()
        assert finisher.stitch.call_count == 1


def test_stop_queued_story_prevents_render_and_allows_delete(tmp_path: Path) -> None:
    engine, service, provider, _, video_id = setup_job(tmp_path)
    with Session(engine) as session:
        assert service.stop(session, video_id).status == "cancelled"
        assert service.render(session, video_id).status == "cancelled"
        provider.generate_scene.assert_not_called()
        service.delete(session, video_id)
        assert service.list(session) == []


def test_stop_during_render_preserves_checkpoint_and_can_resume(tmp_path: Path) -> None:
    engine, service, provider, _, video_id = setup_job(tmp_path)
    generate = provider.generate_scene.side_effect

    def stop_second(request, output):
        result = generate(request, output)
        if request.seed == 4202:
            with Session(engine) as control:
                assert service.stop(control, video_id).status == "cancel_requested"
                with pytest.raises(ValueError, match="Active"):
                    service.delete(control, video_id)
        return result

    provider.generate_scene.side_effect = stop_second
    with Session(engine) as session:
        stopped = service.render(session, video_id)
        assert stopped.status == "cancelled"
        assert stopped.scenes[0].status == "complete"
        assert provider.generate_scene.call_count == 2
    provider.generate_scene.reset_mock()
    provider.generate_scene.side_effect = generate
    with Session(engine) as session:
        service.requeue(session, video_id)
        assert service.render(session, video_id).status == "complete"
        # The saved pending second scene is reused, as well as the first scene.
        assert [call.args[0].seed for call in provider.generate_scene.call_args_list] == [4203]
