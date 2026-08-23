"""Rendering public API: typed command construction plus explicit execution."""

from clipper.rendering.ffmpeg import FfmpegCommand, build_ffmpeg_command
from clipper.rendering.service import RenderRequest, VideoRenderer
from clipper.rendering.tracking import CropPoint, smooth_crop_path

__all__ = [
    "CropPoint",
    "FfmpegCommand",
    "RenderRequest",
    "VideoRenderer",
    "build_ffmpeg_command",
    "smooth_crop_path",
]
