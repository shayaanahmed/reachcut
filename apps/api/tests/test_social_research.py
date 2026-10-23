import pytest

from clipper.providers.trends import AgentReachTrendProvider, TrendDiscoveryError


def test_youtube_search_bounds_duration_and_preserves_available_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgentReachTrendProvider()

    def extract(target: str, *, flat: bool = False) -> dict:
        if flat:
            return {
                "entries": [
                    {"id": "abcdefghijk", "duration": 40},
                    {"id": "lmnopqrstuv", "duration": 600},
                ]
            }
        return {
            "title": "Short reference",
            "duration": 40,
            "description": "Real description",
            "view_count": 0,
            "upload_date": "20261015",
        }

    monkeypatch.setattr(provider, "_extract", extract)
    results = provider.search("AI tools", "test")
    assert len(results) == 1 and results[0].view_count == 0
    assert results[0].description == "Real description"
    assert results[0].published_at.startswith("2026-10-15")
    assert results[0].transcript == ""


TEST_BRIEF = (
    "Create a 30-second vertical video showing how an AI tool turns messy meeting notes "
    "into a clear action plan. Open with scattered notes, then reveal an organized checklist "
    "with tasks, owners, and deadlines. Keep the visuals clean and the pacing quick."
)


def test_production_brief_becomes_topic_queries_without_changing_original() -> None:
    from clipper.shorts.search_queries import search_queries

    queries = search_queries("AI tools", TEST_BRIEF)
    assert queries == [
        "AI tools meeting notes action plan",
        "AI meeting notes",
        "AI tools",
    ]
    assert all("vertical" not in q and "30-second" not in q for q in queries)
    assert search_queries("Food", "Create a video.") == ["Food"]


def test_youtube_retries_broader_topics_and_scans_past_long_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgentReachTrendProvider()
    queries = []

    def extract(target: str, *, flat: bool = False) -> dict:
        if flat:
            queries.append(target)
            entries = [{"id": f"abcdefghij{i}", "duration": 700} for i in range(9)]
            if len(queries) > 1:
                entries.append({"id": "xyzabcdefgh", "title": "Meeting notes demo", "duration": 30})
            return {"entries": entries}
        return {"description": "A real meeting notes demonstration", "duration": 30}

    monkeypatch.setattr(provider, "_extract", extract)
    results = provider.search("AI tools", TEST_BRIEF)
    assert len(queries) == 2
    assert "vertical" not in queries[0] and "meeting notes action plan" in queries[0]
    assert len(results) == 1 and results[0].duration_seconds == 30


def test_metadata_failures_do_not_appear_as_no_matching_videos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgentReachTrendProvider()

    def extract(target: str, *, flat: bool = False) -> dict:
        if flat:
            return {"entries": [{"id": "abcdefghijk", "title": "Reference", "duration": None}]}
        raise TrendDiscoveryError("YouTube metadata is unavailable")

    monkeypatch.setattr(provider, "_extract", extract)
    with pytest.raises(TrendDiscoveryError, match="metadata"):
        provider.search("AI tools", "meeting notes")


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("instagram", "https://www.instagram.com/reel/real-reference/"),
        ("facebook", "https://www.facebook.com/creator/videos/12345/"),
        ("x", "https://x.com/creator/status/12345"),
        ("tiktok", "https://www.tiktok.com/@creator/video/12345"),
        ("youtube", "https://www.youtube.com/shorts/abcdefghijk"),
    ],
)
def test_public_platform_fallback_needs_no_searxng_and_filters_non_post_urls(
    platform: str,
    url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgentReachTrendProvider(search_url="")
    monkeypatch.setattr(provider, "search", lambda *args, **kwargs: [])
    queries = []

    def public(query: str) -> list[dict]:
        queries.append(query)
        return [
            {
                "title": "Login",
                "href": "https://www.instagram.com/accounts/login/",
                "body": "Sign in",
            },
            {"title": "Reference", "href": "https://evil.test/reel/123", "body": "Wrong host"},
            {
                "title": "AI meeting notes demonstration",
                "href": url,
                "body": "An indexed real description",
            },
        ]

    monkeypatch.setattr(provider, "_public_results", public)
    results = provider.search_platform(platform, "AI tools", TEST_BRIEF)
    assert len(results) == 1 and results[0].url == url
    assert results[0].duration_seconds is None and results[0].view_count is None
    assert "unverified" in results[0].basis
    assert "vertical" not in queries[0]
