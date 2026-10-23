"""Editorial repair must explain the violated bounds without clipping copy."""

import json
from unittest.mock import Mock

import pytest

from clipper.providers.ollama_story import OllamaStoryDirector
from clipper.providers.studio_narrative import ConciseSentence, structured_response


def test_overlong_narration_is_rewritten_with_the_rejected_text_and_exact_limit() -> None:
    rejected = {"text": "You could " + "organize photographs " * 12}
    corrected = {"text": "You could organize photographs into dated folders."}
    director = OllamaStoryDirector("http://ollama", "qwen3:8b")
    generate = Mock(side_effect=[rejected, corrected])
    director._generate = generate

    assert structured_response(director, "Condense this sentence", ConciseSentence) == corrected
    retry = generate.call_args_list[1].args[0]
    assert "text: String should have at most 140 characters" in retry
    assert json.dumps(rejected) in retry
    assert "Preserve factual qualifiers" in retry


def test_failed_editorial_repair_keeps_the_actual_diagnostic() -> None:
    director = OllamaStoryDirector("http://ollama", "qwen3:8b")
    director._generate = Mock(return_value={"text": "x" * 141})
    with pytest.raises(ValueError, match="text: String should have at most 140 characters"):
        structured_response(director, "Condense this sentence", ConciseSentence)


def test_multilingual_evidence_remains_readable_and_available_to_the_writer() -> None:
    from clipper.providers.ollama_story import prompt_json
    from clipper.providers.studio_editor import source_excerpts
    from clipper.shorts.contracts import Evidence

    text = (
        "这个工具可以读取网页内容和视频字幕。帮助你的人工智能助手搜索公开资料。"
        "部分平台需要用户登录配置。安装默认只检查环境。"
    )
    source = Evidence(id="readme", url="https://github.com/example/tool", title="README", text=text)
    excerpts = source_excerpts([source])
    assert list(excerpts.values()) == [("readme", text)]
    encoded = prompt_json({"evidence": text})
    assert text in encoded
    assert "\\u" not in encoded
    assert json.loads(encoded) == {"evidence": text}


@pytest.mark.parametrize("is_complete", [True, False])
def test_grammar_allegation_is_checked_without_source_or_critic_bias(is_complete: bool) -> None:
    from test_short_studio import SOURCE, ideas_output, narrative_output

    from clipper.providers.studio_editor import OllamaStudioEditor
    from clipper.providers.studio_narrative import write_narrative
    from clipper.shorts.studio import Storyline, StudioBrief

    draft = narrative_output()
    sentence = "You can read public pages without logging in or installing tools."
    if not is_complete:
        sentence = "Your AI can put."
    draft["beats"][3]["narration"] = sentence
    stories = [Storyline(id=f"story-{i}", **s) for i, s in enumerate(ideas_output()["storylines"])]
    brief = StudioBrief(
        category="github",
        subject="tool",
        repo_url=SOURCE.url,
        context="",
        analysis="Source facts",
        sources=[SOURCE],
        storylines=stories,
    )
    editor = OllamaStudioEditor("http://ollama", "qwen3:8b")
    allegation = "Beat 4 lacks a verb object and needs another result."
    generate = Mock(
        side_effect=[
            draft,
            {"issues": [allegation]},
            {"issues": [{"category": "incomplete_sentence", "message": allegation}]},
            # Unrelated allegations must not replace the original beat-4 finding.
            {"incomplete_beats": [1, 5] if is_complete else [4]},
        ]
        * (1 if is_complete else 3)
    )
    editor.director._generate = generate
    if is_complete:
        result = write_narrative(
            editor.director, brief, stories[0], {"E1": (SOURCE.id, SOURCE.text)}, ""
        )
        assert result.beats[3].narration == sentence
    else:
        with pytest.raises(ValueError, match="grammatically incomplete"):
            write_narrative(
                editor.director, brief, stories[0], {"E1": (SOURCE.id, SOURCE.text)}, ""
            )
    independent_check = generate.call_args_list[-1].args[0]
    assert sentence in independent_check
    assert draft["beats"][0]["narration"] not in independent_check
    assert SOURCE.text not in independent_check
    assert allegation not in independent_check


def test_documented_repository_name_is_preserved_without_allowing_other_jargon() -> None:
    from clipper.providers.studio_narrative import audience_terms

    assert audience_terms("Agent-Reach", proper_names=("Agent-Reach",)) == []
    assert audience_terms("Agent-Reach uses agents", proper_names=("Agent-Reach",)) == ["agents"]
    assert audience_terms("Agent-Reach uses MCP", proper_names=("Agent-Reach",)) == ["MCP"]
