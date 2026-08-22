import pytest

from clipper.domain.transcript import Transcript
from clipper.providers.ollama import OllamaEditorialProvider


def test_rejects_malformed_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {"response": '{"answer":"prose"}'}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    with pytest.raises(ValueError, match="candidates array"):
        provider.select_candidates(
            Transcript(language="en", segments=[], provider="test", model="test"), 5, lambda: False
        )
