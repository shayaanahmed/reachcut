from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import httpx


class LocalVideoEngineSupervisor:
    """Own the optional LTX worker process without coupling it to the API process."""

    def __init__(
        self,
        root: Path,
        data_dir: Path,
        base_url: str,
        token: str,
    ) -> None:
        self.root = root.resolve()
        self.data_dir = data_dir.resolve()
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: object | None = None
        self._lock = threading.Lock()

    @property
    def python_path(self) -> Path:
        return self.root / "backend" / ".venv" / "bin" / "python"

    @property
    def server_path(self) -> Path:
        return self.root / "backend" / "ltx2_server.py"

    def installed(self) -> bool:
        return self.python_path.is_file() and self.server_path.is_file()

    def running(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/health",
                headers=self._headers,
                timeout=2,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def start(self) -> bool:
        if self.running():
            return True
        if not self.installed():
            return False
        with self._lock:
            if self._process and self._process.poll() is None:
                return True
            self.data_dir.mkdir(parents=True, exist_ok=True)
            (self.data_dir / "reachcut-engine.json").write_text(
                json.dumps({"data_dir": str(self.data_dir), "url": self.base_url}) + "\n",
                encoding="utf-8",
            )
            log_path = self.data_dir / "ltx-engine.log"
            log_handle = log_path.open("ab")
            environment = os.environ.copy()
            environment.update(
                {
                    "LTX_APP_DATA_DIR": str(self.data_dir),
                    "LTX_PORT": self.base_url.rsplit(":", maxsplit=1)[-1],
                    "LTX_AUTH_TOKEN": self.token,
                    "MPLCONFIGDIR": str(self.data_dir / "cache" / "matplotlib"),
                    "TORCH_EXTENSIONS_DIR": str(self.data_dir / "cache" / "torch-extensions"),
                    "PATH": f"{self.python_path.parent}{os.pathsep}{environment.get('PATH', '')}",
                    "PYTHONUNBUFFERED": "1",
                }
            )
            if sys.platform == "darwin":
                xcrun = shutil.which("xcrun")
                if xcrun:
                    sdk = subprocess.run(
                        [xcrun, "--sdk", "macosx", "--show-sdk-path"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if sdk.returncode == 0:
                        environment["SDKROOT"] = sdk.stdout.strip()
            self._process = subprocess.Popen(
                [str(self.python_path), str(self.server_path)],
                cwd=self.root / "backend",
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._log_handle = log_handle
        return True

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}
