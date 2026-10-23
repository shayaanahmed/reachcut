"""English research follows only an explicit, same-repository README translation."""

import base64

import httpx
import pytest

from clipper.providers.github_repository import GitHubRepositoryProvider


@pytest.mark.parametrize(
    ("link", "translation_found"),
    [
        ('<a href="docs/README_en.md">English</a>', True),
        ("[English](docs/README_en.md)", True),
        ("[English](https://elsewhere.example/instructions.md)", False),
        ("[English](../README_en.md)", False),
    ],
)
def test_research_uses_safe_explicit_english_translation(
    link: str, translation_found: bool
) -> None:
    primary = "Primary repository documentation with original language details.\n" + link
    english = "The tool reads video subtitles. Some platforms require login configuration."
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/readme"):
            text = primary
        elif request.url.path.endswith("/contents/docs/README_en.md"):
            text = english
        else:
            return httpx.Response(200, json={"description": "Tool", "language": "Python"})
        return httpx.Response(
            200, json={"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        _, _, sources = GitHubRepositoryProvider(client).research("https://github.com/example/tool")
    assert len(calls) == (3 if translation_found else 2)
    assert (english if translation_found else primary) in sources[0].text


def test_missing_optional_translation_keeps_original_readme() -> None:
    primary = "Useful original documentation. [English](docs/README_en.md)"

    def handle(request: httpx.Request) -> httpx.Response:
        if "/contents/" in request.url.path:
            return httpx.Response(404)
        if request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json={"encoding": "base64", "content": base64.b64encode(primary.encode()).decode()},
            )
        return httpx.Response(200, json={"description": "Tool", "language": "Python"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        _, _, sources = GitHubRepositoryProvider(client).research("https://github.com/example/tool")
    assert primary in sources[0].text
