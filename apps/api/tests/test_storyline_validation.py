"""Optional prerequisites and planning notes must not use screen-copy constraints."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from test_short_studio import SOURCE, ideas_output

from clipper.providers.studio_editor import OllamaStudioEditor


@pytest.mark.parametrize("value", [None, "", "None", "none.", " N/A ", "Not specified", "unknown"])
def test_unspecified_prerequisites_do_not_reject_a_storyline(value: object) -> None:
    output = ideas_output()
    output["storylines"][0]["prerequisite"] = value
    editor = OllamaStudioEditor("http://ollama", "gpt-oss:20b")
    generate = Mock(return_value=output)
    editor.director._generate = generate
    _, stories = editor.ideas("github", "example/photos", [SOURCE])
    assert len(stories) == 3
    assert stories[0].prerequisite == ""
    generate.assert_called_once()


def test_missing_or_short_documented_prerequisite_is_valid() -> None:
    output = ideas_output()
    output["storylines"][0].pop("prerequisite")
    output["storylines"][1]["prerequisite"] = "Git"
    editor = OllamaStudioEditor("http://ollama", "gpt-oss:20b")
    editor.director._generate = Mock(return_value=output)
    _, stories = editor.ideas("github", "example/photos", [SOURCE])
    assert stories[0].prerequisite == ""
    assert stories[1].prerequisite == "Git"


def test_planning_steps_preserve_valid_notes_longer_than_screen_labels() -> None:
    output = ideas_output()
    note = (
        "Write short descriptions of the documented workflow, including how to preview "
        "proposed changes before applying them to the selected photo folder."
    )
    output["storylines"][0]["steps"][1]["body"] = note
    editor = OllamaStudioEditor("http://ollama", "gpt-oss:20b")
    editor.director._generate = Mock(return_value=output)
    _, stories = editor.ideas("github", "example/photos", [SOURCE])
    assert 90 < len(note) <= 200
    assert stories[0].steps[1].body == note


def test_public_planning_limit_still_requires_correction_instead_of_clipping() -> None:
    invalid = ideas_output()
    invalid["storylines"][0]["steps"][0]["body"] = "x" * 201
    corrected = deepcopy(invalid)
    corrected["storylines"][0]["steps"][0]["body"] = "Follow the documented setup guide"
    editor = OllamaStudioEditor("http://ollama", "gpt-oss:20b")
    generate = Mock(side_effect=[invalid, corrected])
    editor.director._generate = generate
    _, stories = editor.ideas("github", "example/photos", [SOURCE])
    assert generate.call_count == 2
    assert stories[0].steps[0].body == corrected["storylines"][0]["steps"][0]["body"]
    assert "200 characters" in generate.call_args_list[1].args[0]
