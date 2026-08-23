from pathlib import Path

from clipper.rendering.ffmpeg import build_ffmpeg_command


def test_preview_command_is_built_without_execution(make_plan) -> None:  # type: ignore[no-untyped-def]
    command = build_ffmpeg_command(
        "/usr/bin/ffmpeg",
        Path("source.mp4"),
        make_plan(),
        Path("captions.ass"),
        Path("preview.mp4"),
        preview=True,
    )

    assert (command.width, command.height) == (360, 640)
    assert command.arguments[0] == "/usr/bin/ffmpeg"
    assert "-filter_complex" in command.arguments
    assert "gblur=sigma=28" in command.arguments[command.arguments.index("-filter_complex") + 1]


def test_center_crop_framing_is_owned_by_filter_builder(make_plan) -> None:  # type: ignore[no-untyped-def]
    plan = make_plan().model_copy(update={"frame_style": "center_crop"})
    command = build_ffmpeg_command(
        "ffmpeg",
        Path("source.mp4"),
        plan,
        Path("captions.ass"),
        Path("final.mp4"),
        preview=False,
    )

    video_filter = command.arguments[command.arguments.index("-filter_complex") + 1]
    assert "crop=1080:1920" in video_filter
    assert "gblur" not in video_filter
