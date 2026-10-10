from clipper.domain.transcript import Segment, Transcript
from clipper.editorial import suggest_clip_types


def test_transcript_suggests_advice_and_story_directions() -> None:
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=0,
                start_seconds=0,
                end_seconds=8,
                text="When I started, the best advice I learned was to ask for feedback.",
                words=[],
            )
        ],
    )

    suggestions = suggest_clip_types(transcript)
    types = {item.clip_type.value for item in suggestions}

    assert {"advice", "story", "highlight"} <= types
