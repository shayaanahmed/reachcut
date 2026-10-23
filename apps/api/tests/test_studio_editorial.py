"""Regression checks for the failed public-facing video, not just successful API calls."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_short_studio import (
    SOURCE,
    client,
    legacy_frame,
    narrative_output,
    start_ideas,
    start_storyboard,
)

from clipper.providers.ollama_story import OllamaStoryDirector
from clipper.providers.studio_editor import source_excerpts
from clipper.providers.studio_narrative import copy_issues, write_narrative
from clipper.rendering.frames import render_frame, validate_frame_layout
from clipper.shorts.frames import FrameContent, FrameItem, frame_library, frame_sequences
from clipper.shorts.pacing import narrative_durations
from clipper.shorts.studio import StudioBrief

# Reuse the isolated app/database fixture, never the user's running database.
__all__ = ["client"]


def test_pacing_follows_the_story_and_preserves_the_target_duration() -> None:
    durations = narrative_durations(
        [
            "Where did your photos go?",
            "A tool helps organize your collection.",
            "Holiday photographs become dated folders that are easier to explore.",
            "Install the dependencies before selecting your folder and previewing changes.",
            "Check the result first.",
            "Which photographs would you find again?",
        ]
    )
    assert sum(durations) == pytest.approx(30)
    assert durations[0] == 3
    assert durations[3] > durations[4]
    assert max(durations) <= 6.5


def test_menu_and_badges_cannot_be_used_as_claim_evidence() -> None:
    text = (
        "Repository: sample/tool\nDescription: Analyze apps\n\n"
        "**English** · [German](docs/de.md) · [Spanish](docs/es.md)\n\n"
        '<div><a href="/">Join our community and find out more</a></div>\n\n'
        "See a feature in an app? This tool can inspect the app and explain how it works."
    )
    source = SOURCE.model_copy(update={"text": text})
    quotes = [quote for _, quote in source_excerpts([source]).values()]
    assert len(quotes) == 1
    assert quotes[0].startswith("See a feature")
    assert all(quote in text for quote in quotes)


def test_editor_rewrites_semantically_unsupported_claim_before_design(client: TestClient) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    draft["beats"][2]["narration"] = (
        "This tool also deletes all your duplicate pictures automatically."
    )
    director = OllamaStoryDirector("http://unused", "local")
    mock = Mock(
        side_effect=[
            draft,
            {"issues": ["Beat 3 invents automatic duplicate deletion."]},
            {
                "issues": [
                    {
                        "category": "unsupported_claim",
                        "message": "Beat 3 invents automatic duplicate deletion.",
                    }
                ]
            },
            narrative_output(),
            {"issues": []},
        ]
    )
    director._generate = mock
    story = write_narrative(
        director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, ""
    )
    assert mock.call_count == 5
    assert "duplicate deletion" in mock.call_args_list[3].args[0]
    assert "deletes" not in story.beats[2].narration


def test_critic_request_for_more_detail_does_not_force_rewrite(client: TestClient) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    sentence = (
        "Hold Ctrl, drag any file, and drop it on the format in the donut menu "
        "to convert instantly."
    )
    draft = narrative_output()
    draft["beats"][3]["narration"] = sentence
    allegation = (
        "Sentence in beat 4 ends before its thought is complete. It should clarify "
        "that the file gets converted immediately upon dropping. "
        "Offending words: 'to convert instantly.'"
    )
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(
        side_effect=[
            draft,
            {"text": sentence},  # The length pass may preserve this complete instruction.
            {"issues": [allegation]},
            {"issues": []},  # Verification dismisses the critic's extra-detail preference.
        ]
    )
    evidence = {"E1": (SOURCE.id, SOURCE.text + "\n" + sentence)}
    result = write_narrative(director, brief, brief.storylines[0], evidence, "")
    assert result.beats[3].narration == sentence
    assert director._generate.call_count == 4
    verification = director._generate.call_args_list[-1].args[0]
    assert allegation in verification
    assert "reference_texts" in verification
    assert "Imperatives are complete sentences" in verification
    assert not copy_issues([sentence])


def test_verified_unsupported_claim_still_blocks_after_retries(client: TestClient) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    draft["beats"][2]["narration"] = "This tool deletes all duplicate pictures automatically."
    issue = {"issues": ["Beat 3 invents automatic duplicate deletion."]}
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(
        side_effect=[
            draft,
            issue,
            {"issues": [{"category": "unsupported_claim", "message": issue["issues"][0]}]},
        ]
        * 3
    )
    with pytest.raises(ValueError, match="duplicate deletion"):
        write_narrative(director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, "")
    assert director._generate.call_count == 9


def test_repetitive_or_incomplete_story_cannot_pass_even_if_model_critic_misses_it(
    client: TestClient,
) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    draft["beats"][0]["narration"] = "You ask the tool to inspect the."
    draft["beats"][4]["narration"] = draft["beats"][1]["narration"]
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(side_effect=[draft, {"issues": []}] * 3)
    with pytest.raises(ValueError, match="editorial review"):
        write_narrative(director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, "")
    assert director._generate.call_count == 6
    assert copy_issues([draft["beats"][0]["narration"]])


@pytest.mark.parametrize("sequence", frame_sequences(), ids=lambda value: value.id)
def test_layout_reports_dense_copy_instead_of_overdrawing_card(
    sequence: object, tmp_path: Path
) -> None:
    frame = FrameContent(
        template="comparison",
        caption="A useful idea",
        eyebrow="Try this",
        title="What could you make?",
        items=[
            FrameItem(
                title="A clear start",
                body=(
                    "Explain the intricate relationship between data streams "
                    "and reconstruction algorithms"
                ),
            ),
            FrameItem(title="A real possibility", body="Build your own version"),
        ],
    )
    assert validate_frame_layout(frame, sequence)
    with pytest.raises(ValueError, match="does not fit"):
        render_frame(frame, sequence, tmp_path / "bad.png")
    assert not (tmp_path / "bad.png").exists()


def test_every_library_composition_fits_all_display_fonts() -> None:
    for sequence in frame_sequences():
        for definition in frame_library():
            assert not validate_frame_layout(definition.sample, sequence), (
                sequence.id,
                definition.id,
            )


def test_unreviewed_older_studio_cannot_be_produced_or_published(client: TestClient) -> None:
    from clipper.api.informative import short_service
    from clipper.projects.short_studio import SessionLocal

    detail = start_storyboard(client, start_ideas(client)["brief"])
    with SessionLocal() as session:
        short = short_service.get(session, detail["short"]["id"])
        artifacts = short.artifacts.copy()
        artifacts["series_episode"] = {
            **artifacts["series_episode"],
            "plan": {**artifacts["series_episode"]["plan"], "editorial_version": ""},
        }
        short.artifacts = artifacts
        session.commit()
        with pytest.raises(ValueError, match="Regenerate this older storyboard"):
            short_service.approve_script(session, short)
        short.status, short.output_path = "review", "/unused/old-video.mp4"
        with pytest.raises(ValueError, match="Regenerate this older storyboard"):
            short_service.approve_video(session, short)


def test_new_editorial_grammar_keeps_cardinality_without_truncating_sentences() -> None:
    import json

    from clipper.providers.ollama_story import _ollama_schema
    from clipper.providers.studio_narrative import Narrative

    grammar = _ollama_schema(
        Narrative.model_json_schema(),
        preserve_bounds=True,
        preserve_patterns=False,
        preserve_string_bounds=False,
    )
    assert "maxLength" not in json.dumps(grammar)
    assert grammar["properties"]["beats"]["minItems"] == 5
    assert grammar["properties"]["beats"]["maxItems"] == 6


def test_artwork_is_regenerated_when_local_vision_finds_an_unrelated_subject(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import copy

    from PIL import Image

    from clipper.api.informative import short_service
    from clipper.projects.short_studio import SessionLocal
    from clipper.shorts.series import EpisodeSnapshot

    detail = start_storyboard(client, start_ideas(client)["brief"])
    prompts = []

    def generate(model: str, prompt: str, output: Path, cancelled: object) -> Path:
        prompts.append(prompt)
        Image.new("RGB", (100, 180), "#88aaff").save(output)
        return output

    reviewer = Mock(side_effect=[["The portrait is unrelated to holiday photographs."], []])
    monkeypatch.setattr(short_service, "image_provider", lambda session: Mock(generate=generate))
    monkeypatch.setattr(short_service, "visual_reviewer", reviewer)
    with SessionLocal() as session:
        short = short_service.get(session, detail["short"]["id"])
        artifacts = copy.deepcopy(short.artifacts)
        snapshot = EpisodeSnapshot.model_validate(artifacts["series_episode"])
        snapshot.plan.visuals[0].frame = legacy_frame("photo")
        snapshot.plan.visuals[0].art_prompt = "A stack of holiday photographs on a table"
        (short_service.root / short.id).mkdir(parents=True, exist_ok=True)
        short_service.prepare_frame_asset(
            session, short, artifacts, snapshot, snapshot.plan.visuals[0]
        )
        assert len(prompts) == reviewer.call_count == 2
        assert "portrait is unrelated" in prompts[1]
        assert artifacts["scene_1"]["artwork_reviewed"] is True
        assert Path(artifacts["scene_1"]["asset"]).exists()


@pytest.mark.parametrize("visual_type", ["particles", "search", "folders", "typing", "browser"])
def test_concrete_illustrations_animate_and_fit(visual_type: str) -> None:
    from clipper.rendering.frames import FramePainter

    frame = (
        __import__("test_short_studio")
        .legacy_frame("demo")
        .model_copy(update={"visual_type": visual_type})
    )
    sequence = frame_sequences()[0]
    assert not validate_frame_layout(frame, sequence)
    painter = FramePainter(frame, sequence)
    assert painter.frame(0.5, 5).tobytes() != painter.frame(3, 5).tobytes()


def test_closing_scene_labels_are_corrected_against_the_approved_question(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from test_short_studio import editorial_response, scenes_output

    from clipper.providers.ollama_story import OllamaStoryDirector

    reviews = 0

    def generate(self: object, prompt: str, schema: object) -> dict:
        nonlocal reviews
        if schema.__name__ == "_VisualReview":
            reviews += 1
            return (
                {
                    "issues": [
                        {"scene": 5, "issue": "Choices must name photos the viewer could find."}
                    ]
                }
                if reviews == 1
                else {"issues": []}
            )
        if schema.__name__ == "CompactFrameCopy":
            data = json.loads(prompt[prompt.index("{") :])
            if not data.get("editorial_fix", "").startswith("Choices must"):
                return editorial_response(schema, prompt)
            assert data["approved_sentence"] == "Which photos would you want to find again?"
            assert data["editorial_fix"]
            return {
                "caption": "Which memories would you find?",
                "title": "Your next search",
                "eyebrow": "Your choice",
                "items": [
                    {"title": "Holiday photos", "body": ""},
                    {"title": "Family photos", "body": ""},
                    {"title": "Yearly photos", "body": ""},
                ],
            }
        if result := editorial_response(schema, prompt):
            return result
        return scenes_output()["scenes"][int(schema.__name__.split("_")[1])]

    brief = start_ideas(client)["brief"]
    monkeypatch.setattr(OllamaStoryDirector, "_generate", generate)
    detail = start_storyboard(client, brief)
    assert [
        item["title"] for item in detail["episode"]["plan"]["visuals"][-1]["frame"]["items"]
    ] == ["Holiday photos", "Family photos", "Yearly photos"]
    assert reviews == 1


def test_ollama_uses_supported_thinking_setting_for_installed_reasoning_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from clipper.providers.studio_narrative import EditorialReview

    payloads = []

    def post(url: str, **kwargs: object) -> httpx.Response:
        payloads.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"message": {"content": '{"issues": []}'}}
            if url.endswith("/chat")
            else {"response": '{"issues": []}'},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    OllamaStoryDirector("http://local", "gpt-oss:20b")._generate("Check the story", EditorialReview)
    OllamaStoryDirector("http://local", "qwen3:8b")._generate("Check the story", EditorialReview)
    assert payloads[0]["think"] == "low"
    assert payloads[1]["think"] is False


@pytest.mark.parametrize("defect", ["duplicate_caption", "unexplained_jargon"])
def test_future_studio_drafts_cannot_bypass_copy_safeguards(
    client: TestClient, defect: str
) -> None:
    import copy

    from clipper.api.informative import short_service
    from clipper.projects.short_studio import SessionLocal

    detail = start_storyboard(client, start_ideas(client)["brief"])
    with SessionLocal() as session:
        short = short_service.get(session, detail["short"]["id"])
        artifacts = copy.deepcopy(short.artifacts)
        frames = artifacts["series_episode"]["plan"]["visuals"]
        if defect == "duplicate_caption":
            frames[2]["frame"]["caption"] = frames[0]["frame"]["caption"]
            expected = "distinct caption"
        else:
            frames[2]["frame"]["items"][0]["body"] = "Read the compiled binary"
            expected = "Simplify the screen copy"
        short.artifacts = artifacts
        with pytest.raises(ValueError, match=expected):
            short_service.approve_script(session, short)


def test_reveal_shrinks_whole_words_instead_of_splitting_them() -> None:
    from clipper.rendering.frames import FramePainter

    frame = legacy_frame("reveal").model_copy(update={"title": "App Investigation"})
    painter = FramePainter(frame, frame_sequences()[1])
    draw_text = Mock(wraps=painter.text)
    painter.text = draw_text
    painter.frame(1, 5)
    rows = [
        call.args[3]
        for call in draw_text.call_args_list
        if len(call.args) >= 7 and call.args[6] == "mm" and call.args[2] < 494
    ]
    assert "Investigation" in rows
    assert "Investi" not in rows and "gation" not in rows
    assert not painter.layout_issues


def test_caption_shortening_cannot_reverse_an_approved_capability() -> None:
    from test_short_studio import narrative_output

    from clipper.providers.studio_narrative import Narrative, screen_story

    story = Narrative.model_validate(narrative_output())
    director = OllamaStoryDirector("http://unused", "local")
    generate = Mock(
        side_effect=[
            {"text": "Can't find those holiday photos?"},
            {"text": "**Sort your photos by date**"},
            {"text": "This tool cannot organize photographs"},
            {"text": "Your photos become dated folders"},
            {"text": "Choose a folder and preview changes"},
            {"text": "You could find your photographs again"},
        ]
    )
    director._generate = generate
    captions = screen_story(director, story)
    assert captions[2] == "Your photos become dated folders"
    assert not any("cannot" in caption for caption in captions)
    assert "**" not in " ".join(captions)
    assert any("reversed" in call.args[0] for call in generate.call_args_list)
    assert captions[-1] == story.beats[-1].narration


def test_toolbar_and_repeated_outcome_are_repaired_without_rewriting_valid_beats(
    client: TestClient,
) -> None:
    import copy

    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    lines = [
        "Want your files ready without repeated conversions?",
        "Filee helps convert your files between different formats.",
        "You could use a watch folder for incoming photos.",
        "Select Watch Folder from the toolbar to set up automatic conversion.",
        "Filee converts files dropped into a watch folder automatically.",
        "Which files would you convert first?",
    ]
    for beat, line in zip(draft["beats"], lines, strict=True):
        beat["narration"] = line
    fixed = copy.deepcopy(draft)
    fixed["beats"][0]["narration"] = "An unrelated rewrite that must not replace the valid hook."
    fixed["beats"][3]["narration"] = (
        "A configured watch folder automatically converts the files dropped into it."
    )
    fixed["beats"][4]["narration"] = "The documented photo formats include PNG and JPG."
    issues = {
        "issues": [
            "Beat 4 invents the toolbar location for Watch Folder.",
            "Beat 2 and beat 5 repeat the same conversion outcome.",
        ]
    }
    director = OllamaStoryDirector("http://unused", "local")
    verified = {
        "issues": [
            {"category": "unsupported_claim", "message": issues["issues"][0]},
            {"category": "repetition", "message": issues["issues"][1]},
        ]
    }
    director._generate = Mock(side_effect=[draft, issues, verified, fixed, {"issues": []}])
    progress = Mock()
    result = write_narrative(
        director,
        brief,
        brief.storylines[0],
        {
            "E1": (
                SOURCE.id,
                "Filee converts files between formats. Configured watch folders automatically "
                "convert files dropped into them. Supported photo formats include PNG and JPG.",
            )
        },
        "",
        progress,
    )
    assert result.beats[0].narration == lines[0]
    assert "toolbar" not in result.beats[3].narration
    assert result.beats[4].narration == fixed["beats"][4]["narration"]
    assert any("Correcting source details" in call.args[0] for call in progress.call_args_list)


def test_persistent_repetition_returns_editable_story_instead_of_failing(
    client: TestClient,
) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    message = (
        "Sentence in beat 3 merely repeats the same information as beat 2. "
        "For example, drag a file and drop it onto a format to convert it."
    )
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(
        side_effect=[
            draft,
            {"issues": [message]},
            {"issues": [{"category": "repetition", "message": message}]},
        ]
        * 3
    )
    result = write_narrative(
        director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, ""
    )
    assert result.editorial_notes == [message]
    assert director._generate.call_count == 9


def test_repetition_does_not_hide_simultaneous_factual_error(client: TestClient) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(
        side_effect=[
            draft,
            {"issues": ["Beat 3 repeats; beat 4 invents a toolbar."]},
            {
                "issues": [
                    {"category": "repetition", "message": "Beat 3 repeats beat 2."},
                    {"category": "unsupported_claim", "message": "Beat 4 invents a toolbar."},
                ]
            },
        ]
        * 3
    )
    with pytest.raises(ValueError, match="invents a toolbar"):
        write_narrative(director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, "")


def test_exact_repetition_is_also_an_editing_note(client: TestClient) -> None:
    brief = StudioBrief.model_validate(start_ideas(client)["brief"])
    draft = narrative_output()
    draft["beats"][2]["narration"] = draft["beats"][1]["narration"]
    director = OllamaStoryDirector("http://unused", "local")
    director._generate = Mock(side_effect=[draft, {"issues": []}] * 3)
    result = write_narrative(
        director, brief, brief.storylines[0], {"E1": (SOURCE.id, SOURCE.text)}, ""
    )
    assert "repeat" in result.editorial_notes[0]
    assert not copy_issues([b.narration for b in result.beats], include_repetition=False)
