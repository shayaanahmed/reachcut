from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1, SecondaryMediaKind, TransitionStyle
from clipper.rendering.framing import build_video_filter


@dataclass(frozen=True)
class FfmpegCommand:
    """An executable argument vector and its stable render metadata."""

    arguments: tuple[str, ...]
    width: int
    height: int
    duration_seconds: float


def build_ffmpeg_command(
    executable: str,
    source: Path,
    plan: EditingPlanV1,
    subtitles: Path,
    output: Path,
    *,
    preview: bool,
    asset_paths: Mapping[str, Path] | None = None,
) -> FfmpegCommand:
    """Build a shell-free FFmpeg command without running a process."""

    width, height = (360, 640) if preview else (1080, 1920)
    duration = plan.timeline_duration
    slices = plan.source_slices or [plan.source]
    resolved_assets = asset_paths or {}
    referenced_assets = [item for item in plan.secondary_media if item.asset_id in resolved_assets]
    input_indexes = {item.asset_id: index + 1 for index, item in enumerate(referenced_assets)}
    multi_slice = len(slices) > 1
    timeline_filter = ""
    video_input = "0:v"
    audio_map = "0:a?"
    if multi_slice:
        video_sources = "".join(f"[source_v{index}]" for index in range(len(slices)))
        audio_sources = "".join(f"[source_a{index}]" for index in range(len(slices)))
        source_audio = f"0:a:{plan.audio_track_index}"
        video_parts = [f"[0:v]split={len(slices)}{video_sources};"]
        audio_parts = [f"[{source_audio}]asplit={len(slices)}{audio_sources};"]
        for index, source_slice in enumerate(slices):
            slice_duration = source_slice.end_seconds - source_slice.start_seconds
            video_transition = ""
            audio_transition = ""
            if plan.transition_style is TransitionStyle.FADE:
                fade = min(plan.transition_duration_seconds, slice_duration / 3)
                if index > 0:
                    video_transition += f",fade=t=in:st=0:d={fade:.3f}"
                    audio_transition += f",afade=t=in:st=0:d={fade:.3f}"
                if index < len(slices) - 1:
                    fade_start = max(slice_duration - fade, 0)
                    video_transition += f",fade=t=out:st={fade_start:.3f}:d={fade:.3f}"
                    audio_transition += f",afade=t=out:st={fade_start:.3f}:d={fade:.3f}"
            video_parts.append(
                f"[source_v{index}]trim=start={source_slice.start_seconds:.3f}:"
                f"end={source_slice.end_seconds:.3f},setpts=PTS-STARTPTS"
                f"{video_transition}[cut_v{index}];"
            )
            audio_parts.append(
                f"[source_a{index}]atrim=start={source_slice.start_seconds:.3f}:"
                f"end={source_slice.end_seconds:.3f},asetpts=PTS-STARTPTS"
                f"{audio_transition}[cut_a{index}];"
            )
        cut_v = "".join(f"[cut_v{index}]" for index in range(len(slices)))
        cut_a = "".join(f"[cut_a{index}]" for index in range(len(slices)))
        timeline_filter = (
            "".join(video_parts)
            + f"{cut_v}concat=n={len(slices)}:v=1:a=0[timeline_v];"
            + "".join(audio_parts)
            + f"{cut_a}concat=n={len(slices)}:v=0:a=1[timeline_a];"
        )
        video_input = "timeline_v"
        audio_map = "[timeline_a]"
    video_filter = timeline_filter + build_video_filter(
        plan,
        subtitles,
        width,
        height,
        input_label=video_input,
        secondary_inputs=input_indexes,
    )
    seek_arguments: tuple[str, ...] = ()
    if not multi_slice:
        seek_arguments = ("-ss", f"{plan.source.start_seconds:.3f}")
    asset_arguments: list[str] = []
    for item in referenced_assets:
        if item.loop:
            asset_arguments.extend(["-stream_loop", "-1"])
        asset_arguments.extend(["-i", str(resolved_assets[item.asset_id])])

    audio_assets = [
        item
        for item in referenced_assets
        if item.kind in {SecondaryMediaKind.SOUND_EFFECT, SecondaryMediaKind.MUSIC}
        and not item.muted
    ]
    if audio_assets:
        base_audio = "timeline_a" if multi_slice else f"0:a:{plan.audio_track_index}"
        audio_labels = [f"[{base_audio}]"]
        audio_filters: list[str] = []
        for index, item in enumerate(audio_assets):
            input_index = input_indexes[item.asset_id]
            delay = round((item.start_seconds or 0) * 1000)
            clip_duration = (
                item.end_seconds - item.start_seconds
                if item.start_seconds is not None and item.end_seconds is not None
                else duration
            )
            label = f"asset_a{index}"
            audio_filters.append(
                f"[{input_index}:a]atrim=duration={clip_duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={item.volume_db:.1f}dB,adelay={delay}|{delay}[{label}]"
            )
            audio_labels.append(f"[{label}]")
        video_filter += ";" + ";".join(audio_filters)
        video_filter += (
            ";" + "".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=first[a]"
        )
        audio_map = "[a]"
    elif not multi_slice:
        audio_map = f"0:a:{plan.audio_track_index}?"
    arguments = (
        executable,
        "-hide_banner",
        "-nostdin",
        "-y",
        *seek_arguments,
        "-i",
        str(source),
        *asset_arguments,
        "-t",
        f"{duration:.3f}",
        "-filter_complex",
        video_filter,
        "-map",
        "[v]",
        "-map",
        audio_map,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.2",
        "-tag:v",
        "avc1",
        "-preset",
        "veryfast",
        "-crf",
        "25" if preview else "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output),
    )
    return FfmpegCommand(arguments, width, height, duration)
