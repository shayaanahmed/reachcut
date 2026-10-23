from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from clipper.domain.transcript import Segment, Transcript
from clipper.editorial.quality import candidate_findings, distinct_candidates
from clipper.persistence.models import (
    Base,
    Clip,
    Project,
    Publication,
    PublicationDestination,
    SocialAccount,
    now_utc,
)
from clipper.projects.publications import (
    AutomaticPublicationCreate,
    PublicationService,
    PublicationStateError,
)
from clipper.projects.stages import StageRunner
from clipper.providers.youtube import _http_error
from clipper.publishing import OAuthConnection, PublishedPost


def test_candidate_overlap_and_sentence_findings(make_plan):  # type: ignore[no-untyped-def]
    plans = [make_plan(10, 30, 85), make_plan(12, 32, 60), make_plan(45, 55, 20)]
    assert distinct_candidates(plans) == [plans[0]]
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(id=0, text="A whole sentence.", start_seconds=9, end_seconds=32, words=[])
        ],
    )
    findings = candidate_findings(plans[0], transcript)
    assert [f["start"] for f in findings] == [10, 30]
    assert all(f["basis"] == "source_transcript" for f in findings)


def test_corrupt_stage_cache_rebuilds_and_changed_input_invalidates(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Cache",
            original_filename="source.mp4",
            source_path=str(tmp_path / "source.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()
        runner = StageRunner()
        calls = []

        def operation(progress):  # type: ignore[no-untyped-def]
            calls.append(1)
            return {"version": 1, "result": len(calls)}

        assert runner.run(session, project, "probe", "v1", operation)["result"] == 1
        runner.run(session, project, "probe", "v1", operation)
        assert len(calls) == 1
        runner.artifact_path(project, "probe").write_text("{")
        assert runner.run(session, project, "probe", "v1", operation)["result"] == 2
        assert runner.run(session, project, "probe", "v2", operation)["result"] == 3


def test_youtube_channel_limits_are_separate_from_api_quota() -> None:
    request = httpx.Request("POST", "https://www.googleapis.com/upload/youtube/v3/videos")
    for reason, expected in [
        ("uploadLimitExceeded", "channel has an upload restriction"),
        ("quotaExceeded", "Google Cloud API quota"),
    ]:
        response = httpx.Response(
            403, json={"error": {"errors": [{"reason": reason}]}}, request=request
        )
        message = _http_error(
            "YouTube", httpx.HTTPStatusError("blocked", request=request, response=response)
        )
        assert expected in message
        if reason == "uploadLimitExceeded":
            assert "did not supply a reset time" in message


class Credentials:
    def load(self, account_id):  # type: ignore[no-untyped-def]
        return OAuthConnection("fixture-credential")

    def save(self, *args):  # type: ignore[no-untyped-def]
        pass


class Publisher:
    def __init__(self, failure=""):  # type: ignore[no-untyped-def]
        self.calls = 0
        self.failure = failure

    def publish(self, *args):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.failure:
            raise RuntimeError(self.failure)
        return PublishedPost(post_url="https://youtube.com/shorts/fixture")


def test_upload_restriction_pauses_account_and_preserves_reservation(make_plan):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Publish",
            original_filename="source.mp4",
            source_path="/fixture/source.mp4",
            media_sha256="b" * 64,
            authorization_confirmed_at=now_utc(),
        )
        clip = Clip(
            project=project,
            plan=make_plan().model_dump(mode="json"),
            approval_status="approved",
            final_path="/fixture/final.mp4",
        )
        account = SocialAccount(platform="youtube", label="Channel", connection_status="connected")
        session.add_all([project, clip, account])
        session.commit()
        service = PublicationService()
        request = AutomaticPublicationCreate(account.id, "Title", "Description")
        publisher = Publisher("uploadLimitExceeded")
        with pytest.raises(RuntimeError, match="uploadLimitExceeded"):
            service.publish(session, clip.id, request, publisher, Credentials())
        publication = session.scalar(select(Publication))
        assert publication and publication.status == "deferred"
        assert session.get(PublicationDestination, publication.id)
        with pytest.raises(PublicationStateError, match="paused"):
            service.publish(session, clip.id, request, publisher, Credentials())
        assert publisher.calls == 1


def test_queued_publication_is_claimed_once(make_plan):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            title="Publish",
            original_filename="source.mp4",
            source_path="/fixture/source.mp4",
            media_sha256="b" * 64,
            authorization_confirmed_at=now_utc(),
        )
        clip = Clip(
            project=project,
            plan=make_plan().model_dump(mode="json"),
            approval_status="approved",
            final_path="/fixture/final.mp4",
        )
        account = SocialAccount(platform="youtube", label="Channel", connection_status="connected")
        session.add_all([project, clip, account])
        session.commit()
        service = PublicationService()
        request = AutomaticPublicationCreate(account.id, "Title", "Description")
        _, queued = service.queue_many(session, clip.id, [request], Credentials())
        publication_id, _ = queued[0]
        publisher = Publisher()
        service.publish_queued(session, publication_id, request, publisher, Credentials())
        with pytest.raises(PublicationStateError, match="no longer queued"):
            service.publish_queued(session, publication_id, request, publisher, Credentials())
        assert publisher.calls == 1


def test_review_correction_is_bounded_and_keeps_unresolved_findings(
    tmp_path: Path, make_plan, monkeypatch
):  # type: ignore[no-untyped-def]
    import clipper.projects.pipeline as module
    from clipper.config import Settings
    from clipper.domain.transcript import Transcript
    from clipper.projects.pipeline import Pipeline

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    pipeline = Pipeline(
        Settings(),
        type("Transcription", (), {"identity": "fixture"})(),
        type("Editorial", (), {"identity": "fixture"})(),
    )
    renders = []

    def render(session, project, clips, progress):
        renders.append(1)
        Path(clips[0].preview_path).write_bytes(b"still invalid fixture")
        return []

    monkeypatch.setattr(pipeline, "_render_previews", render)
    monkeypatch.setattr(
        module,
        "inspect_render",
        lambda *args, **kwargs: [
            {
                "severity": "error",
                "code": "decode",
                "start": 0,
                "message": "Cannot decode",
                "basis": "rendered_media",
            }
        ],
    )
    with Session(engine) as session:
        source = tmp_path / "source.mp4"
        preview = tmp_path / "preview.mp4"
        preview.write_bytes(b"broken fixture")
        project = Project(
            title="Review",
            original_filename="source.mp4",
            source_path=str(source),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.flush()
        clip = Clip(
            project_id=project.id,
            plan=make_plan().model_dump(mode="json"),
            preview_path=str(preview),
        )
        session.add(clip)
        session.commit()
        result = pipeline._review(
            session,
            project,
            [clip],
            Transcript(language="en", provider="fixture", model="fixture", segments=[]),
        )
        assert len(renders) == 1
        assert result["clips"][0]["findings"][0]["severity"] == "error"
        assert len(result["clips"][0]["corrections"]) == 1


def test_publication_recovery_uses_saved_privacy_without_external_uploads(monkeypatch):  # type: ignore[no-untyped-def]
    import clipper.api.dependencies as dependencies
    from clipper.persistence.models import PublicationAccountLink, PublicationOptions

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(
            id="privacy-project",
            title="Privacy",
            original_filename="source.mp4",
            source_path="/fixture/source.mp4",
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
        )
        clip = Clip(id="privacy-clip", project=project, plan={})
        account = SocialAccount(id="privacy-account", platform="youtube", label="Channel")
        publication = Publication(
            id="privacy-publication",
            clip=clip,
            platform="youtube",
            status="queued",
            title="Title",
            description="Description",
        )
        session.add_all([project, clip, account, publication])
        session.flush()
        session.add_all(
            [
                PublicationAccountLink(
                    publication_id=publication.id,
                    social_account_id=account.id,
                    account_label_snapshot="Channel",
                ),
                PublicationOptions(publication_id=publication.id, privacy_status="private"),
            ]
        )
        session.commit()
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: Session(engine))
    calls = []
    monkeypatch.setattr(dependencies, "run_publication_batch", lambda queued: calls.extend(queued))
    dependencies.run_publication_cycle()
    assert len(calls) == 1 and calls[0][1].privacy_status == "private"


def test_silent_recording_is_a_valid_visual_but_not_a_finished_narrated_video(
    tmp_path: Path,
) -> None:
    import json
    import subprocess

    from clipper.media.video_validation import valid_generated_video

    recording = tmp_path / "screen.mp4"
    recording.write_bytes(b"screen recording fixture")
    calls = []

    def runner(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"format": {"duration": 10}, "streams": [{"codec_type": "video"}]}),
            "",
        )

    assert valid_generated_video(
        recording, require_audio=False, runner=runner, tool_locator=lambda x: x
    )
    assert "0:a:0" not in calls[-1]
    assert not valid_generated_video(recording, runner=runner, tool_locator=lambda x: x)


def test_editorial_cache_identity_includes_endpoint_and_generation_settings() -> None:
    from clipper.providers.ollama import EditorialGenerationConfig, OllamaEditorialProvider

    first = OllamaEditorialProvider("http://localhost:11434", "same-model")
    endpoint = OllamaEditorialProvider("http://localhost:11435", "same-model")
    settings = OllamaEditorialProvider(
        "http://localhost:11434", "same-model", generation=EditorialGenerationConfig(num_ctx=16000)
    )
    assert len({first.identity, endpoint.identity, settings.identity}) == 3
    assert "localhost" not in first.identity
