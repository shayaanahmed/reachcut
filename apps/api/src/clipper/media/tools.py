import shutil
from pathlib import Path

from clipper.media.errors import MediaError


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        executable = _bundled_tool(name)
    if not executable:
        raise MediaError(f"{name} is required but was not found on PATH; run pnpm doctor")
    return executable


def _bundled_tool(name: str) -> str | None:
    """Resolve the repository's pinned media binaries when they are installed."""

    repository = Path(__file__).resolve().parents[5]
    if name == "ffprobe":
        import platform

        system = {"Darwin": "darwin", "Linux": "linux", "Windows": "win32"}.get(
            platform.system(), ""
        )
        arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x64", "AMD64": "x64"}.get(
            platform.machine(), ""
        )
        candidate = (
            repository
            / "node_modules"
            / "ffprobe-static"
            / "bin"
            / system
            / arch
            / ("ffprobe.exe" if system == "win32" else "ffprobe")
        )
        return str(candidate) if candidate.is_file() else None
    if name != "ffmpeg":
        return None
    candidate = repository / "node_modules" / "ffmpeg-static" / "ffmpeg"
    return str(candidate) if candidate.is_file() else None
