"""Source-grounded story choices, durable retries and the actual selected-frame renderer."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import cv2
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.api import informative
from clipper.main import app
from clipper.persistence import get_session
from clipper.persistence.models import Base
from clipper.projects import short_studio as jobs
from clipper.providers.github_repository import GitHubRepositoryProvider
from clipper.providers.ollama_story import OllamaStoryDirector, _ollama_schema
from clipper.providers.studio_editor import OllamaStudioEditor, source_excerpts
from clipper.rendering.frames import (
    FramePainter,
    render_frame,
    render_frame_video,
    validate_frame_layout,
)
from clipper.rendering.series import silent_audio
from clipper.shorts.contracts import Evidence, script_issues
from clipper.shorts.frames import FrameContent, frame_library, frame_sequences
from clipper.shorts.series import EpisodeSnapshot
from clipper.shorts.studio import IdeaRequest


def legacy_frame(kind: str) -> FrameContent:
    import json

    records = json.loads((Path(__file__).parent / "fixtures/legacy_scene_frames.json").read_text())
    return FrameContent.model_validate(next(f["sample"] for f in records if f["id"] == kind))


SOURCE = Evidence(
    id="repo-docs",
    url="https://github.com/example/photos",
    title="Photo sorter README",
    text=(
        "This tool organizes photographs into folders by date. Install the documented "
        "dependencies, choose a folder, and preview the proposed changes before applying them."
    ),
    kind="primary",
)


def ideas_output() -> dict:
    return {
        "analysis": (
            "This tool organizes photographs into folders by date. "
            "It needs the documented dependencies and your photo folder."
        ),
        "storylines": [
            {
                "title": f"Your photo folder, sorted {i}",
                "hook": "Can you find last summer's photos?",
                "focus": (
                    "Begin with a messy photo folder, explain sorting by date and show "
                    "the possibility of finding pictures more easily."
                ),
                "payoff": "You could organize a photo collection by date.",
                "source_id": SOURCE.id,
                "example": "Sort a holiday photo collection by date.",
                "steps": [
                    {"title": "Install the dependencies", "body": "Follow the project setup guide"},
                    {"title": "Choose a folder", "body": "Select your holiday photographs"},
                    {
                        "title": "Preview the changes",
                        "body": "Check before applying the new folders",
                    },
                ],
                "prerequisite": "Install the documented dependencies first.",
            }
            for i in range(3)
        ],
    }


def scenes_output(sequence_id: str = "html-d189115ff61aab9d") -> dict:
    sequence = next(s for s in frame_sequences() if s.id == sequence_id)
    definitions = {f.id: f.sample for f in frame_library()}
    scenes = []
    for i, kind in enumerate(sequence.frames):
        sample = definitions[kind]
        scenes.append(
            {
                "caption": f"Your photos, easier to find again {i}",
                "eyebrow": "A useful discovery",
                "title": "Organize your photo collection",
                "items": [{"title": item.title, "body": item.body} for item in sample.items],
                "query": "summer photos" if kind == "demo" else "",
                "art_prompt": (
                    "Portrait photograph of a hand holding a stack of holiday photos "
                    "on a cream table, no text, no logos."
                )
                if kind in {"photo", "poll"}
                else "",
                "narration": "This tool organizes photographs into folders by date.",
                "excerpt_id": "E1" if i in {1, 2, 3, 4} else "",
            }
        )
    return {"scenes": scenes}


def narrative_output() -> dict:
    lines = [
        ("Where did those holiday photos go?", "Find that holiday", "Missing memories"),
        (
            "This tool organizes photographs into folders by date.",
            "Your photos, sorted by date",
            "Photo sorter",
        ),
        (
            "Your holiday collection could become a set of dated folders.",
            "A home for each holiday",
            "Holiday folders",
        ),
        (
            "Install the dependencies, then choose your photo folder.",
            "Choose your photo folder",
            "Get started",
        ),
        (
            "Preview the proposed changes before applying them to your collection.",
            "Check before you apply",
            "Preview first",
        ),
        (
            "Which photos would you want to find again?",
            "Which memories would you find?",
            "Your next search",
        ),
    ]
    return {
        "beats": [
            {
                "narration": line,
                "caption": caption,
                "title": title,
                "visual": "Holiday photographs move into clearly illustrated dated folders.",
                "excerpt_id": "E1" if i in {1, 2, 3, 4} else "",
                "choices": ["Holiday photos", "Family photos"] if i == 5 else [],
            }
            for i, (line, caption, title) in enumerate(lines)
        ]
    }


def editorial_response(schema: object, prompt: str = "") -> dict | None:
    if schema.__name__ == "CaptionLine":
        import json

        data = json.loads(
            prompt.split("Source data:\n")[1].split("\nCorrect these exact defects:")[0]
        )
        index = data["beat_number"] - 1
        beat = narrative_output()["beats"][index]
        return {"text": beat["narration"] if index == 0 else beat["caption"]}
    if schema.__name__ == "CompactFrameCopy" and prompt:
        import json

        data = json.loads(prompt[prompt.index("{") :])
        return data.get("draft", data.get("rejected_copy"))
    if schema.__name__ == "CompleteVideoStory":
        result = narrative_output()
        count = schema.model_json_schema()["properties"]["beats"]["maxItems"]
        if count == 5:
            result["beats"].pop(3)
        return result
    if schema.__name__ in {"EditorialReview", "VerifiedEditorialReview", "_VisualReview"}:
        return {"issues": []}
    return None


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'studio.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    def session() -> Generator[Session]:
        with Session(engine, expire_on_commit=False) as value:
            yield value

    app.dependency_overrides[get_session] = session
    monkeypatch.setattr(jobs, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    monkeypatch.setattr(informative.short_service, "root", tmp_path / "videos")
    monkeypatch.setattr(informative.short_service, "visual_reviewer", Mock(return_value=[]))
    monkeypatch.setattr(
        GitHubRepositoryProvider,
        "research",
        Mock(return_value=("example/photos", SOURCE.url, [SOURCE])),
    )
    monkeypatch.setattr(jobs, "research_tech_tricks", lambda offset: ([SOURCE], []))

    def generate(self: object, prompt: str, schema: object) -> dict:
        if "GroundedIdeas" in str(schema):
            return ideas_output()
        if response := editorial_response(schema, prompt):
            return response
        index = int(schema.__name__.split("_")[1])
        return scenes_output()["scenes"][index]

    monkeypatch.setattr(OllamaStoryDirector, "_generate", generate)
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()
    engine.dispose()


def start_ideas(client: TestClient, category: str = "github", key: str = "ideas-request") -> dict:
    response = client.post(
        "/api/short-studio/ideas",
        json={
            "category": category,
            "repo_url": SOURCE.url if category == "github" else "",
            "request_key": key,
        },
    )
    assert response.status_code == 200, response.text
    result = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert result["status"] == "ready", result
    return result


def start_storyboard(client: TestClient, brief: dict, key: str = "plan-request") -> dict:
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": brief["storylines"][0]["id"],
            "sequence_id": "html-d189115ff61aab9d",
            "theme": "paper",
            "request_key": key,
        },
    )
    assert response.status_code == 200, response.text
    result = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert result["status"] == "ready", result
    return client.get("/api/content-series/episodes/" + result["short_id"]).json()


@pytest.mark.parametrize("category", ["github", "tech-tricks"])
def test_both_paths_need_no_saved_niche_and_preserve_selected_story(
    client: TestClient, category: str
) -> None:
    job = start_ideas(client, category)
    assert len(job["brief"]["storylines"]) == 3
    detail = start_storyboard(client, job["brief"])
    snapshot = EpisodeSnapshot.model_validate(detail["episode"])
    assert [v.frame.template for v in snapshot.plan.visuals if v.frame] == frame_sequences()[
        0
    ].frames
    assert sum(v.frame.duration_seconds for v in snapshot.plan.visuals if v.frame) == pytest.approx(
        30
    )
    assert snapshot.style.frame_sequence is not None
    assert snapshot.style.frame_sequence.theme == "paper"
    assert snapshot.angle.id == job["brief"]["storylines"][0]["id"]
    assert not script_issues(snapshot.plan.script, snapshot.brief.sources, require_claims=False)
    assert detail["short"]["settings"]["narration_mode"] == "none"
    for visual in snapshot.plan.visuals:
        response = client.get(
            f"/api/content-series/episodes/{detail['short']['id']}/visuals/{visual.section_id}"
        )
        assert response.status_code == 200 and response.content.startswith(b"\x89PNG")


def test_invalid_repo_or_category_fails_before_ollama(client: TestClient) -> None:
    for payload in [
        {"category": "github", "repo_url": "https://127.0.0.1/private"},
        {"category": "history"},
        {"category": "github"},
        {"category": "tech-tricks", "repo_url": SOURCE.url},
    ]:
        assert (
            client.post(
                "/api/short-studio/ideas", json={**payload, "request_key": "invalid-request"}
            ).status_code
            == 422
        )
    assert client.get("/api/content-series").status_code == 404
    assert client.post("/api/content-series", json={"name": "History"}).status_code == 404


def test_requests_are_idempotent_and_cannot_change_inputs(client: TestClient) -> None:
    first = start_ideas(client)
    second = start_ideas(client)
    assert first["id"] == second["id"]
    changed = client.post(
        "/api/short-studio/ideas",
        json={
            "category": "github",
            "repo_url": "https://github.com/other/repo",
            "request_key": "ideas-request",
        },
    )
    assert changed.status_code == 422
    one = start_storyboard(client, first["brief"])
    two = start_storyboard(client, first["brief"])
    assert one["short"]["id"] == two["short"]["id"]
    assert len(client.get("/api/shorts").json()) == 1


def test_failure_retry_reuses_research_and_does_not_invent_fallbacks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = OllamaStudioEditor.ideas
    monkeypatch.setattr(OllamaStudioEditor, "ideas", Mock(side_effect=ValueError("Ollama offline")))
    payload = {"category": "github", "repo_url": SOURCE.url, "request_key": "retry-ideas"}
    response = client.post("/api/short-studio/ideas", json=payload).json()
    failed = client.get("/api/short-studio/jobs/" + response["id"]).json()
    assert failed["status"] == "failed" and failed["brief"] is None
    monkeypatch.setattr(OllamaStudioEditor, "ideas", real)
    retry = client.post("/api/short-studio/ideas", json=payload).json()
    done = client.get("/api/short-studio/jobs/" + retry["id"]).json()
    assert done["status"] == "ready"
    assert GitHubRepositoryProvider.research.call_count == 1


def test_library_has_real_distinct_compositions_and_misspelled_ids_fail(
    client: TestClient, tmp_path: Path
) -> None:
    frames = client.get("/api/short-studio/frames").json()
    assert len(frames) == 25
    assert {f["volume"] for f in frames} == {2}
    assert not {"photo", "steps", "headline", "flow", "terminal"} & {f["id"] for f in frames}
    assert client.get("/api/short-studio/frames/headline/player").status_code == 404
    player = client.get(f"/api/short-studio/frames/{frames[0]['id']}/player")
    assert player.status_code == 200 and "Everyone keeps" in player.text
    assert "default-src 'none'" in player.headers["content-security-policy"]
    assert len(client.get("/api/short-studio/sequences").json()) == 5
    for frame in frames:
        r = client.get(f"/api/short-studio/frames/{frame['id']}/preview")
        assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    assert client.get("/api/short-studio/frames/unknown/preview").status_code == 404
    assert (
        client.get("/api/short-studio/frames/photo/preview?sequence_id=unknown").status_code == 404
    )


@pytest.mark.parametrize(
    "sequence_id",
    [sequence.id for sequence in frame_sequences()],
)
def test_faceless_sequences_fit_and_new_compositions_have_motion(sequence_id: str) -> None:
    sequence = next(s for s in frame_sequences() if s.id == sequence_id)
    definitions = {frame.id: frame.sample for frame in frame_library()}
    assert len(sequence.frames) == len(sequence.durations) == 5
    assert 20 <= sum(sequence.durations) <= 30
    for kind in sequence.frames:
        content = definitions[kind]
        assert not validate_frame_layout(content, sequence)
        from clipper.rendering.html_frames import HTMLFramePainter

        with HTMLFramePainter(content, sequence) as painter:
            first = painter.frame(0.1, 5)
            later = painter.frame(3, 5)
        assert ImageChops.difference(first, later).getbbox() is not None


@pytest.mark.parametrize(
    "sequence_id",
    [sequence.id for sequence in frame_sequences()],
)
def test_unknown_excerpt_is_corrected_and_quotes_are_hydrated_server_side(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, sequence_id: str
) -> None:
    brief = start_ideas(client)["brief"]
    from clipper.shorts.studio import StudioBrief

    first = True

    def response(prompt: str, schema: object) -> dict:
        nonlocal first
        if schema.__name__ == "CompleteVideoStory" and first:
            story = narrative_output()
            story["beats"].pop(3)
            story["beats"][2]["excerpt_id"] = "E999"
            first = False
            return story
        if result := editorial_response(schema, prompt):
            return result
        index = int(schema.__name__.split("_")[1])
        return scenes_output(sequence_id)["scenes"][index]

    generate = Mock(side_effect=response)
    editor = OllamaStudioEditor("http://ollama", "text")
    monkeypatch.setattr(editor.director, "_generate", generate)
    b = StudioBrief.model_validate(brief)
    sequence = next(s for s in frame_sequences() if s.id == sequence_id)
    result = editor.plan(b, b.storylines[0], sequence)
    assert result.visuals[2].quote == SOURCE.text
    schema = next(
        call.args[1].model_json_schema()
        for call in generate.call_args_list
        if call.args[1].__name__ == f"FrameSelection_4_{sequence.frames[4]}"
    )
    grammar = _ollama_schema(schema, preserve_bounds=True)
    assert grammar["properties"]["items"]["maxItems"] == (
        2 if sequence.frames[4] == "story-poll" else 3
    )
    assert source_excerpts([SOURCE])["E1"] == (SOURCE.id, SOURCE.text)


def test_unsupported_demo_quantity_is_corrected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipper.shorts.studio import StudioBrief

    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    first_demo = True

    def response(prompt: str, schema: object) -> dict:
        nonlocal first_demo
        if result := editorial_response(schema, prompt):
            return result
        index = int(schema.__name__.split("_")[1])
        scene = scenes_output()["scenes"][index]
        if index == 3 and first_demo:
            scene["items"][0]["title"] = "5 seconds"
            first_demo = False
        return scene

    editor = OllamaStudioEditor("http://ollama", "text")
    generate = Mock(side_effect=response)
    monkeypatch.setattr(editor.director, "_generate", generate)
    plan = editor.plan(brief, brief.storylines[0], frame_sequences()[0])
    assert any(
        "unsupported quantity: 5 seconds" in call.args[0] for call in generate.call_args_list
    )
    assert plan.visuals[3].frame.items[0].title == "Question"


def test_storyboard_failure_keeps_previous_short_and_story_choices(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = start_ideas(client)["brief"]
    original = start_storyboard(client, brief)
    monkeypatch.setattr(
        OllamaStudioEditor, "plan", Mock(side_effect=ValueError("Retry storyboard"))
    )
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": "story-1",
            "sequence_id": "html-d189115ff61aab9d",
            "request_key": "new-failed-plan",
        },
    ).json()
    assert client.get("/api/short-studio/jobs/" + response["id"]).json()["status"] == "failed"
    assert client.get("/api/content-series/episodes/" + original["short"]["id"]).status_code == 200
    assert (
        client.get("/api/short-studio/briefs/" + brief["id"]).json()["storylines"]
        == brief["storylines"]
    )


def test_restart_marks_interrupted_job_retryable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with jobs.SessionLocal() as session:
        job, _ = jobs.create_job(
            session,
            IdeaRequest(category="github", repo_url=SOURCE.url, request_key="interrupted-key"),
        )
        job.worker = "old-process"
        jobs.save_job(session, job)
        value = jobs.get_job(session, job.id)
        assert value.status == "failed" and "restart" in value.error


def test_storyboard_scene_renderer_animates_at_30fps(tmp_path: Path) -> None:
    frame = legacy_frame("steps")
    painter = FramePainter(frame, frame_sequences()[0])
    assert painter.frame(0.1, 2).tobytes() != painter.frame(1.8, 2).tobytes()
    png = render_frame(frame, frame_sequences()[0], tmp_path / "frame.png")
    assert Image.open(png).size == (1080, 1920)
    audio = tmp_path / "silent.wav"
    silent_audio(audio, 1)
    output = render_frame_video(frame, frame_sequences()[0], audio, tmp_path / "sample.mp4", 1)
    video = cv2.VideoCapture(str(output))
    assert (video.get(cv2.CAP_PROP_FRAME_WIDTH), video.get(cv2.CAP_PROP_FRAME_HEIGHT)) == (
        1080,
        1920,
    )
    assert video.get(cv2.CAP_PROP_FPS) == 30
    assert video.get(cv2.CAP_PROP_FRAME_COUNT) == 30
    video.release()


@pytest.mark.parametrize("final_review_required", [False, True])
def test_production_uses_selected_frames_and_exact_silent_timings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    final_review_required: bool,
) -> None:
    import shutil
    import wave

    import clipper.shorts.service as service_module

    brief = start_ideas(client)["brief"]
    detail = start_storyboard(client, brief)
    calls = []
    images = []

    def image(model: str, prompt: str, output: Path, cancelled: object) -> Path:
        images.append(prompt)
        Image.new("RGB", (768, 1360), "#448899").save(output)
        return output

    def render(
        content: object, sequence: object, audio: Path, output: Path, duration: float, *args: object
    ) -> Path:
        assert sequence.theme == "paper"
        calls.append((content.template, duration))
        output.write_bytes(b"frame fixture")
        output.with_suffix(".ass").write_text("[Events]\n")
        return output

    def duration(path: Path) -> float:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()

    def assemble(paths: list[Path], output: Path) -> Path:
        output.write_bytes(b"assembled fixture")
        return output

    def music(source: Path, output: Path, duration: float) -> Path:
        shutil.copy2(source, output)
        return output

    monkeypatch.setattr(informative.short_service, "image_provider", lambda _: Mock(generate=image))
    monkeypatch.setattr(service_module, "audio_duration", duration)
    monkeypatch.setattr(service_module, "render_frame_video", render)
    monkeypatch.setattr(
        service_module,
        "render_section",
        Mock(side_effect=AssertionError("New frames must not use the retired compositor")),
    )
    monkeypatch.setattr(service_module, "assemble_sections", assemble)
    monkeypatch.setattr(service_module, "add_original_music", music)
    monkeypatch.setattr(service_module, "inspect_render", lambda *args: [])
    with jobs.SessionLocal() as session:
        short = informative.short_service.get(session, detail["short"]["id"])
        if final_review_required:
            from clipper.shorts.video_review import FinalVideoAssessment

            short.artifacts = {
                **short.artifacts,
                "studio": {
                    **short.artifacts["studio"],
                    "final_review_required": True,
                },
            }
            reviewer = Mock(
                return_value=FinalVideoAssessment(
                    publishable=True,
                    summary="Clear, readable scenes",
                    hook_score=80,
                    clarity_score=80,
                    pacing_score=80,
                    shareability_score=75,
                )
            )
            monkeypatch.setattr(informative.short_service, "final_reviewer", reviewer)
        informative.short_service.approve_script(session, short)
        informative.short_service.produce(session, short)
        assert short.status == "review", short.error
        assert short.usage["actual_duration_seconds"] == pytest.approx(30)
        assert calls == list(
            zip(
                frame_sequences()[0].frames,
                [v["frame"]["duration_seconds"] for v in detail["episode"]["plan"]["visuals"]],
                strict=True,
            )
        )
        assert len(images) == 0
        assert all(short.artifacts[f"scene_{i + 1}"]["frame_generated"] for i in range(5))
        informative.short_service.produce(session, short)
        assert len(calls) == 5 and len(images) == 0
        if final_review_required:
            assert reviewer.call_count == 2
            assert short.artifacts["final_video_review"]["status"] == "passed"


def test_dense_caption_is_shortened_without_changing_narration_or_evidence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipper.shorts.studio import StudioBrief

    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    scene = scenes_output()["scenes"][2]
    original_narration = narrative_output()["beats"][2]["narration"]
    scene["caption"] = "This tool helps you sort all of your photos into date folders"

    def generate(prompt: str, schema: object) -> dict:
        if schema.__name__ == "CompleteVideoStory":
            story = narrative_output()
            story["beats"].pop(3)
            story["beats"][2]["caption"] = scene["caption"]
            return story
        if schema.__name__ == "CompactFrameCopy":
            import json

            data = json.loads(prompt[prompt.index("{") :])
            draft = data.get("draft", data.get("rejected_copy"))
            if draft["caption"] != scene["caption"]:
                return editorial_response(schema, prompt)
            return {
                "caption": "Your photos, easier to find again",
                "title": scene["title"],
                "eyebrow": scene["eyebrow"],
                "items": scene["items"],
            }
        if result := editorial_response(schema, prompt):
            return result
        index = int(schema.__name__.split("_")[1])
        return scene if index == 2 else scenes_output()["scenes"][index]

    editor = OllamaStudioEditor("http://ollama", "text")
    mock = Mock(side_effect=generate)
    monkeypatch.setattr(editor.director, "_generate", mock)
    plan = editor.plan(brief, brief.storylines[0], frame_sequences()[0])
    assert plan.visuals[2].frame.caption == "A home for each holiday"
    assert plan.script.sections[2].text == original_narration
    assert plan.visuals[2].quote == SOURCE.text


def test_local_grammar_omits_problematic_word_patterns_but_keeps_size_bounds() -> None:
    from clipper.providers.studio_editor import _ScreenCopy

    grammar = _ollama_schema(
        _ScreenCopy.model_json_schema(), preserve_bounds=True, preserve_patterns=False
    )
    import json

    text = json.dumps(grammar)
    assert '"pattern"' not in text
    assert '"maxLength"' in text and '"maxItems"' in text


def test_research_page_title_does_not_include_later_svg_icon_titles() -> None:
    from clipper.providers.short_research import _Text

    parser = _Text()
    parser.feed(
        "<html><head><title>Using the clipboard</title></head>"
        "<body><svg><title>Privacy icon</title></svg>"
        "<main>Useful guide text</main></body></html>"
    )
    assert parser.title == "Using the clipboard"


def test_manual_frames_and_reframe_preserve_narration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise the workflow with local layout checks isolated from browser startup.
    monkeypatch.setattr("clipper.rendering.frames.validate_frame_layout", lambda *args: [])
    brief = start_ideas(client)["brief"]
    original = start_storyboard(client, brief)
    chosen = list(frame_sequences()[0].frames)
    chosen[0] = frame_sequences()[1].frames[0]
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": brief["storylines"][0]["id"],
            "sequence_id": "html-d189115ff61aab9d",
            "frames": chosen,
            "frame_mode": "manual",
            "source_short_id": original["short"]["id"],
            "request_key": "reframe-request",
        },
    )
    assert response.status_code == 200, response.text
    job = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert job["status"] == "ready", job
    revised = client.get("/api/content-series/episodes/" + job["short_id"]).json()
    assert revised["short"]["id"] != original["short"]["id"]
    assert revised["episode"]["style"]["frame_sequence"]["frames"] == chosen
    assert [s["text"] for s in revised["short"]["script"]["sections"]] == [
        s["text"] for s in original["short"]["script"]["sections"]
    ]
    assert client.get("/api/content-series/episodes/" + original["short"]["id"]).json() == original


def test_ai_frames_are_chosen_and_saved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clipper.rendering.frames.validate_frame_layout", lambda *args: [])
    from clipper.providers.studio_editor import OllamaStudioEditor

    chosen = list(frame_sequences()[0].frames)
    chosen[0] = frame_sequences()[1].frames[0]
    choose = Mock(return_value=chosen)
    monkeypatch.setattr(OllamaStudioEditor, "choose_frames", choose)
    brief = start_ideas(client)["brief"]
    response = client.post(
        "/api/short-studio/storyboards",
        json={
            "brief_id": brief["id"],
            "storyline_id": brief["storylines"][0]["id"],
            "sequence_id": "html-d189115ff61aab9d",
            "frame_mode": "ai",
            "request_key": "ai-frames-request",
        },
    )
    job = client.get("/api/short-studio/jobs/" + response.json()["id"]).json()
    assert job["status"] == "ready", job
    detail = client.get("/api/content-series/episodes/" + job["short_id"]).json()
    assert detail["episode"]["style"]["frame_sequence"]["frames"] == chosen
    choose.assert_called_once()


def test_delete_short_removes_only_its_files_and_rejects_active_render(client: TestClient) -> None:
    from clipper.shorts.contracts import ShortSettings

    with jobs.SessionLocal() as session:
        short = informative.short_service.create(
            session, "Delete this video", ShortSettings(), "delete-test"
        )
        short_id = short.id
        directory = informative.short_service.root / short_id
        directory.mkdir(parents=True)
        (directory / "master.mp4").write_bytes(b"test")
        neighbor = informative.short_service.root / "other-video.mp4"
        neighbor.write_bytes(b"keep")
        short.status = "producing"
        session.commit()
    assert client.delete("/api/shorts/" + short_id).status_code == 422
    assert directory.exists()
    with jobs.SessionLocal() as session:
        short = informative.short_service.get(session, short_id)
        short.status = "review"
        session.commit()
    assert client.delete("/api/shorts/" + short_id).status_code == 204
    assert client.get("/api/shorts/" + short_id).status_code == 404
    assert not directory.exists()
    assert neighbor.read_bytes() == b"keep"


def test_editorial_notes_survive_storyboard_and_do_not_block_approval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipper.providers.studio_narrative import Narrative

    monkeypatch.setattr("clipper.rendering.frames.validate_frame_layout", lambda *args: [])
    monkeypatch.setattr("clipper.shorts.service.validate_frame_layout", lambda *args: [])
    draft = narrative_output()
    draft["beats"].pop(3)
    narrative = Narrative.model_validate(draft)
    narrative.beats[2].narration = narrative.beats[1].narration
    narrative.editorial_notes = ["Beat 3 repeats beat 2; consider a different example."]
    monkeypatch.setattr(
        "clipper.providers.studio_editor.write_narrative", lambda *args, **kwargs: narrative
    )
    detail = start_storyboard(client, start_ideas(client)["brief"])
    assert detail["episode"]["plan"]["editorial_notes"] == narrative.editorial_notes
    response = client.post("/api/shorts/" + detail["short"]["id"] + "/script/approve")
    assert response.status_code == 200, response.text


def test_bento_prose_fits_cards_without_splitting_words_or_covering_caption() -> None:
    from clipper.rendering.html_frames import HTMLFramePainter
    from clipper.shorts.frames import FrameItem

    content = FrameContent(
        template="bento-stats",
        caption="Learn Electron features with visibility",
        eyebrow="REA Analysis",
        title="Limitations",
        items=[
            FrameItem(title="System Code", body="Shows basic instructions"),
            FrameItem(title="App Code", body="Reveals parts and connections"),
            FrameItem(title="Electron Apps", body="Maps how parts work together"),
        ],
    )
    with HTMLFramePainter(content, frame_sequences()[0]) as painter:
        assert not painter.issues()
        assert painter.page.eval_on_selector_all(
            "[data-fit-box]",
            "nodes => nodes.every(n => getComputedStyle(n).overflowWrap === 'normal' "
            "&& parseFloat(getComputedStyle(n).fontSize) >= 14)",
        )
        painter.page.eval_on_selector(
            "[data-fit-box]", "n => n.textContent = 'Unbreakablylongword'.repeat(20)"
        )
        assert painter.issues()
