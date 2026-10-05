from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx

from clipper.discovery import (
    CountryOption,
    DiscoveryResult,
    DiscoveryUnavailableError,
    SourceCandidate,
    TrendTopic,
)

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
HttpGetter = Callable[..., httpx.Response]
OpportunityType = Literal["trending_interview", "upcoming_interview"]
RECENT_SOURCE_DAYS = 7

TRENDS_NAMESPACE = "https://trends.google.com/trending/rss"
CATEGORY_QUERIES = {
    "news": "breaking news analysis",
    "movies": "movie television cast interview",
    "sports": "sports athlete interview",
    "technology": "technology creator interview",
    "podcasts": "podcast interview",
    "gaming": "gaming creator interview",
}


class GoogleYouTubeDiscoveryProvider:
    """Fetch Google trend signals and inspect YouTube results without downloading media."""

    def __init__(
        self,
        repository: Path | None = None,
        timeout_seconds: float = 45,
        *,
        runner: ProcessRunner = subprocess.run,
        http_get: HttpGetter = httpx.get,
    ) -> None:
        self.repository = repository.resolve() if repository and repository.is_dir() else None
        self.timeout_seconds = timeout_seconds
        self._runner = runner
        self._http_get = http_get

    def discover(
        self,
        country: CountryOption,
        limit: int,
        *,
        query: str | None = None,
        category: str = "trending",
    ) -> DiscoveryResult:
        if query or category != "trending":
            return self._discover_topic(country, limit, query=query, category=category)
        try:
            response = self._http_get(
                "https://trends.google.com/trending/rss",
                params={"geo": country.code},
                headers={"User-Agent": "Clipper/0.1 trend discovery"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            topics = parse_trending_topics(response.text, limit)
        except (httpx.HTTPError, ElementTree.ParseError) as error:
            raise DiscoveryUnavailableError("could not fetch current trend data") from error
        if not topics:
            raise DiscoveryUnavailableError("the trend provider returned no topics")

        sources: list[SourceCandidate] = []
        failed_searches = 0
        per_topic = max(2, min(4, limit // 2))
        for topic in topics[:2]:
            try:
                sources.extend(
                    self._search(
                        f"{topic.title} interview {country.name}",
                        per_topic,
                        topic.title,
                        "trending_interview",
                    )
                )
            except DiscoveryUnavailableError:
                failed_searches += 1
        try:
            sources.extend(
                self._search(
                    f"upcoming interview {country.name}",
                    max(3, limit // 2),
                    f"Upcoming interviews in {country.name}",
                    "upcoming_interview",
                    upcoming_only=True,
                )
            )
        except DiscoveryUnavailableError:
            failed_searches += 1
        deduplicated = {source.id: source for source in sources}
        ranked = sorted(
            deduplicated.values(), key=lambda source: source.source_score, reverse=True
        )[:limit]
        note = (
            "Sources are from the last 7 days or genuinely upcoming. "
            "Confirm media rights before importing."
        )
        if failed_searches:
            note = (
                "Trend data is current, but some video source searches were unavailable. "
                "Confirm media rights before importing."
            )
        return DiscoveryResult(
            country=country,
            category=category,
            fetched_at=datetime.now(UTC),
            topics=topics,
            sources=ranked,
            note=note,
        )

    def _discover_topic(
        self,
        country: CountryOption,
        limit: int,
        *,
        query: str | None,
        category: str,
    ) -> DiscoveryResult:
        phrase = query or CATEGORY_QUERIES.get(category, category)
        topics = [TrendTopic(title=query or category.replace("_", " ").title())]
        searches = (
            f"{phrase} interview {country.name}",
            f"{phrase} podcast {country.name}",
        )
        sources: list[SourceCandidate] = []
        failed_searches = 0
        per_search = max(4, min(8, limit))
        for search in searches:
            try:
                sources.extend(
                    self._search(
                        search, per_search, query or category.title(), "trending_interview"
                    )
                )
            except DiscoveryUnavailableError:
                failed_searches += 1
        ranked = sorted(
            {source.id: source for source in sources}.values(),
            key=lambda source: source.source_score,
            reverse=True,
        )[:limit]
        note = "Recent public source ideas. Confirm media rights before importing."
        if failed_searches:
            note = "Some source searches were unavailable. Confirm media rights before importing."
        return DiscoveryResult(
            country=country,
            query=query,
            category=category,
            fetched_at=datetime.now(UTC),
            topics=topics,
            sources=ranked,
            note=note,
        )

    def _search(
        self,
        query: str,
        limit: int,
        topic: str,
        opportunity_type: OpportunityType,
        *,
        upcoming_only: bool = False,
    ) -> list[SourceCandidate]:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-config",
            "--skip-download",
            "--playlist-end",
            str(limit),
            "--dateafter",
            f"now-{RECENT_SOURCE_DAYS}days",
            "--print",
            "%(.{id,title,webpage_url,channel,thumbnail,duration,view_count,"
            "timestamp,release_timestamp,live_status})j",
        ]
        if runtime := _javascript_runtime():
            command.extend(("--js-runtimes", runtime))
        command.extend(("--", f"ytsearch{limit}:{query}"))
        try:
            completed = self._runner(
                command,
                cwd=self.repository,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise DiscoveryUnavailableError("video source search timed out") from error
        if completed.returncode != 0:
            raise DiscoveryUnavailableError("video source search failed")
        try:
            entries = [
                decoded
                for line in completed.stdout.splitlines()
                if isinstance((decoded := json.loads(line)), dict)
            ]
        except json.JSONDecodeError as error:
            raise DiscoveryUnavailableError("video source search returned invalid data") from error

        sources: list[SourceCandidate] = []
        cutoff = datetime.now(UTC) - timedelta(days=RECENT_SOURCE_DAYS)
        for index, entry in enumerate(entries):
            live_status = entry.get("live_status")
            release_timestamp = _number(entry.get("release_timestamp"))
            is_upcoming = live_status == "is_upcoming" or (
                release_timestamp is not None and release_timestamp > datetime.now(UTC).timestamp()
            )
            if upcoming_only and not is_upcoming:
                continue
            published_timestamp = _number(entry.get("timestamp"))
            if not is_upcoming and (
                published_timestamp is None
                or datetime.fromtimestamp(published_timestamp, UTC) < cutoff
            ):
                continue
            source = _source_candidate(
                entry,
                index,
                topic,
                "upcoming_interview" if is_upcoming else opportunity_type,
                is_upcoming,
            )
            if source is not None:
                sources.append(source)
        return sources


def parse_trending_topics(document: str, limit: int) -> list[TrendTopic]:
    if len(document.encode()) > 2 * 1024 * 1024:
        raise ElementTree.ParseError("trend feed exceeds the safe size limit")
    lowered = document.casefold()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ElementTree.ParseError("trend feed contains prohibited XML declarations")
    root = ElementTree.fromstring(document)  # noqa: S314 - bounded and DTD/entity-free above
    topics: list[TrendTopic] = []
    namespace = {"ht": TRENDS_NAMESPACE}
    for item in root.findall("./channel/item")[:limit]:
        title = _text(item.find("title"))
        if not title:
            continue
        news_item = item.find("ht:news_item", namespace)
        news_title = (
            _text(news_item.find("ht:news_item_title", namespace))
            if news_item is not None
            else None
        )
        news_url = (
            _text(news_item.find("ht:news_item_url", namespace)) if news_item is not None else None
        )
        topics.append(
            TrendTopic.model_validate(
                {
                    "title": title,
                    "approximate_traffic": _text(item.find("ht:approx_traffic", namespace)),
                    "news_title": news_title,
                    "news_url": news_url,
                }
            )
        )
    return topics


def _source_candidate(
    entry: dict[str, Any],
    index: int,
    topic: str,
    opportunity_type: OpportunityType,
    is_upcoming: bool,
) -> SourceCandidate | None:
    identifier = str(entry.get("id") or "").strip()
    title = str(entry.get("title") or "").strip()
    if not identifier or not title:
        return None
    url = entry.get("webpage_url") or entry.get("original_url")
    if not isinstance(url, str) or not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={identifier}"
    view_count = _integer(entry.get("view_count"))
    popularity = min(12, round(math.log10(max(1, view_count)) * 2)) if view_count else 0
    source_score = min(100, max(0, 84 - index * 4 + popularity + (6 if is_upcoming else 0)))
    timestamp = _number(entry.get("release_timestamp") or entry.get("timestamp"))
    published_at = datetime.fromtimestamp(timestamp, UTC) if timestamp is not None else None
    thumbnail = entry.get("thumbnail")
    if not isinstance(thumbnail, str):
        thumbnails = entry.get("thumbnails")
        if isinstance(thumbnails, list) and thumbnails and isinstance(thumbnails[-1], dict):
            thumbnail = thumbnails[-1].get("url")
    return SourceCandidate.model_validate(
        {
            "id": identifier,
            "title": title,
            "url": url,
            "channel": _optional_text(entry.get("channel") or entry.get("uploader")),
            "thumbnail_url": (
                thumbnail if isinstance(thumbnail, str) and thumbnail.startswith("http") else None
            ),
            "duration_seconds": _number(entry.get("duration")),
            "view_count": view_count,
            "published_at": published_at,
            "opportunity_type": opportunity_type,
            "topic": topic,
            "is_upcoming": is_upcoming,
            "source_score": source_score,
        }
    )


def _javascript_runtime() -> str | None:
    if shutil.which("deno"):
        return "deno"
    if shutil.which("node"):
        return "node"
    return None


def _text(element: ElementTree.Element | None) -> str | None:
    return element.text.strip() if element is not None and element.text else None


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _integer(value: object) -> int | None:
    if not isinstance(value, str | int | float):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float | None:
    if not isinstance(value, str | int | float):
        return None
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        return None
