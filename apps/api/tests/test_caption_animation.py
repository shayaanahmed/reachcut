from clipper.captions.animation import animated_events
from clipper.captions.models import CaptionCue
from clipper.domain.editing_plan import CaptionConfig
from clipper.domain.transcript import Word


def test_pop_animation_creates_one_event_per_word() -> None:
    words = (
        Word(text="One", start_seconds=0, end_seconds=0.3),
        Word(text="idea", start_seconds=0.3, end_seconds=0.8),
    )
    events = animated_events(CaptionCue(0, 0.8, "One idea", words), CaptionConfig(animation="pop"))

    assert [(start, end) for start, end, _ in events] == [(0, 0.3), (0.3, 0.8)]
    assert all("\\fscx118" in text for _, _, text in events)


def test_karaoke_animation_keeps_word_timing_tags() -> None:
    words = (
        Word(text="Timed", start_seconds=0, end_seconds=0.25),
        Word(text="words", start_seconds=0.25, end_seconds=0.75),
    )
    events = animated_events(
        CaptionCue(0, 0.75, "Timed words", words), CaptionConfig(animation="karaoke")
    )

    assert len(events) == 1
    assert "{\\kf25}Timed" in events[0][2]
    assert "{\\kf50}words" in events[0][2]
