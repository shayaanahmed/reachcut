import json
import subprocess
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

import clipper.api.discovery as discovery_routes
from clipper.discovery import CountryOption, DiscoveryResult, DiscoveryService, TrendTopic
from clipper.main import app
from clipper.providers.trend_discovery import GoogleYouTubeDiscoveryProvider, parse_trending_topics

RSS = """<?xml version="1.0"?>
<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
  <item><title>Major topic</title><ht:approx_traffic>200K+</ht:approx_traffic>
    <ht:news_item><ht:news_item_title>Context</ht:news_item_title>
      <ht:news_item_url>https://news.example/story</ht:news_item_url></ht:news_item>
  </item>
</channel></rss>"""


def test_google_trends_rss_is_mapped_to_typed_topics() -> None:
    topics = parse_trending_topics(RSS, 5)

    assert topics == [
        TrendTopic(
            title="Major topic",
            approximate_traffic="200K+",
            news_title="Context",
            news_url="https://news.example/story",
        )
    ]


def test_provider_finds_ranked_youtube_sources_without_downloading() -> None:
    response = httpx.Response(200, text=RSS, request=httpx.Request("GET", "https://example.test"))
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        upcoming = "upcoming" in command[-1]
        entry = {
            "id": "future-1" if upcoming else "trend-1",
            "title": "Scheduled interview" if upcoming else "Major topic interview",
            "channel": "Publisher",
            "view_count": 100_000,
            "live_status": "is_upcoming" if upcoming else "not_live",
            "timestamp": datetime.now(UTC).timestamp(),
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(entry), "")

    provider = GoogleYouTubeDiscoveryProvider(
        runner=run,
        http_get=lambda *args, **kwargs: response,
    )
    result = provider.discover(CountryOption(code="DE", name="Germany"), 4)

    assert {source.id for source in result.sources} == {"trend-1", "future-1"}
    assert result.sources[0].source_score >= result.sources[1].source_score
    assert all("--skip-download" in command for command in commands)
    assert all("--dateafter" in command for command in commands)
    assert all("now-7days" in command for command in commands)
    assert all(command[-1].startswith("ytsearch") for command in commands)
    assert all(not command[-1].startswith("ytsearchdate") for command in commands)
    assert all("--" in command for command in commands)


def test_source_search_failures_return_trends_instead_of_failing_discovery() -> None:
    response = httpx.Response(200, text=RSS, request=httpx.Request("GET", "https://example.test"))

    def fail(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "search unavailable")

    result = GoogleYouTubeDiscoveryProvider(
        runner=fail,
        http_get=lambda *args, **kwargs: response,
    ).discover(CountryOption(code="DE", name="Germany"), 4)

    assert result.topics[0].title == "Major topic"
    assert result.sources == []
    assert "some video source searches were unavailable" in result.note


def test_topic_discovery_searches_the_requested_category_without_trend_feed() -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        entry = {
            "id": f"video-{len(commands)}",
            "title": "Film creator interview",
            "channel": "Publisher",
            "view_count": 10_000,
            "live_status": "not_live",
            "timestamp": datetime.now(UTC).timestamp(),
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(entry), "")

    def unexpected_feed(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("topic search should not require the country trend feed")

    result = GoogleYouTubeDiscoveryProvider(
        runner=run,
        http_get=unexpected_feed,
    ).discover(
        CountryOption(code="US", name="United States"),
        6,
        query="film editing",
        category="movies",
    )

    assert result.query == "film editing"
    assert result.category == "movies"
    assert result.sources
    assert all("film editing" in command[-1] for command in commands)


def test_old_or_undated_sources_are_not_returned_as_current() -> None:
    response = httpx.Response(200, text=RSS, request=httpx.Request("GET", "https://example.test"))

    def old_result(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        entry = {
            "id": "old-video",
            "title": "An old interview",
            "timestamp": datetime(2020, 1, 1, tzinfo=UTC).timestamp(),
            "live_status": "not_live",
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(entry), "")

    result = GoogleYouTubeDiscoveryProvider(
        runner=old_result,
        http_get=lambda *args, **kwargs: response,
    ).discover(CountryOption(code="DE", name="Germany"), 4)

    assert result.sources == []


def test_discovery_service_caches_current_country_result() -> None:
    calls = 0

    class FakeProvider:
        def discover(
            self,
            country: CountryOption,
            limit: int,
            *,
            query: str | None = None,
            category: str = "trending",
        ) -> DiscoveryResult:
            nonlocal calls
            calls += 1
            assert query is None
            assert category == "trending"
            return DiscoveryResult(
                country=country,
                fetched_at=datetime.now(UTC),
                topics=[TrendTopic(title="Topic")],
                sources=[],
            )

    service = DiscoveryService(FakeProvider())
    first = service.discover("de", 3)
    second = service.discover("DE", 3)

    assert first == second
    assert calls == 1


def test_discovery_routes_expose_countries_and_typed_results(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = DiscoveryResult(
        country=CountryOption(code="DE", name="Germany"),
        fetched_at=datetime.now(UTC),
        topics=[TrendTopic(title="Topic")],
        sources=[],
    )

    class FakeService:
        @staticmethod
        def countries() -> tuple[CountryOption, ...]:
            return (result.country,)

        @staticmethod
        def discover(
            country: str,
            limit: int,
            *,
            query: str | None,
            category: str,
        ) -> DiscoveryResult:
            assert (country, limit, query, category) == ("DE", 4, None, "trending")
            return result

    monkeypatch.setattr(discovery_routes, "discovery_service", FakeService())
    with TestClient(app) as client:
        countries = client.get("/api/discovery/countries")
        discovered = client.get("/api/discovery?country=DE&limit=4")

    assert countries.json() == [{"code": "DE", "name": "Germany"}]
    assert discovered.status_code == 200
    assert discovered.json()["topics"][0]["title"] == "Topic"
