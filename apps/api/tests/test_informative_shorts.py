"""Orchestration fixtures are not evidence of narration or editorial quality."""

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import clipper.shorts.service as service_module
from clipper.persistence.models import Base, Clip, InformativeShort, Project
from clipper.providers.voicebox import VoiceboxError, VoiceboxNarrationProvider
from clipper.shorts.contracts import (
    Evidence,
    Script,
    ShortSettings,
    fingerprint,
    script_issues,
    speech_input,
)
from clipper.shorts.queue import run_next
from clipper.shorts.service import ShortService


class Narrator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_submit = False
        self.state = "completed"

    def capabilities(self) -> dict[str, object]:
        return {"connected": True}

    def submit(self, text: str, settings: ShortSettings) -> str:
        self.calls.append(text)
        if self.fail_submit:
            raise TimeoutError("submission connection interrupted")
        return str(len(self.calls))

    def status(self, generation_id: str) -> str:
        return self.state

    def audio(self, generation_id: str) -> bytes:
        return b"audio fixture, not real speech"

    def cancel(self, generation_id: str) -> bool:
        self.state = "cancelled"
        return True


def fixture_script() -> Script:
    return Script.model_validate(
        {
            "version": "1",
            "sections": [
                {
                    "id": f"part-{i}",
                    "heading": f"Section {i}",
                    "text": f"An evidenced explanation {i}.",
                    "visual": "explanation",
                    "claims": [
                        {
                            "text": "A supported fact",
                            "source_id": "source",
                            "quote": "The documented feature is available.",
                            "status": "supported",
                        }
                    ],
                }
                for i in range(2)
            ],
        }
    )


def add_short(session: Session, service: ShortService) -> InformativeShort:
    short = service.create(
        session,
        "An informative topic",
        ShortSettings(allow_explanation_cards=True, profile_id="voice"),
        "request-key",
    )
    short.sources = [
        Evidence(
            id="source",
            url="https://docs.python.org/3/",
            title="Documentation",
            text="The documented feature is available.",
        ).model_dump()
    ]
    service.save_script(session, short, fixture_script())
    service.approve_script(session, short)
    return short


@pytest.fixture
def session() -> Any:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def media(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    renders: list[str] = []
    monkeypatch.setattr(service_module, "audio_duration", lambda _: 17.0)

    def render(audio: Path, output: Path, *args: Any) -> Path:
        renders.append(output.name)
        output.write_bytes(b"render fixture")
        output.with_suffix(".ass").write_text("[Events]\n")
        return output

    def assemble(scenes: list[Path], output: Path) -> Path:
        output.write_bytes(b"assembled fixture")
        return output

    monkeypatch.setattr(service_module, "render_section", render)
    monkeypatch.setattr(service_module, "assemble_sections", assemble)
    monkeypatch.setattr(service_module, "inspect_render", lambda *args: [])
    return renders


def test_evidence_quote_must_exist_and_unresolved_claims_block() -> None:
    script = fixture_script()
    source = Evidence(
        id="source",
        title="Evidence",
        url="https://docs.python.org/3/",
        text="The documented feature is available.",
    )
    assert not script_issues(script, [source])
    script.sections[0].claims[0].quote = "Invented supporting statement"
    assert "not in source" in script_issues(script, [source])[0]["message"]
    script.sections[0].claims[0].quote = source.text
    script.sections[0].claims[0].status = "disputed"
    assert script_issues(script, [source])[0]["message"] == "Claim is disputed"


def test_approval_invalidated_by_script_and_language_change(
    session: Session, tmp_path: Path
) -> None:
    service = ShortService(tmp_path, Narrator())
    short = add_short(session, service)
    assert short.approved_hash == service.approval_hash(short)
    script = fixture_script()
    script.sections[0].text = "Revised explanation"
    service.save_script(session, short, script)
    with pytest.raises(ValueError, match="Approve"):
        service.enqueue(session, short)
    service.approve_script(session, short)
    short.settings = {**short.settings, "language": "ur"}
    with pytest.raises(ValueError, match="Approve"):
        service.enqueue(session, short)


def test_duration_caches_partial_replacement_and_publishing_approval(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    narrator = Narrator()
    service = ShortService(tmp_path, narrator)
    short = add_short(session, service)
    with pytest.raises(ValueError, match="Produce"):
        service.approve_video(session, short)
    service.enqueue(session, short)
    service.produce(session, short)
    assert short.status == "review"
    assert len(narrator.calls) == 2
    assert short.usage["actual_duration_seconds"] == 34
    assert short.usage["timeline"] == [
        {
            "section": "part-0",
            "start": 0.0,
            "end": 17.0,
            "caption_timing": "approximate phrases within measured narration section",
        },
        {
            "section": "part-1",
            "start": 17.0,
            "end": 34.0,
            "caption_timing": "approximate phrases within measured narration section",
        },
    ]
    service.enqueue(session, short)
    service.produce(session, short)
    assert len(narrator.calls) == 2 and len(media) == 2
    assets = dict(short.artifacts)
    asset = tmp_path / "replacement.png"
    asset.write_bytes(b"replacement fixture")
    assets["part-0"] = {**assets["part-0"], "asset": str(asset), "asset_hash": "changed"}
    short.artifacts = assets
    service.enqueue(session, short)
    service.produce(session, short)
    assert len(narrator.calls) == 2 and len(media) == 3
    path = service.approve_video(session, short)
    assert path.endswith("/publish")
    clip = session.scalar(select(Clip))
    assert (
        clip
        and clip.approval_status == "approved"
        and Path(clip.final_path).read_bytes() == Path(short.output_path).read_bytes()
    )
    assert session.scalar(select(Project)) is not None
    service.save_script(session, short, fixture_script())
    assert clip.approval_status == "approved" and Path(clip.final_path).exists()
    assert short.approved_hash is None and short.output_path is None


def test_unknown_submission_never_blindly_repeated(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    narrator = Narrator()
    narrator.fail_submit = True
    service = ShortService(tmp_path, narrator)
    short = add_short(session, service)
    with pytest.raises(TimeoutError):
        service.produce(session, short)
    narrator.fail_submit = False
    with pytest.raises(ValueError, match="reconcile"):
        service.produce(session, short)
    assert len(narrator.calls) == 1


def test_uploaded_narration_bypasses_voicebox_and_detects_script_edits(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    narrator = Narrator()
    service = ShortService(tmp_path, narrator)
    short = add_short(session, service)
    script = fixture_script()
    short.settings = {**short.settings, "language": "ur-en"}
    service.approve_script(session, short)
    artifacts = {}
    for section in script.sections:
        audio = tmp_path / f"{section.id}.wav"
        audio.write_bytes(b"uploaded speech fixture")
        artifacts[section.id] = {
            "uploaded_audio": str(audio),
            "uploaded_script_hash": fingerprint(section.text),
        }
    short.artifacts = artifacts
    service.produce(session, short)
    assert short.status == "review" and not narrator.calls
    script.sections[0].text = "بدلا ہوا متن with English"
    service.save_script(session, short, script)
    service.approve_script(session, short)
    with pytest.raises(ValueError, match="Replace narration"):
        service.produce(session, short)


def test_recovery_and_cancellation_preserve_artifacts(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    service = ShortService(tmp_path, Narrator())
    short = add_short(session, service)
    short.status = "producing"
    session.commit()
    assert run_next(session, service) == short.id
    saved = dict(short.artifacts)
    short.status = "cancel_requested"
    session.commit()
    assert run_next(session, service) is None
    assert short.status == "cancelled" and short.artifacts == saved


def test_narration_overrun_requires_script_adjustment(
    session: Session, tmp_path: Path, media: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ShortService(tmp_path, Narrator())
    short = add_short(session, service)
    monkeypatch.setattr(service_module, "audio_duration", lambda _: 40.0)
    with pytest.raises(ValueError, match="not truncated"):
        service.produce(session, short)
    assert short.status == "failed" and not short.output_path


def voicebox_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "healthy"})
    if request.url.path == "/profiles":
        return httpx.Response(200, json=[{"id": "voice", "name": "Narrator"}])
    if request.url.path == "/models/status":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"model_name": "qwen-tts-1.7B", "downloaded": True},
                    {"model_name": "unknown-engine", "downloaded": True},
                ]
            },
        )
    if request.url.path == "/generate":
        import json

        data = json.loads(request.content)
        assert data["profile_id"] == "voice" and data["personality"] is False
        return httpx.Response(200, json={"id": "generation-1", "status": "generating"})
    if request.url.path.endswith("export-audio"):
        return httpx.Response(200, content=b"RIFFfixture")
    return httpx.Response(200, json={"id": "generation-1", "status": "completed"})


def test_voicebox_http_capabilities_generation_retrieval_and_language_limits() -> None:
    client = httpx.Client(transport=httpx.MockTransport(voicebox_handler))
    provider = VoiceboxNarrationProvider("http://voicebox", client)
    config = ShortSettings(profile_id="voice")
    caps = provider.capabilities()
    assert len(caps["engines"]) == 1  # type: ignore[arg-type]
    assert provider.submit("English preview", config) == "generation-1"
    assert provider.status("generation-1") == "completed"
    assert provider.audio("generation-1") == b"RIFFfixture"
    with pytest.raises(VoiceboxError, match="Urdu"):
        provider.submit("اردو", config.model_copy(update={"language": "ur"}))
    with pytest.raises(VoiceboxError, match="delivery"):
        provider.submit("Preview", config.model_copy(update={"delivery": "Calm"}))
    with pytest.raises(VoiceboxError, match="profile"):
        provider.submit("Preview", config.model_copy(update={"profile_id": "missing"}))


def test_voicebox_offline_and_uninstalled_models_fail_before_generation() -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = VoiceboxNarrationProvider(
        "http://voicebox", httpx.Client(transport=httpx.MockTransport(offline))
    )
    with pytest.raises(VoiceboxError, match="unreachable"):
        provider.capabilities()

    def uninstalled(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models/status":
            return httpx.Response(
                200, json={"models": [{"model_name": "qwen-tts-1.7B", "downloaded": False}]}
            )
        assert request.method == "GET"
        return voicebox_handler(request)

    provider = VoiceboxNarrationProvider(
        "http://voicebox", httpx.Client(transport=httpx.MockTransport(uninstalled))
    )
    with pytest.raises(VoiceboxError, match="Install"):
        provider.submit("Preview", ShortSettings(profile_id="voice"))


def test_pronunciation_preserves_display_text_and_word_boundaries() -> None:
    text = "Use SQL with PostgreSQL. اردو English"
    assert speech_input(text, {"SQL": "sequel"}) == "Use sequel with PostgreSQL. اردو English"
    assert text.startswith("Use SQL")


def test_alignment_uses_measured_words_and_rejects_unmatched_speech() -> None:
    from clipper.domain.transcript import Segment, Transcript, Word
    from clipper.shorts.alignment import align_display_script

    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=0,
                text="Hello world",
                start_seconds=0,
                end_seconds=2,
                words=[
                    Word(text="Hello", start_seconds=0.3, end_seconds=0.7),
                    Word(text="world", start_seconds=1.2, end_seconds=1.8),
                ],
            )
        ],
    )
    cues = align_display_script("Hello world!", transcript, 2)
    assert cues[0].start_seconds == 0.3 and cues[0].end_seconds == 1.8
    assert cues[0].text == "Hello world!"
    with pytest.raises(ValueError, match="do not match"):
        align_display_script("Unrelated script", transcript, 2)


def test_unicode_phrase_captions_without_word_timestamps_are_not_empty() -> None:
    from clipper.captions.ass import serialize_ass
    from clipper.captions.models import CaptionCue
    from clipper.domain.editing_plan import CaptionConfig

    text = "اردو اور English text"
    output = serialize_ass([CaptionCue(0, 3, text)], CaptionConfig())
    assert text in output
    assert "MarginL, MarginR, MarginV" in output


def test_retry_budget_is_bounded(session: Session, tmp_path: Path, media: list[str]) -> None:
    service = ShortService(tmp_path, Narrator())
    short = add_short(session, service)
    service.produce(session, short)
    artifacts = dict(short.artifacts)
    entry = dict(artifacts["part-0"])
    Path(entry["audio"]).unlink()
    entry.pop("generation")
    entry["attempts"] = 2
    artifacts["part-0"] = entry
    short.artifacts = artifacts
    with pytest.raises(ValueError, match="budget exhausted"):
        service.produce(session, short)


def test_unconfirmed_upstream_cancel_is_distinct_from_reachcut_stop(
    session: Session, tmp_path: Path, media: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    narrator = Narrator()
    service = ShortService(tmp_path, narrator)
    short = add_short(session, service)

    def status(generation_id: str) -> str:
        short.status = "cancel_requested"
        session.commit()
        return "generating"

    def cancel(generation_id: str) -> bool:
        raise RuntimeError("Voicebox offline during cancellation")

    monkeypatch.setattr(narrator, "status", status)
    monkeypatch.setattr(narrator, "cancel", cancel)
    monkeypatch.setattr(service_module.time, "sleep", lambda _: None)
    service.produce(session, short)
    assert short.status == "cancelled"
    assert short.artifacts["part-0"]["cancel_requested"] is True
    assert short.artifacts["part-0"]["cancel_confirmed"] is False
    assert len(narrator.calls) == 1


def test_approved_revision_preserves_topic_format_and_default_destinations(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    import json
    from urllib.parse import parse_qs, urlsplit

    from clipper.persistence.models import RuntimeSetting

    service = ShortService(tmp_path, Narrator())
    short = add_short(session, service)
    short.settings = {**short.settings, "destinations": ["channel-1", "channel-2"]}
    service.produce(session, short)
    path = service.approve_video(session, short)
    assert parse_qs(urlsplit(path).query)["destinations"] == ["channel-1,channel-2"]
    revision = session.get(RuntimeSetting, f"informative-revision:{short.publication_project_id}")
    saved = json.loads(revision.value)
    assert saved["topic"] == short.topic and saved["settings"]["style"] == "demo"
    assert saved["script"] == short.script


def test_optional_narration_reuses_generated_scenes_without_starting_video_renderer(
    session: Session, tmp_path: Path, media: list[str]
) -> None:
    narrator = Narrator()
    service = ShortService(tmp_path / "shorts", narrator)
    short = service.create(
        session,
        "Original generated video",
        ShortSettings(duration=45, profile_id="voice", narration_mode="voicebox"),
        "optional-narration-key",
    )
    visual = tmp_path / "generated-scene.mp4"
    visual.write_bytes(b"saved-generated-scene")
    script = fixture_script()
    for section in script.sections:
        section.claims = []
        section.visual = "recording"
    short.artifacts = {
        "creation": {"video_id": "previously-generated-video"},
        **{
            section.id: {"asset": str(visual), "asset_kind": "recording", "asset_hash": "visual"}
            for section in script.sections
        },
    }
    service.save_script(session, short, script)
    service.approve_script(session, short)
    service.enqueue(session, short)
    service.produce(session, short)
    assert short.status == "review"
    assert len(narrator.calls) == 2 and len(media) == 2
    assert short.usage["actual_duration_seconds"] == 34
    assert visual.read_bytes() == b"saved-generated-scene"
    assert short.artifacts[script.sections[0].id]["asset"] == str(visual)
