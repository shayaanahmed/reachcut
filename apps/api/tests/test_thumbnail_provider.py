import base64
import json

import pytest

from clipper.domain.editing_plan import ThumbnailTemplate
from clipper.providers.ollama_thumbnail import (
    OllamaThumbnailProvider,
    ThumbnailPlanningError,
)


def test_thumbnail_provider_sends_frames_and_structured_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "frame_index": 1,
                            "headline": "The Turning Point",
                            "rationale": "Clear subject and useful negative space.",
                        }
                    )
                }
            }

    def post(*args: object, **kwargs: object) -> Response:
        requests.append(kwargs["json"])  # type: ignore[arg-type]
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaThumbnailProvider("http://127.0.0.1:11434", "qwen3-vl:8b")

    choice = provider.plan(
        [b"first", b"second"],
        transcript="A useful idea reaches its turning point.",
        suggested_title="A useful idea",
        template=ThumbnailTemplate.CINEMATIC,
    )

    assert choice.frame_index == 1
    assert choice.headline == "The Turning Point"
    message = requests[0]["messages"]
    assert isinstance(message, list)
    assert message[0]["images"] == [
        base64.b64encode(b"first").decode("ascii"),
        base64.b64encode(b"second").decode("ascii"),
    ]
    assert isinstance(requests[0]["format"], dict)
    assert requests[0]["think"] is False


def test_thumbnail_provider_rejects_an_unavailable_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "frame_index": 3,
                            "headline": "A Strong Hook",
                            "rationale": "Expressive subject.",
                        }
                    )
                }
            }

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())

    with pytest.raises(ThumbnailPlanningError, match="unavailable frame"):
        OllamaThumbnailProvider("http://127.0.0.1:11434", "qwen3-vl:8b").plan(
            [b"only-frame"],
            transcript="Transcript",
            suggested_title="Title",
            template=ThumbnailTemplate.SPEAKER,
        )
