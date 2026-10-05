import subprocess
from pathlib import Path

import pytest

from clipper.providers.yt_dlp import YtDlpDownloader


def test_downloader_uses_local_checkout_and_fixed_argument_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "yt-dlp"
    repository.mkdir()
    output = tmp_path / "project" / "source"
    captured: dict[str, object] = {}

    def run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        captured.update(command=command, options=options)
        (output / "source.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    stored = YtDlpDownloader(repository).download(
        "https://www.youtube.com/watch?v=abc",
        output,
        1_024,
    )

    command = captured["command"]
    options = captured["options"]
    assert isinstance(command, list)
    assert command[1:3] == ["-m", "yt_dlp"]
    assert "--no-config" in command
    assert command[-2:] == ["--", "https://www.youtube.com/watch?v=abc"]
    assert isinstance(options, dict)
    assert options["cwd"] == repository.resolve()
    assert "shell" not in options
    assert stored.path == output / "source.mp4"
