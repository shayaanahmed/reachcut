import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.captions import serialize_ass
from clipper.domain.editing_plan import (
    CaptionConfig,
    SecondaryMediaKind,
    TimeRange,
    WatermarkConfig,
)
from clipper.media import MediaError, require_tool
from clipper.media.probe import probe_media
from clipper.persistence import Base
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService
from clipper.projects.clips import ClipService, ClipStyleUpdate
from clipper.projects.publishing_uploads import upload_publishing_video
from clipper.rendering import VideoRenderer


def test_watermark_is_escaped_and_visible_without_captions() -> None:
    ass = serialize_ass(
        [],
        CaptionConfig(enabled=False),
        watermark=WatermarkConfig(text=r"Brand {\pos(0,0)}", position="top_left", opacity=0.5),
        duration_seconds=2.5,
    )
    assert r"\an7\fs32\alpha&H80&" in ass
    assert r"Brand {\pos(0,0)}" not in ass
    assert "0:00:02.50,Watermark" in ass
    assert "Dialogue:" in ass


@pytest.mark.parametrize("has_audio", [False, True])
@pytest.mark.parametrize("multiple_cuts", [False, True])
def test_uploaded_clip_can_trim_watermark_and_mix_voiceover(
    tmp_path: Path, has_audio: bool, multiple_cuts: bool
) -> None:
    ffmpeg = require_tool("ffmpeg")
    source = tmp_path / "original.mp4"
    args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=180x320:r=15:d=2.4",
    ]
    if has_audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2.4"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)]
    subprocess.run(args, check=True, capture_output=True)
    narration = tmp_path / "narration.wav"
    with wave.open(str(narration), "wb") as track:
        track.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        track.writeframes(
            b"".join(
                struct.pack("<h", round(16000 * math.sin(2 * math.pi * 880 * n / 48000)))
                for n in range(14400)
            )
        )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    artifacts = ClipArtifactService(ArtifactProvenance("none", "none"))
    service = ClipService(artifacts, VideoRenderer(), projects_root=tmp_path / "projects")
    with Session(engine) as session, source.open("rb") as stream:
        project = upload_publishing_video(
            session, tmp_path / "projects", "Uploaded clip", source.name, stream, 1024**2, 60
        )
        assert project.transcript is None
        clip = project.clips[0]
        cuts = (
            (
                TimeRange(start_seconds=0.2, end_seconds=0.8),
                TimeRange(start_seconds=1.2, end_seconds=1.8),
            )
            if multiple_cuts
            else (TimeRange(start_seconds=0.2, end_seconds=1.4),)
        )
        watermark = WatermarkConfig(text="@My brand", position="bottom_right")
        service.update_style(
            session,
            clip.id,
            ClipStyleUpdate(
                caption_config=CaptionConfig(enabled=False),
                frame_style="center_crop",
                source_slices=cuts,
                watermark=watermark,
                original_audio_volume=0,
            ),
        )
        assert clip.final_path is None
        assert clip.plan["watermark"]["text"] == "@My brand"
        with narration.open("rb") as voice:
            service.add_secondary_media(
                session,
                clip.id,
                voice,
                narration.name,
                SecondaryMediaKind.VOICEOVER,
                0.2,
                0.8,
                "audio",
                volume_db=0,
            )
        asset = clip.plan["secondary_media"][0]
        assert asset["muted"] is False
        assert asset["loop"] is False
        preview = Path(clip.preview_path or "")
        metadata = probe_media(preview, 60)
        assert metadata["duration_seconds"] == pytest.approx(1.2, abs=0.1)
        assert metadata["has_audio"] is True
        assert metadata["width"] == 360
        decoded = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(preview),
                "-map",
                "0:a",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-f",
                "s16le",
                "-",
            ],
            check=True,
            capture_output=True,
        ).stdout
        samples = struct.unpack(f"<{len(decoded) // 2}h", decoded)
        assert max(abs(n) for n in samples[12000:20000]) > 1000
        assert max(abs(n) for n in samples[48000:52000]) < 100
        if has_audio and multiple_cuts:
            final = service.render_final(session, clip.id)
            assert probe_media(final, 60)["width"] == 1080
        service.remove_secondary_media(session, clip.id, asset["asset_id"])
        assert clip.plan["secondary_media"] == []
        assert clip.final_path is None
    engine.dispose()


def test_invalid_voiceover_leaves_no_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Metadata rejection happens before rendering and must not attach invalid media.
    from io import BytesIO

    import clipper.projects.clips as clips
    from clipper.domain.editing_plan import EditingPlanV1
    from clipper.persistence import Clip, Project, now_utc

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(
            id="project",
            title="Upload",
            original_filename="clip.mp4",
            source_path=str(tmp_path / "source" / "clip.mp4"),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
            status="complete",
            duration_seconds=2,
        )
        plan = EditingPlanV1.model_validate(
            {
                "source": {"start_seconds": 0, "end_seconds": 2},
                "scores": dict.fromkeys(
                    ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                ),
                "rationale": "Uploaded clip",
            }
        )
        clip = Clip(id="clip", project=project, plan=plan.model_dump(mode="json"))
        session.add(clip)
        session.commit()
        monkeypatch.setattr(
            clips, "media_metadata", lambda _: {"streams": [{"codec_type": "video"}]}
        )
        service = ClipService(None, None)  # type: ignore[arg-type]
        with pytest.raises(MediaError, match="audio stream"):
            service.add_secondary_media(
                session,
                clip.id,
                BytesIO(b"RIFFbad"),
                "voice.wav",
                SecondaryMediaKind.VOICEOVER,
                None,
                None,
                "audio",
            )
        assert clip.plan["secondary_media"] == []
        assert not list((tmp_path / "source" / "clips" / clip.id / "assets").glob("*"))
    engine.dispose()
