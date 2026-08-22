from clipper.domain.transcript import Word
from clipper.services.captions import phrase_cues, serialize_srt, serialize_vtt


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
