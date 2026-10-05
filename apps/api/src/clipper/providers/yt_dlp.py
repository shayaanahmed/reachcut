from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from clipper.media import MediaError, StoredUpload, inspect_stored_media


class YtDlpDownloader:
    """Download one public media URL through yt-dlp without invoking a shell."""

    def __init__(self, repository: Path | None = None, timeout_seconds: float = 3_600) -> None:
        self.repository = repository.resolve() if repository and repository.is_dir() else None
        self.timeout_seconds = timeout_seconds

    def download(self, url: str, target_directory: Path, max_bytes: int) -> StoredUpload:
        target_directory.mkdir(parents=True, exist_ok=False)
        command = self.command(url, target_directory, max_bytes)
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip().splitlines()
                message = detail[-1][:500] if detail else "yt-dlp could not import this URL"
                raise MediaError(message)
            candidates = [
                path
                for path in target_directory.glob("source.*")
                if path.is_file() and path.suffix not in {".part", ".ytdl"}
            ]
            if len(candidates) != 1:
                raise MediaError("yt-dlp did not produce one playable media file")
            return inspect_stored_media(candidates[0], max_bytes)
        except subprocess.TimeoutExpired as error:
            raise MediaError("yt-dlp import timed out") from error
        except Exception:
            shutil.rmtree(target_directory, ignore_errors=True)
            raise

    def command(self, url: str, target_directory: Path, max_bytes: int) -> list[str]:
        return [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-config",
            "--no-playlist",
            "--restrict-filenames",
            "--max-filesize",
            str(max_bytes),
            "--format",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--output",
            str(target_directory / "source.%(ext)s"),
            "--",
            url,
        ]
