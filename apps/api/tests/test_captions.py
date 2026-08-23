from clipper.captions import phrase_cues, serialize_ass, serialize_srt, serialize_vtt
from clipper.domain.editing_plan import CaptionConfig
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
