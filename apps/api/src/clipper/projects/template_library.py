"""Durable clip references and AI blueprints, stored outside the source tree."""

import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from clipper.generation.reference_templates import ReferenceTemplate
from clipper.media import MediaError, validate_public_media_url
from clipper.media.template_frames import sample_template_frames
from clipper.providers.ollama_templates import OllamaTemplateClassifier

MAX_TEMPLATE_BYTES = 50 * 1024**2
_CATALOGUE = Path(__file__).parents[1] / "generation" / "assets" / "reference_catalogue.json"


class TemplateLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.RLock()
        self._analysis_lock = threading.Lock()

    def list(self) -> list[ReferenceTemplate]:
        with self._lock:
            items = {
                item.id: item
                for item in (
                    self._source(item["source_url"], item["name"], item.get("source_category"))
                    for item in json.loads(_CATALOGUE.read_text())
                )
            }
            for path in self.root.glob("*.json"):
                item = ReferenceTemplate.model_validate_json(path.read_text())
                items[item.id] = item
            return sorted(
                [self._with_video(item) for item in items.values()],
                key=lambda item: item.status != "ready",
            )

    def get(self, template_id: str) -> ReferenceTemplate:
        if not re.fullmatch(r"[0-9a-f]{32}", template_id):
            raise MediaError("Invalid template ID")
        item = next((item for item in self.list() if item.id == template_id), None)
        if item is None:
            raise MediaError("Template not found")
        return item

    def import_source(self, url: str, name: str) -> ReferenceTemplate:
        # Only the public gallery CDN and shorts directory are enabled for remote imports.
        parsed = urlsplit(url)
        if parsed.hostname != "media.viewmax.io" or not re.fullmatch(
            r"/static/prompt-library/shorts/[a-zA-Z0-9_-]+\.mp4", parsed.path
        ):
            raise MediaError("Import a Viewmax shorts MP4 URL or upload your own clip")
        normalized = validate_public_media_url(url, ["media.viewmax.io"])
        item = self._source(normalized, name)
        with self._lock:
            existing = next((value for value in self.list() if value.id == item.id), None)
            if existing is not None:
                item = existing
            if self._path(item.id).is_file():
                return item
        with httpx.stream("GET", normalized, timeout=60, follow_redirects=False) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise MediaError("Template redirects are not supported")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_TEMPLATE_BYTES:
                    raise MediaError("Template clips must be smaller than 50 MB")
        with self._lock:
            # Another import or classifier may have finished while the download ran.
            existing = next((value for value in self.list() if value.id == item.id), None)
            if existing is not None:
                item = existing
            if self._path(item.id).is_file():
                return self._with_video(item)
            return self._save_clip(item, bytes(content))

    def upload(self, content: bytes, name: str) -> ReferenceTemplate:
        with self._lock:
            return self._save_clip(ReferenceTemplate(id=uuid4().hex, name=name), content)

    def classify(self, template_id: str, classifier: OllamaTemplateClassifier) -> ReferenceTemplate:
        with self._analysis_lock:
            item = self.get(template_id)
            try:
                if not self._path(item.id).is_file():
                    if not item.source_url:
                        raise MediaError("Upload the reference clip before classification")
                    item = self.import_source(item.source_url, item.name)
                images, duration = sample_template_frames(self._path(item.id))
                (self.root / f"{item.id}.jpg").write_bytes(images[len(images) // 2])
                blueprint = classifier.classify(images, duration)
                item = item.model_copy(
                    update={
                        "name": blueprint.name,
                        "blueprint": blueprint,
                        "duration_seconds": duration,
                        "status": "ready",
                        "error": None,
                        "analysis_model": classifier.model,
                    }
                )
            except (httpx.HTTPError, ValueError, KeyError, MediaError) as error:
                item = item.model_copy(
                    update={
                        "status": "failed",
                        "error": (
                            str(error)
                            if isinstance(error, MediaError)
                            else "Classification failed. Check the Ollama vision model and retry."
                        ),
                    }
                )
            self._save(item)
            return self._with_video(item)

    def guidance(self, template_id: str | None) -> str:
        if not template_id:
            return ""
        item = self.get(template_id)
        if item.status != "ready" or item.blueprint is None:
            raise MediaError("Classify this clip before using it as a template")
        return item.blueprint.model_dump_json()

    def video_path(self, template_id: str) -> Path:
        self.get(template_id)
        path = self._path(template_id)
        if not path.is_file():
            raise MediaError("The reference clip has not been downloaded yet")
        return path

    def poster_path(self, template_id: str) -> Path:
        video = self.video_path(template_id)
        poster = self.root / f"{template_id}.jpg"
        with self._lock:
            if not poster.is_file():
                images, _ = sample_template_frames(video)
                poster.write_bytes(images[len(images) // 2])
        return poster

    def _save_clip(self, item: ReferenceTemplate, content: bytes) -> ReferenceTemplate:
        if not content or len(content) > MAX_TEMPLATE_BYTES:
            raise MediaError("Template clips must be between 1 byte and 50 MB")
        if content[4:8] != b"ftyp":
            raise MediaError("Upload or import a valid MP4 video")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(item.id)
        path.write_bytes(content)
        try:
            images, duration = sample_template_frames(path)
        except MediaError:
            path.unlink(missing_ok=True)
            raise
        (self.root / f"{item.id}.jpg").write_bytes(images[len(images) // 2])
        item = item.model_copy(update={"duration_seconds": duration})
        self._save(item)
        return self._with_video(item)

    def _save(self, item: ReferenceTemplate) -> None:
        with self._lock:
            self._write_metadata(item)

    def _write_metadata(self, item: ReferenceTemplate) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f"{uuid4().hex}.tmp"
        temporary.write_text(item.model_dump_json(indent=2))
        temporary.replace(self.root / f"{item.id}.json")

    def _path(self, template_id: str) -> Path:
        return self.root / f"{template_id}.mp4"

    def _with_video(self, item: ReferenceTemplate) -> ReferenceTemplate:
        url = f"/api/video-generation/template-library/{item.id}/file"
        saved = self._path(item.id).is_file()
        poster = (
            f"/api/video-generation/template-library/{item.id}/poster"
            if saved
            else item.source_url.replace("-min.mp4", ".jpg")
            if item.source_url
            else None
        )
        return item.model_copy(update={"video_url": url if saved else None, "poster_url": poster})

    @staticmethod
    def _source(url: str, name: str, category: str | None = None) -> ReferenceTemplate:
        return ReferenceTemplate(
            id=hashlib.sha256(url.encode()).hexdigest()[:32],
            name=name,
            source_url=url,
            source_category=category,
        )
