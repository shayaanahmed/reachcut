"""Source adapters selected by the supplied URL, independently of niche names."""

from urllib.parse import urlsplit

from clipper.providers.github_repository import GitHubRepositoryProvider
from clipper.providers.short_research import SourceResearchProvider
from clipper.shorts.contracts import Evidence


class SubjectResearchProvider:
    def __init__(self, github: GitHubRepositoryProvider | None = None) -> None:
        self.github = github or GitHubRepositoryProvider()

    def research(self, subject: str, source_url: str = "") -> tuple[str, str, list[Evidence]]:
        url = source_url.strip() or (
            subject.strip() if subject.strip().startswith("https://") else ""
        )
        if not url:
            return subject.strip(), "", []
        parsed = urlsplit(url)
        if parsed.hostname == "github.com":
            name, canonical, sources = self.github.research(url)
            return name if subject.strip() == url else subject.strip(), canonical, sources
        sources = SourceResearchProvider((parsed.hostname or "",)).retrieve([url])
        name = sources[0].title[:200] if subject.strip() == url else subject.strip()
        return name, url, sources
