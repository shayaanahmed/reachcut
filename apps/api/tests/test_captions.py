from clipper.captions import (
    bilingual_cues,
    phrase_cues,
    retime_text,
    serialize_ass,
    serialize_srt,
    serialize_vtt,
)
from clipper.domain.editing_plan import CTA, CaptionConfig, Effect, Hook
from clipper.domain.transcript import Word


def test_breaks_caption_on_pause_and_word_limit() -> None:
    words = [
        Word(text="One", start_seconds=0, end_seconds=0.2),
        Word(text="clear", start_seconds=0.2, end_seconds=0.4),
        Word(text="idea", start_seconds=1.0, end_seconds=1.2),
        Word(text="ends", start_seconds=1.2, end_seconds=1.4),
    ]
    cues = phrase_cues(words, max_words=2)
    assert [cue.text for cue in cues] == ["One clear", "idea ends"]
    assert "00:00:00,000 --> 00:00:00,400" in serialize_srt(cues)
    assert serialize_vtt(cues).startswith("WEBVTT\n")


def test_ass_preserves_urdu_and_adds_word_highlighting() -> None:
    words = [
        Word(text="یہ", start_seconds=0, end_seconds=0.3),
        Word(text="اہم", start_seconds=0.3, end_seconds=0.7),
        Word(text="ہے۔", start_seconds=0.7, end_seconds=1.0),  # noqa: RUF001
    ]
    cues = phrase_cues(words)
    rendered = serialize_ass(
        cues,
        CaptionConfig(
            position="top",
            animation="pop",
            highlight_color="#D8FF42",
            highlighted_words=["اہم"],
        ),
    )
    assert "یہ اہم ہے۔" in cues[0].text  # noqa: RUF001
    assert "Alignment" in rendered
    assert ",8,72,72,180,1" in rendered
    assert "&H0042FFD8&" in rendered
    assert "\\fscx118" in rendered


def test_corrected_caption_text_keeps_the_original_timeline() -> None:
    words = [
        Word(text="wrong", start_seconds=1, end_seconds=2),
        Word(text="words", start_seconds=2, end_seconds=3),
    ]

    corrected = retime_text(words, "Corrected caption text")

    assert [word.text for word in corrected] == ["Corrected", "caption", "text"]
    assert corrected[0].start_seconds == 1
    assert corrected[-1].end_seconds == 3


def test_ass_can_render_hook_when_regular_captions_are_disabled() -> None:
    rendered = serialize_ass(
        [],
        CaptionConfig(enabled=False),
        hook=Hook(
            text="Why this matters",
            start_seconds=0,
            end_seconds=3,
            render=True,
        ),
    )

    assert ",Hook," in rendered
    assert "Why this matters" in rendered
    assert ",Caption," not in rendered.split("[Events]", 1)[1]


def test_ass_renders_bilingual_caption_cta_and_question_card() -> None:
    words = [Word(text="Hello", start_seconds=0, end_seconds=1)]
    translated = [Word(text="Hallo", start_seconds=0, end_seconds=1)]
    cues = bilingual_cues(phrase_cues(words), phrase_cues(translated))

    rendered = serialize_ass(
        cues,
        CaptionConfig(),
        cta=CTA(text="Follow", start_seconds=1, end_seconds=2, render=True),
        effects=[
            Effect(
                time_seconds=0,
                type="question_card",
                parameters={"text": "Did you know?", "duration_seconds": 1},
            )
        ],
    )

    assert r"\N{\fs42}Hallo" in rendered
    assert ",CTA," in rendered
    assert ",Card," in rendered
