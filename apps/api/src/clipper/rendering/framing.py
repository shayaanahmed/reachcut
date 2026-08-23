from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1


def build_video_filter(plan: EditingPlanV1, subtitles: Path, width: int, height: int) -> str:
    """Build only the composition filter graph for a vertical render."""

    escaped = str(subtitles).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    subtitle_filter = "ass" if subtitles.suffix.lower() == ".ass" else "subtitles"
    if plan.frame_style == "center_crop":
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},{subtitle_filter}='{escaped}'[v]"
        )
    return (
        f"[0:v]split=2[background][foreground];"
        f"[background]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},gblur=sigma=28,eq=brightness=-0.10:saturation=0.75[bg];"
        f"[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{subtitle_filter}='{escaped}'[v]"
    )
