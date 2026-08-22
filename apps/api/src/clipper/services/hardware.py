from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HardwareProfile:
    name: str
    transcription_device: str
    transcription_compute_type: str
    video_encoder: str
    optional_models_enabled: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_profile() -> HardwareProfile:
    machine = platform.machine().lower()
    if platform.system() == "Darwin" and machine == "arm64":
        memory_gb = _mac_memory_gb()
        return HardwareProfile(
            "apple_silicon_32gb" if memory_gb >= 24 else "apple_silicon_16gb",
            "cpu",
            "int8",
            "h264_videotoolbox" if _encoder_available("h264_videotoolbox") else "libx264",
            memory_gb >= 24,
        )
    if shutil.which("nvidia-smi"):
        return HardwareProfile("nvidia_8gb", "cuda", "int8_float16", "h264_nvenc", False)
    return HardwareProfile("cpu_low_memory", "cpu", "int8", "libx264", False)


def _mac_memory_gb() -> int:
    sysctl = shutil.which("sysctl")
    if not sysctl:
        return 0
    result = subprocess.run(
        [sysctl, "-n", "hw.memsize"], capture_output=True, text=True, check=False
    )
    return int(result.stdout.strip() or 0) // 1024**3


def _encoder_available(name: str) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    return name in result.stdout
