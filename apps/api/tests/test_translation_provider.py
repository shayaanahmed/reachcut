import json
from typing import Any

import pytest

from clipper.providers.ollama_translation import (
    CaptionTranslationError,
    OllamaCaptionTranslationProvider,
)


def test_ollama_translation_uses_strict_json_and_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"response": json.dumps({"translated_text": "Hallo Welt"})}

    def post(*args: object, **kwargs: object) -> Response:
        requests.append(kwargs["json"])  # type: ignore[arg-type]
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaCaptionTranslationProvider("http://127.0.0.1:11434", "qwen")

    assert provider.translate("Hello world", "en", "de") == "Hallo Welt"
    assert requests[0]["think"] is False
    assert requests[0]["options"] == {"temperature": 0.0}


def test_ollama_translation_rejects_non_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"response": "Here is your translation"}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    provider = OllamaCaptionTranslationProvider("http://127.0.0.1:11434", "qwen")

    with pytest.raises(CaptionTranslationError, match="translation failed"):
        provider.translate("Hello", "en", "de")
