from pathlib import Path

import pytest

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Segment, Transcript, Word
from clipper.persistence import Clip, Project, now_utc
from clipper.projects.artifacts import (
    ArtifactPathError,
    ArtifactProvenance,
    ClipArtifactService,
    resolve_clip_artifact,
)


def test_clip_artifact_resolution_requires_the_expected_owned_regular_file(
    tmp_path: Path,
    make_plan,  # type: ignore[no-untyped-def]
) -> None:
    projects_root = tmp_path / "projects"
    source = projects_root / "project-id" / "source" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    project = Project(
        id="project-id",
        title="Fixture",
        original_filename=source.name,
        source_path=str(source),
        media_sha256="a" * 64,
        authorization_confirmed_at=now_utc(),
    )
    clip = Clip(
        id="clip-id",
        project_id=project.id,
        plan=make_plan(10, 40).model_dump(mode="json"),
    )
    artifact = source.parent / "clips" / clip.id / "preview.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"preview")

    assert (
        resolve_clip_artifact(projects_root, project, clip, str(artifact), "preview.mp4")
        == artifact
    )

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"private")
    with pytest.raises(ArtifactPathError, match="outside its owned directory"):
        resolve_clip_artifact(projects_root, project, clip, str(outside), "preview.mp4")

    artifact.unlink()
    artifact.symlink_to(outside)
    with pytest.raises(ArtifactPathError, match="symbolic link"):
        resolve_clip_artifact(projects_root, project, clip, str(artifact), "preview.mp4")


def test_clip_artifact_resolution_rejects_a_symlinked_source_directory(
    tmp_path: Path,
    make_plan,  # type: ignore[no-untyped-def]
) -> None:
    projects_root = tmp_path / "projects"
    project_root = projects_root / "project-id"
    outside_source = tmp_path / "outside-source"
    outside_source.mkdir()
    source = outside_source / "source.mp4"
    source.write_bytes(b"source")
    project_root.mkdir(parents=True)
    (project_root / "source").symlink_to(outside_source, target_is_directory=True)
    project = Project(
        id="project-id",
        title="Fixture",
        original_filename=source.name,
        source_path=str(project_root / "source" / source.name),
        media_sha256="a" * 64,
        authorization_confirmed_at=now_utc(),
    )
    clip = Clip(
        id="clip-id",
        project_id=project.id,
        plan=make_plan(10, 40).model_dump(mode="json"),
    )
    artifact = outside_source / "clips" / clip.id / "preview.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"preview")

    with pytest.raises(ArtifactPathError, match="outside its owned directory"):
        resolve_clip_artifact(projects_root, project, clip, str(artifact), "preview.mp4")


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


def test_artifacts_join_source_slices_and_apply_caption_corrections(
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
    payload = make_plan(0, 12).model_dump(mode="json")
    payload["source_slices"] = [
        {"start_seconds": 0, "end_seconds": 2},
        {"start_seconds": 10, "end_seconds": 12},
    ]
    payload["caption_config"]["text_override"] = "First corrected second"
    plan = EditingPlanV1.model_validate(payload)
    clip = Clip(id="clip-id", project_id=project.id, plan=plan.model_dump(mode="json"))
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=1,
                text="First gap second",
                start_seconds=0,
                end_seconds=12,
                words=[
                    Word(text="First", start_seconds=0, end_seconds=1),
                    Word(text="gap", start_seconds=5, end_seconds=6),
                    Word(text="second", start_seconds=10, end_seconds=11),
                ],
            )
        ],
    )

    root = ClipArtifactService(ArtifactProvenance("speech:v1", "editor:v1")).write(
        project, clip, plan, transcript
    )

    captions = (root / "captions.srt").read_text()
    assert "First corrected second" in captions
    assert "gap" not in captions
    assert "00:00:03,000" in captions
