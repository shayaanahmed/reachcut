from pathlib import Path

from clipper.domain.transcript import Segment, Transcript, Word
from clipper.persistence import Clip, Project, now_utc
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService


def test_artifact_service_keeps_caption_formats_synchronized(
    tmp_path: Path,
    make_plan,  # type: ignore[no-untyped-def]
) -> None:
    source = tmp_path / "source.mp4"
    project = Project(
        id="project-id",
        title="Fixture",
        original_filename=source.name,
        source_path=str(source),
        media_sha256="a" * 64,
        authorization_confirmed_at=now_utc(),
    )
    clip = Clip(id="clip-id", project_id=project.id, plan=make_plan(10, 40).model_dump(mode="json"))
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=1,
                text="A clear idea",
                start_seconds=10,
                end_seconds=11,
                words=[Word(text="Idea", start_seconds=10, end_seconds=11)],
            )
        ],
    )

    root = ClipArtifactService(ArtifactProvenance("speech:v1", "editor:v1")).write(
        project, clip, make_plan(10, 40), transcript
    )

    assert (root / "captions.srt").read_text().endswith("Idea\n")
    assert "Idea" in (root / "captions.vtt").read_text()
    assert "Idea" in (root / "captions.ass").read_text()
    assert '"transcription": "speech:v1"' in (root / "provenance.json").read_text()
