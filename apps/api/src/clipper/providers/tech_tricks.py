"""Read current official feature guides before Ollama proposes practical tech tricks."""

import logging

import httpx

from clipper.providers.short_research import SourceResearchProvider
from clipper.shorts.contracts import Evidence

logger = logging.getLogger(__name__)
GUIDES = (
    "https://support.microsoft.com/en-us/windows/apps/using-the-clipboard",
    ("https://support.apple.com/guide/mac-help/replace-text-punctuation-documents-mac-mh35735/mac"),
    "https://support.google.com/chrome/answer/2391819?hl=en&co=GENIE.Platform%3DDesktop",
    "https://support.apple.com/guide/iphone/use-text-replacements-iph6d01d862/ios",
    "https://support.google.com/chrome/answer/157179?hl=en&co=GENIE.Platform%3DDesktop",
)


def research_tech_tricks(offset: int = 0) -> tuple[list[Evidence], list[str]]:
    provider = SourceResearchProvider(
        ("support.microsoft.com", "support.apple.com", "support.google.com")
    )
    sources: list[Evidence] = []
    notices: list[str] = []
    ordered = list(GUIDES[offset % len(GUIDES) :] + GUIDES[: offset % len(GUIDES)])
    for url in ordered:
        try:
            found = provider.retrieve([url])
            if not found or len(found[0].text.strip()) < 100:
                raise ValueError("Guide did not contain readable instructions")
            found[0].kind = "primary"
            sources.extend(found)
            if len(sources) == 3:
                break
        except (ValueError, httpx.HTTPError):
            logger.warning("Tech guide unavailable: %s", url)
            notices.append("One official guide could not be read; the remaining guides were used.")
    if len(sources) < 2:
        raise ValueError(
            "Official tech guides could not be read. Check the connection and retry; no "
            "tips were invented."
        )
    return sources, list(dict.fromkeys(notices))
