from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import urlencode

import httpx

from clipper.generation import (
    SceneGenerationRequest,
    SceneGenerationResult,
    VideoGenerationBusyError,
    VideoGenerationProvider,
)
from clipper.media import MediaError
from clipper.media.video_validation import valid_generated_video


class LtxOutputUnavailable(MediaError):
    pass


class LtxDesktopVideoProvider(VideoGenerationProvider):
    """HTTP adapter for Lightricks' official, fully local LTX Desktop backend."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout_seconds: float = 7_200,
        data_dir: Path | None = None,
        video_validator: Callable[[Path, float | None], bool] = valid_generated_video,
    ) -> None:
        self._video_validator = video_validator
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._data_dir = data_dir.resolve() if data_dir else None
        self._observed_remote_data_dir: Path | None = None

    @property
    def identity(self) -> str:
        return "ltx-2.5-fast-local"

    def health(self) -> dict[str, object]:
        response = httpx.get(f"{self.base_url}/health", headers=self._headers, timeout=5)
        response.raise_for_status()
        return response.json()

    def generation_progress(self) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}/api/generation/progress",
            headers=self._headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def model_recommendation(self) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}/api/models/ltx-recommendation",
            headers=self._headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def huggingface_auth_status(self) -> str:
        response = httpx.get(
            f"{self.base_url}/api/auth/huggingface/status",
            headers=self._headers,
            timeout=5,
        )
        response.raise_for_status()
        return str(response.json().get("status", "not_authenticated"))

    def start_huggingface_login(self) -> str:
        response = httpx.post(
            f"{self.base_url}/api/auth/huggingface/login",
            headers=self._headers,
            timeout=5,
        )
        response.raise_for_status()
        params = response.json()
        query = urlencode(
            {
                "client_id": params["client_id"],
                "redirect_uri": params["redirect_uri"],
                "response_type": "code",
                "scope": params["scope"],
                "state": params["state"],
                "code_challenge": params["code_challenge"],
                "code_challenge_method": params["code_challenge_method"],
            }
        )
        return f"https://huggingface.co/oauth/authorize?{query}"

    def start_model_download(self) -> str:
        recommendation = self.model_recommendation()
        checkpoint_ids = recommendation.get("cps_to_download", [])
        if not isinstance(checkpoint_ids, list) or not checkpoint_ids:
            return ""
        response = httpx.post(
            f"{self.base_url}/api/models/download",
            headers=self._headers,
            json={"type": "download", "cp_ids": checkpoint_ids},
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["sessionId"])

    def active_download(self) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}/api/models/download/active",
            headers=self._headers,
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        session_id = payload.get("session_id")
        if not session_id:
            return {"status": "idle", "progress": 0.0}
        progress = httpx.get(
            f"{self.base_url}/api/models/download/progress",
            headers=self._headers,
            params={"sessionId": session_id},
            timeout=5,
        )
        progress.raise_for_status()
        detail = progress.json()
        raw_progress = float(detail.get("total_progress", 0.0))
        normalized_progress = raw_progress / 100 if raw_progress > 1 else raw_progress
        return {
            "status": detail.get("status", "downloading"),
            "progress": min(1.0, max(0.0, normalized_progress)),
        }

    def generate_scene(
        self, request: SceneGenerationRequest, output: Path
    ) -> SceneGenerationResult:
        signature = hashlib.sha256(
            json.dumps(asdict(request), default=str, sort_keys=True).encode()
        ).hexdigest()
        receipt = output.with_suffix(".ltx.json")
        try:
            cached = json.loads(receipt.read_text())
        except (OSError, ValueError):
            cached = None
        if isinstance(cached, dict) and cached.get("signature") == signature:
            if not cached.get("video_path") and cached.get("generation_id"):
                progress = self.generation_progress()
                if progress.get("id") == cached["generation_id"]:
                    if progress.get("status") == "running":
                        raise VideoGenerationBusyError(
                            "Waiting for the saved LTX generation to finish"
                        )
                    if progress.get("status") == "complete" and isinstance(
                        progress.get("result"), str
                    ):
                        cached["video_path"] = progress["result"]
                        self._save_receipt(receipt, cached)
                # Never use a result belonging to a different generation.
            try:
                self._materialize_scene(str(cached["video_path"]), output, request.duration_seconds)
                width, height = dimensions_for(request.aspect_ratio, request.quality)
                return SceneGenerationResult(output, self.identity, width, height)
            except (LtxOutputUnavailable, KeyError):
                # A permanently invalid or missing original needs a fresh render.
                receipt.unlink(missing_ok=True)
        reference_image = self._stage_input(request.reference_image)
        request = replace(request, reference_image=reference_image)
        response = httpx.post(
            f"{self.base_url}/api/generate",
            headers=self._headers,
            json={
                "prompt": request.prompt,
                "promptProvenance": "enhanced",
                "resolution": "1080p" if request.quality == "1080p" else "540p",
                "model": "fast",
                "cameraMotion": request.camera_motion,
                "negativePrompt": request.negative_prompt,
                "duration": request.duration_seconds,
                "fps": 24,
                "audio": True,
                "imagePath": (
                    str(request.reference_image.resolve()) if request.reference_image else None
                ),
                "aspectRatio": request.aspect_ratio,
                "seed": request.seed,
                "loras": [],
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response, operation="generate the scene")
        payload = response.json()
        if payload.get("status") != "complete" or not payload.get("video_path"):
            raise MediaError("The local LTX render was cancelled before producing a video")
        # Record the completed GPU work before file transport/validation can fail.
        output.parent.mkdir(parents=True, exist_ok=True)
        self._save_receipt(receipt, {"signature": signature, "video_path": payload["video_path"]})
        self._materialize_scene(str(payload["video_path"]), output, request.duration_seconds)
        width, height = dimensions_for(request.aspect_ratio, request.quality)
        return SceneGenerationResult(output, self.identity, width, height)

    @staticmethod
    def _save_receipt(receipt: Path, payload: dict[str, object]) -> None:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        pending = receipt.with_suffix(".pending.json")
        pending.write_text(json.dumps(payload))
        pending.replace(receipt)

    def _materialize_scene(self, value: str, output: Path, duration: float) -> None:
        # Bind-mounted files can briefly expose an MP4 header before its moov atom.
        # Retry only transport using the same completed LTX output, never the GPU job.
        deadline = time.monotonic() + 30
        copying = output.with_name(f"{output.stem}.copying.mp4")
        while True:
            try:
                source = self._resolve_engine_path(value)
            except MediaError:
                source = None
            if source is not None and self._video_validator(source, duration):
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, copying)
                if self._video_validator(copying, duration):
                    copying.replace(output)
                    return
            if time.monotonic() >= deadline:
                copying.unlink(missing_ok=True)
                raise LtxOutputUnavailable(
                    "LTX finished rendering, but its MP4 is not yet readable. "
                    "Resume will retry the saved output; completed scenes are preserved."
                )
            time.sleep(0.5)

    def generate_character_reference(self, prompt: str, output: Path, seed: int) -> Path:
        response = httpx.post(
            f"{self.base_url}/api/generate-image",
            headers=self._headers,
            json={
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "numSteps": 8,
                "numImages": 1,
                "strength": 0.65,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        paths = payload.get("image_paths", [])
        if payload.get("status") != "complete" or not paths:
            raise MediaError("The local image model did not produce a character reference")
        source = self._resolve_engine_path(str(paths[0]))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        return output

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, operation: str) -> None:
        if response.status_code == 409:
            raise VideoGenerationBusyError(
                "LTX is already rendering. This short will continue automatically when it is free."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if not isinstance(detail, str) or not detail.strip():
                detail = response.text.strip() or f"HTTP {response.status_code}"
            raise MediaError(f"LTX could not {operation}: {detail[:1_500]}") from error

    def _stage_input(self, source: Path | None) -> Path | None:
        if source is None:
            return None
        if self._data_dir is None:
            return source.resolve()
        source = source.resolve(strict=True)
        staging = self._data_dir / "reachcut-inputs"
        staging.mkdir(parents=True, exist_ok=True)
        target = staging / f"{source.stem}-{source.stat().st_mtime_ns}{source.suffix.lower()}"
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        return self._remote_data_dir / target.relative_to(self._data_dir)

    def _resolve_engine_path(self, value: str) -> Path:
        source = Path(value)
        if source.is_file():
            return source
        if self._data_dir is not None:
            try:
                relative = source.relative_to(self._remote_data_dir)
            except ValueError:
                relative = None
            if relative is not None:
                bridged = self._owned_bridge_file(relative)
                if bridged is not None:
                    return bridged
            # Older supervisor launches did not write the host/container manifest.
            # LTX's generated media live directly inside its outputs directory.
            if source.is_absolute() and source.parent.name == "outputs":
                bridged = self._owned_bridge_file(Path("outputs") / source.name)
                if bridged is not None:
                    self._observed_remote_data_dir = source.parent.parent
                    return bridged
        bridge = f" Shared media directory: {self._data_dir}." if self._data_dir else ""
        raise MediaError(f"The local LTX backend returned a missing media file: {value}.{bridge}")

    def _owned_bridge_file(self, relative: Path) -> Path | None:
        if self._data_dir is None:
            return None
        candidate = (self._data_dir / relative).resolve()
        if not candidate.is_relative_to(self._data_dir) or not candidate.is_file():
            return None
        return candidate

    @property
    def _remote_data_dir(self) -> Path:
        if self._data_dir is None:
            raise MediaError("The local LTX data bridge is not configured")
        if self._observed_remote_data_dir is not None:
            return self._observed_remote_data_dir
        manifest = self._data_dir / "reachcut-engine.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            remote = payload.get("data_dir")
            if isinstance(remote, str) and remote:
                return Path(remote)
        except (OSError, ValueError):
            pass
        return self._data_dir


def dimensions_for(aspect_ratio: str, quality: str) -> tuple[int, int]:
    long_edge = 1920 if quality == "1080p" else 960
    short_edge = 1080 if quality == "1080p" else 544
    if aspect_ratio == "9:16":
        return short_edge, long_edge
    if aspect_ratio == "16:9":
        return long_edge, short_edge
    return short_edge, short_edge
