"""Native Ollama image generation; no external image service or video engine."""

import base64
import binascii
import io
import json
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError


class OllamaImageProvider:
    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def generate(
        self, model: str, prompt: str, output: Path, cancelled: Callable[[], bool]
    ) -> Path:
        if output.is_file():
            return output
        output.parent.mkdir(parents=True, exist_ok=True)
        pending = output.with_name(uuid4().hex + ".png")
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(60, connect=10),
                transport=self.transport,
            ) as client:
                if cancelled():
                    raise InterruptedError("Artwork generation stopped")
                response = client.post("/api/show", json={"model": model})
                if response.status_code == 404:
                    raise ValueError(
                        f"Install the Ollama image model {model} on your Ollama host, "
                        "or choose designed visuals in the niche settings"
                    )
                response.raise_for_status()
                if "image" not in response.json().get("capabilities", []):
                    raise ValueError(
                        f"{model} cannot generate images. Choose an Ollama model "
                        "with the image capability, such as x/flux2-klein:4b"
                    )
                deadline = time.monotonic() + 600
                with client.stream(
                    "POST",
                    "/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": True,
                        "width": 768,
                        "height": 1360,
                        "steps": 4,
                    },
                ) as stream:
                    stream.raise_for_status()
                    for line in stream.iter_lines():
                        if cancelled():
                            raise InterruptedError("Artwork generation stopped")
                        if time.monotonic() > deadline:
                            raise ValueError("Ollama artwork timed out. Retry reuses saved scenes.")
                        if not line:
                            continue
                        if len(line) > 32_000_000:
                            raise ValueError("Ollama returned an oversized image")
                        payload = json.loads(line)
                        if payload.get("error"):
                            raise ValueError(
                                "Ollama image generation failed: " + str(payload["error"])[:300]
                            )
                        encoded = payload.get("image")
                        if encoded:
                            data = base64.b64decode(encoded, validate=True)
                            with Image.open(io.BytesIO(data)) as image:
                                if image.format != "PNG" or not (
                                    256 <= image.width <= 2048 and 256 <= image.height <= 2048
                                ):
                                    raise ValueError("Ollama returned an unsupported image")
                                image.verify()
                            pending.write_bytes(data)
                            # Store only provenance, never the large base64 response.
                            output.with_suffix(".json").write_text(
                                json.dumps(
                                    {
                                        "provider": "ollama",
                                        "model": model,
                                        "prompt": prompt,
                                        "illustrative": True,
                                    }
                                ),
                                encoding="utf-8",
                            )
                            pending.replace(output)
                            return output
            raise ValueError(
                "Ollama returned no image. Select an image generation model "
                "in the niche settings and retry."
            )
        except (binascii.Error, UnidentifiedImageError) as error:
            raise ValueError("Ollama returned invalid image data") from error
        finally:
            pending.unlink(missing_ok=True)
