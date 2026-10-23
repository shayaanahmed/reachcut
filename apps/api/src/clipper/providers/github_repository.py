"""Read public repository metadata and README text without cloning or running code."""

import base64
import json
import re
from urllib.parse import quote, urlsplit

import httpx

from clipper.shorts.contracts import Evidence, fingerprint


class GitHubRepositoryProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    @staticmethod
    def identity(url: str) -> tuple[str, str]:
        parsed = urlsplit(url.strip())
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a public repository URL such as https://github.com/owner/repo")
        path = parsed.path.strip("/")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+", path):
            raise ValueError("Paste the repository root URL, without a file or branch path")
        owner, repo = path.split("/")
        repo = repo.removesuffix(".git")
        if repo in {"", ".", ".."}:
            raise ValueError("Repository name is invalid")
        return owner, repo

    @staticmethod
    def _get(client: httpx.Client, path: str) -> dict[str, object]:
        with client.stream(
            "GET",
            "https://api.github.com" + path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ReachCut-content-research",
            },
        ) as response:
            if response.status_code == 404:
                raise ValueError("Public repository or README not found. Check the GitHub URL.")
            if response.status_code in {403, 429}:
                raise ValueError(
                    "GitHub public research is rate limited. Retry after the rate limit resets."
                )
            if response.is_redirect:
                raise ValueError("This repository moved. Use its current GitHub URL.")
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise ValueError("Repository document exceeds the 2 MB research limit")
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError("GitHub returned invalid repository data")
        return payload

    def research(self, url: str) -> tuple[str, str, list[Evidence]]:
        owner, repo = self.identity(url)
        canonical = f"https://github.com/{owner}/{repo}"
        path = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        if self.client:
            metadata = self._get(self.client, path)
            readme = self._readme(self.client, path)
        else:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                metadata = self._get(client, path)
                readme = self._readme(client, path)
        if metadata.get("private"):
            raise ValueError("Choose a public repository")
        if readme.get("encoding") != "base64" or not isinstance(readme.get("content"), str):
            raise ValueError("GitHub did not return a readable README")
        text = base64.b64decode(str(readme["content"])).decode("utf-8", errors="replace")
        if len(text.strip()) < 20:
            raise ValueError(
                "This repository needs a more detailed README for an explanatory video"
            )
        facts = (
            f"Repository: {owner}/{repo}\n"
            f"Description: {metadata.get('description') or 'Not supplied'}\n"
            f"Primary language: {metadata.get('language') or 'Not supplied'}\n"
        )
        return (
            f"{owner}/{repo}",
            canonical,
            [
                Evidence(
                    id=fingerprint(canonical)[:16],
                    url=canonical,
                    title=f"{owner}/{repo} — repository metadata and README",
                    kind="primary",
                    text=(facts + "\nREADME documentation:\n" + text)[:20000],
                )
            ],
        )

    def _readme(self, client: httpx.Client, path: str) -> dict[str, object]:
        readme = self._get(client, path + "/readme")
        if readme.get("encoding") != "base64" or not isinstance(readme.get("content"), str):
            return readme
        text = base64.b64decode(str(readme["content"])).decode("utf-8", errors="replace")
        # Follow an explicitly labelled translation inside this same repository only.
        match = re.search(
            r"<a\b[^>]*href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>\s*English\s*</a>", text, re.I
        )
        if not match:
            match = re.search(r"\[English(?: version)?\]\(([^)]+)\)", text, re.I)
        if not match:
            return readme
        translation = match[1].removeprefix("./")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+\.md", translation, re.I) or any(
            part in {"", ".", ".."} for part in translation.split("/")
        ):
            return readme
        try:
            english = self._get(client, path + "/contents/" + quote(translation, safe="/"))
            if english.get("encoding") == "base64" and isinstance(english.get("content"), str):
                decoded = base64.b64decode(str(english["content"])).decode(
                    "utf-8", errors="replace"
                )
                if len(decoded.strip()) >= 20:
                    return english
        except (httpx.HTTPError, ValueError):
            pass  # The primary README remains usable if its optional translation moved.
        return readme
