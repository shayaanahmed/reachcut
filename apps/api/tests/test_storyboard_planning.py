from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from clipper.api import video_generation
from clipper.generation import StoryPlanningRequest
from clipper.main import app
from clipper.providers.ollama_story import OllamaStoryDirector

STORY = (
    "A hydraulic press slowly crushes a tower of rainbow chalk cubes. Use a fixed camera, "
    "realistic workshop lighting, and a clear view of the colorful fragments scattering "
    "across the metal platform."
)


def object_plan() -> dict[str, object]:
    return {
        "title": "Rainbow Chalk Crush",
        "logline": "A hydraulic press crushes rainbow chalk into colorful fragments.",
        "visual_style": "Fixed-camera realistic industrial workshop footage",
        "negative_prompt": "text, logos, flicker, invented people, camera movement",
        "characters": [],
        "scenes": [
            {
                "index": index,
                "title": f"Chalk compression {index}",
                "story_beat": "The hydraulic press slowly compresses the rainbow chalk tower.",
                "visual_prompt": (
                    "A fixed camera observes a metallic hydraulic press slowly lowering onto a "
                    "tower of rainbow chalk cubes in a realistically lit industrial workshop."
                ),
                "character_ids": [],
                "camera_motion": "static",
                "duration_seconds": 5,
                "seed": 4400 + index,
            }
            for index in range(1, 3)
        ],
    }


def numeric_object_plan() -> dict[str, object]:
    result = object_plan()
    result["characters"] = [
        {
            "id": "0",
            "name": "Hydraulic Press",
            "role": "Object",
            "appearance_anchor": "Heavy rectangular metallic hydraulic press with industrial bolts",
            "wardrobe_anchor": "industrial machinery without clothing",
            "voice_anchor": "None",
        }
    ]
    return result


@pytest.mark.parametrize(
    "failure", ["numeric_character", "unknown_reference", "scene_count", "logline"]
)
def test_storyboard_repairs_invalid_structure_without_weakening_validation(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = numeric_object_plan() if failure == "numeric_character" else object_plan()
    if failure == "unknown_reference":
        invalid["scenes"][0]["character_ids"] = ["unknown"]  # type: ignore[index]
    elif failure == "scene_count":
        invalid["scenes"] = invalid["scenes"][:1]  # type: ignore[index]
    elif failure == "logline":
        invalid["logline"] = "Chalk"
    valid = object_plan()
    prompts: list[str] = []
    director = OllamaStoryDirector("http://ollama", "text")

    def generate(prompt: str, _: object) -> dict[str, object]:
        prompts.append(prompt)
        return deepcopy(invalid if len(prompts) == 1 else valid)

    monkeypatch.setattr(director, "_generate", generate)
    result = director.plan(
        StoryPlanningRequest(STORY, "documentary_realism", "9:16", 10, shot_mode="story")
    )
    assert result.characters == []
    assert len(result.scenes) == 2
    assert result.duration_seconds == 10
    assert all(scene.character_ids == [] for scene in result.scenes)
    assert len(prompts) == 2
    assert "For an object-only scene, set characters to []" in prompts[0]
    expected = {
        "numeric_character": "characters.0.id: String should match pattern",
        "unknown_reference": "plan: Value error, scene 1 references unknown characters",
        "scene_count": "Expected 2 scenes (shot 1: 5s, shot 2: 5s); received 1",
        "logline": "logline: String should have at least 10 characters",
    }
    assert expected[failure] in prompts[1]


def test_failed_storyboard_repair_is_reported_as_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    director = OllamaStoryDirector("http://ollama", "text")
    calls: list[str] = []

    def generate(prompt: str, _: object) -> dict[str, object]:
        calls.append(prompt)
        return numeric_object_plan()

    monkeypatch.setattr(director, "_generate", generate)
    monkeypatch.setattr(video_generation, "_director", lambda _: director)
    with TestClient(app) as client:
        response = client.post(
            "/api/video-generation/plan",
            json={
                "story": STORY,
                "template": "documentary_realism",
                "target_duration_seconds": 10,
            },
        )
    assert response.status_code == 502
    assert "invalid storyboard after retrying" in response.json()["detail"]
    assert len(calls) == 2


def test_continuous_action_uses_native_ten_second_shots_and_no_narrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = object_plan()
    for scene in raw["scenes"]:  # type: ignore[union-attr]
        scene["camera_motion"] = "dolly_in"
        scene["narration"] = "Pressure builds, tension rises."
        scene["story_beat"] = "The press contacts the chalk tower. " * 30
    director = OllamaStoryDirector("http://ollama", "text")
    monkeypatch.setattr(director, "_generate", lambda *_: deepcopy(raw))
    result = director.plan(StoryPlanningRequest(STORY, "documentary_realism", "9:16", 20))
    assert [scene.duration_seconds for scene in result.scenes] == [10, 10]
    assert all(scene.narration == "" and scene.camera_motion == "static" for scene in result.scenes)
    assert result.scenes[0].story_beat == "The press contacts the chalk tower."
    assert result.scenes[0].visual_prompt == raw["scenes"][0]["visual_prompt"]  # type: ignore[index]


def test_requested_narration_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = object_plan()
    raw["scenes"][0]["narration"] = "Watch the chalk crumble."  # type: ignore[index]
    director = OllamaStoryDirector("http://ollama", "text")
    monkeypatch.setattr(director, "_generate", lambda *_: deepcopy(raw))
    result = director.plan(
        StoryPlanningRequest(
            STORY,
            "documentary_realism",
            "9:16",
            20,
            narration_enabled=True,
        )
    )
    assert result.scenes[0].narration == "Watch the chalk crumble."


@pytest.mark.parametrize(
    "duration,mode,expected",
    [
        (10, "auto", [10]),
        (20, "auto", [10, 10]),
        (15, "continuous", [10, 5]),
        (20, "story", [5, 5, 5, 5]),
    ],
)
def test_continuous_shot_lengths_preserve_requested_duration(duration, mode, expected) -> None:
    from clipper.generation.shot_planning import shot_durations

    assert (
        shot_durations(
            StoryPlanningRequest(
                STORY,
                "documentary_realism",
                "9:16",
                duration,
                shot_mode=mode,
            )
        )
        == expected
    )
