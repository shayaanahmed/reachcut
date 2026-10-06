"""Rendering public API: typed command construction plus explicit execution."""

from clipper.rendering.ffmpeg import FfmpegCommand, build_ffmpeg_command
from clipper.rendering.service import RenderRequest, VideoRenderer
from clipper.rendering.tracking import (
    CropPoint,
    VisualAnalysis,
    VisualTrackingProvider,
    keyframes_for_clip,
    smooth_crop_path,
    strategy_for_mode,
)

__all__ = [
    "CropPoint",
    "FfmpegCommand",
    "RenderRequest",
    "VideoRenderer",
    "VisualAnalysis",
    "VisualTrackingProvider",
    "build_ffmpeg_command",
    "keyframes_for_clip",
    "smooth_crop_path",
    "strategy_for_mode",
]
