from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.rendering import RenderRequest, VideoRenderer
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
    assert command.arguments[command.arguments.index("-pix_fmt") + 1] == "yuv420p"
    assert command.arguments[command.arguments.index("-tag:v") + 1] == "avc1"
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


def test_subtitles_can_be_disabled_without_changing_composition(make_plan) -> None:  # type: ignore[no-untyped-def]
    plan = make_plan().model_copy(
        update={"caption_config": make_plan().caption_config.model_copy(update={"enabled": False})}
    )
    command = build_ffmpeg_command(
        "ffmpeg",
        Path("source.mp4"),
        plan,
        Path("captions.ass"),
        Path("final.mp4"),
        preview=False,
    )

    video_filter = command.arguments[command.arguments.index("-filter_complex") + 1]
    assert "overlay=" in video_filter
    assert "captions.ass" not in video_filter


def test_multi_slice_render_trims_and_joins_video_and_audio(make_plan) -> None:  # type: ignore[no-untyped-def]
    payload = make_plan(start=10, end=50).model_dump(mode="json")
    payload.update(
        {
            "source_slices": [
                {"start_seconds": 10, "end_seconds": 20},
                {"start_seconds": 40, "end_seconds": 50},
            ],
            "frame_style": "center_crop",
            "crop_focus_x": 0.25,
            "crop_focus_y": 0.75,
        }
    )
    plan = EditingPlanV1.model_validate(payload)

    command = build_ffmpeg_command(
        "ffmpeg",
        Path("source.mp4"),
        plan,
        Path("captions.ass"),
        Path("final.mp4"),
        preview=False,
    )

    video_filter = command.arguments[command.arguments.index("-filter_complex") + 1]
    assert "trim=start=10.000:end=20.000" in video_filter
    assert "atrim=start=40.000:end=50.000" in video_filter
    assert "concat=n=2:v=1:a=0[timeline_v]" in video_filter
    assert "x='(in_w-out_w)*(0.2500)':y='(in_h-out_h)*(0.7500)'" in video_filter
    assert "-ss" not in command.arguments
    assert command.arguments[command.arguments.index("-map") + 3] == "[timeline_a]"
    assert command.duration_seconds == 20

    manifest = VideoRenderer._manifest(
        RenderRequest(
            Path("source.mp4"),
            plan,
            Path("captions.ass"),
            Path("final.mp4"),
            preview=False,
        ),
        command.arguments,
        command.width,
        command.height,
    )
    assert manifest["optimization_goal"] == "views"
    assert manifest["duration_seconds"] == 20
    assert manifest["source_slices"] == [
        {"start_seconds": 10.0, "end_seconds": 20.0},
        {"start_seconds": 40.0, "end_seconds": 50.0},
    ]


def test_gameplay_layout_and_audio_asset_are_composed(make_plan) -> None:  # type: ignore[no-untyped-def]
    payload = make_plan(start=0, end=20).model_dump(mode="json")
    payload["secondary_media"] = [
        {
            "asset_id": "game",
            "filename": "game.mp4",
            "kind": "gameplay",
            "muted": True,
            "loop": True,
            "placement": "bottom",
        },
        {
            "asset_id": "music",
            "filename": "music.mp3",
            "kind": "music",
            "muted": False,
            "loop": True,
            "volume_db": -20,
            "placement": "audio",
        },
    ]
    plan = EditingPlanV1.model_validate(payload)

    command = build_ffmpeg_command(
        "ffmpeg",
        Path("source.mp4"),
        plan,
        Path("captions.ass"),
        Path("final.mp4"),
        preview=False,
        asset_paths={"game": Path("game.mp4"), "music": Path("music.mp3")},
    )

    video_filter = command.arguments[command.arguments.index("-filter_complex") + 1]
    assert "[primary_panel][game_panel]vstack=inputs=2[base]" in video_filter
    assert "volume=-20.0dB" in video_filter
    assert "amix=inputs=2:duration=first[a]" in video_filter
    assert command.arguments.count("-stream_loop") == 2


def test_tracking_zoom_and_progress_filters_are_generated(make_plan) -> None:  # type: ignore[no-untyped-def]
    payload = make_plan(start=0, end=20).model_dump(mode="json")
    payload.update(
        {
            "frame_style": "center_crop",
            "tracking": {
                "enabled": True,
                "strategy": "face",
                "keyframes": [
                    {"time_seconds": 0, "center_x": 0.2, "center_y": 0.4},
                    {"time_seconds": 5, "center_x": 0.8, "center_y": 0.6},
                ],
            },
            "effects": [
                {"time_seconds": 1, "type": "punch_zoom", "parameters": {"scale": 1.15}},
                {"time_seconds": 0, "type": "progress_bar", "parameters": {}},
            ],
        }
    )
    plan = EditingPlanV1.model_validate(payload)

    command = build_ffmpeg_command(
        "ffmpeg", Path("source.mp4"), plan, Path("captions.ass"), Path("final.mp4"), preview=False
    )
    video_filter = command.arguments[command.arguments.index("-filter_complex") + 1]

    assert "between(t\\,0.000\\,5.000)" in video_filter
    assert "zoompan=" in video_filter
    assert "drawbox=" in video_filter
