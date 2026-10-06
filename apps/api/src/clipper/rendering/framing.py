from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1, EffectType, SecondaryMediaKind


def build_video_filter(
    plan: EditingPlanV1,
    subtitles: Path,
    width: int,
    height: int,
    *,
    input_label: str = "0:v",
    secondary_inputs: Mapping[str, int] | None = None,
) -> str:
    """Build composition, tracking, secondary-media, effect, and subtitle filters."""

    inputs = secondary_inputs or {}
    parts: list[str] = []
    current = "base"
    gameplay = next(
        (
            item
            for item in plan.secondary_media
            if item.kind is SecondaryMediaKind.GAMEPLAY and item.asset_id in inputs
        ),
        None,
    )
    if gameplay:
        split_height = round(height * 0.54)
        game_height = height - split_height
        parts.append(
            _fill_filter(
                input_label,
                "primary_panel",
                width,
                split_height,
                _focus_expression(plan, "x"),
                _focus_expression(plan, "y"),
            )
        )
        parts.append(
            _fill_filter(
                f"{inputs[gameplay.asset_id]}:v",
                "game_panel",
                width,
                game_height,
                "0.5",
                "0.5",
                setpts_offset=0,
            )
        )
        parts.append("[primary_panel][game_panel]vstack=inputs=2[base]")
    else:
        parts.append(_primary_frame(plan, input_label, current, width, height))

    for index, item in enumerate(plan.secondary_media):
        input_index = inputs.get(item.asset_id)
        if input_index is None or item.kind not in {
            SecondaryMediaKind.BROLL,
            SecondaryMediaKind.REACTION,
        }:
            continue
        prepared = f"secondary_{index}"
        next_label = f"composite_{index}"
        if item.kind is SecondaryMediaKind.REACTION or item.placement == "pip":
            pip_width = round(width * 0.36)
            pip_height = round(height * 0.30)
            parts.append(
                _fit_filter(
                    f"{input_index}:v",
                    prepared,
                    pip_width,
                    pip_height,
                    setpts_offset=item.start_seconds or 0,
                )
            )
            enable = _enable(item.start_seconds, item.end_seconds)
            parts.append(
                f"[{current}][{prepared}]overlay=W-w-36:36:eof_action=pass{enable}[{next_label}]"
            )
        else:
            parts.append(
                _fill_filter(
                    f"{input_index}:v",
                    prepared,
                    width,
                    height,
                    "0.5",
                    "0.5",
                    setpts_offset=item.start_seconds or 0,
                )
            )
            enable = _enable(item.start_seconds, item.end_seconds)
            parts.append(
                f"[{current}][{prepared}]overlay=0:0:eof_action=pass{enable}[{next_label}]"
            )
        current = next_label

    zooms = [
        effect
        for effect in plan.effects
        if effect.type in {EffectType.PUNCH_ZOOM, EffectType.SLOW_ZOOM}
    ]
    if zooms:
        expression = "1"
        for effect in reversed(zooms):
            duration = float(effect.parameters.get("duration_seconds", 0.5))
            scale = float(effect.parameters.get("scale", 1.12))
            end = effect.time_seconds + duration
            expression = (
                f"if(between(in_time,{effect.time_seconds:.3f},{end:.3f}),{scale:.3f},{expression})"
            )
        parts.append(
            f"[{current}]zoompan=z='{expression}':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps=30[zoomed]"
        )
        current = "zoomed"

    if any(effect.type is EffectType.PROGRESS_BAR for effect in plan.effects):
        parts.append(
            f"[{current}]drawbox=x=0:y=ih-14:w='iw*min(t/{plan.timeline_duration:.3f},1)':"
            "h=14:color=0xD8FF42@0.95:t=fill[progressed]"
        )
        current = "progressed"

    escaped = str(subtitles).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    subtitle_filter = "ass" if subtitles.suffix.lower() == ".ass" else "subtitles"
    render_ass = (
        plan.caption_config.enabled
        or bool(plan.hook and plan.hook.render)
        or bool(plan.cta and plan.cta.render)
        or any(
            effect.type
            in {EffectType.SPEAKER_LABEL, EffectType.QUESTION_CARD, EffectType.QUOTE_CARD}
            for effect in plan.effects
        )
    )
    if render_ass:
        parts.append(f"[{current}]{subtitle_filter}='{escaped}'[v]")
    else:
        parts.append(f"[{current}]null[v]")
    return ";".join(parts)


def _primary_frame(
    plan: EditingPlanV1,
    input_label: str,
    output_label: str,
    width: int,
    height: int,
) -> str:
    if plan.frame_style == "center_crop":
        return _fill_filter(
            input_label,
            output_label,
            width,
            height,
            _focus_expression(plan, "x"),
            _focus_expression(plan, "y"),
        )
    return (
        f"[{input_label}]split=2[background][foreground];"
        f"[background]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},gblur=sigma=28,eq=brightness=-0.10:saturation=0.75[bg];"
        f"[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[{output_label}]"
    )


def _fill_filter(
    input_label: str,
    output_label: str,
    width: int,
    height: int,
    focus_x: str,
    focus_y: str,
    *,
    setpts_offset: float | None = None,
) -> str:
    timing = f"setpts=PTS-STARTPTS+{setpts_offset:.3f}/TB," if setpts_offset is not None else ""
    return (
        f"[{input_label}]{timing}scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:x='(in_w-out_w)*({focus_x})':"
        f"y='(in_h-out_h)*({focus_y})'[{output_label}]"
    )


def _fit_filter(
    input_label: str,
    output_label: str,
    width: int,
    height: int,
    *,
    setpts_offset: float | None = None,
) -> str:
    timing = f"setpts=PTS-STARTPTS+{setpts_offset:.3f}/TB," if setpts_offset is not None else ""
    return (
        f"[{input_label}]{timing}scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black[{output_label}]"
    )


def _focus_expression(plan: EditingPlanV1, axis: str) -> str:
    fallback = plan.crop_focus_x if axis == "x" else plan.crop_focus_y
    if not plan.tracking.enabled or not plan.tracking.keyframes:
        return f"{fallback:.4f}"
    points = plan.tracking.keyframes
    value = points[-1].center_x if axis == "x" else points[-1].center_y
    expression = f"{value:.4f}"
    for start, end in reversed(list(pairwise(points))):
        start_value = start.center_x if axis == "x" else start.center_y
        end_value = end.center_x if axis == "x" else end.center_y
        duration = max(end.time_seconds - start.time_seconds, 0.001)
        interpolated = (
            f"{start_value:.4f}+({end_value - start_value:.4f})*"
            f"(t-{start.time_seconds:.3f})/{duration:.3f}"
        )
        expression = (
            f"if(between(t\\,{start.time_seconds:.3f}\\,{end.time_seconds:.3f})\\,"
            f"{interpolated}\\,{expression})"
        )
    first_value = points[0].center_x if axis == "x" else points[0].center_y
    return f"if(lt(t\\,{points[0].time_seconds:.3f})\\,{first_value:.4f}\\,{expression})"


def _enable(start: float | None, end: float | None) -> str:
    if start is None or end is None:
        return ""
    return f":enable='between(t,{start:.3f},{end:.3f})'"
