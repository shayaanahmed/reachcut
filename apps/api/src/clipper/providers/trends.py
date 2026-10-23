"""Bounded discovery using Agent-Reach's yt-dlp toolchain and optional SearXNG."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urlsplit

import httpx

from clipper.media.errors import MediaError
from clipper.media.url_policy import validate_public_media_url
from clipper.shorts.contracts import fingerprint
from clipper.shorts.discovery import Platform, SocialReference
from clipper.shorts.search_queries import search_queries


class TrendDiscoveryError(RuntimeError):
    """A discovery tool is unavailable or returned unusable data."""


class AgentReachTrendProvider:
    """Call the upstream tools directly; Agent-Reach is a setup/diagnostic layer."""

    def __init__(
        self,
        agent_reach_command: str = "agent-reach",
        search_command: str = "yt-dlp",
        search_url: str = "",
    ) -> None:
        self.agent_reach_command = agent_reach_command
        self.search_command = search_command
        self.search_url = search_url

    def _command(self) -> list[str]:
        if shutil.which(self.search_command):
            return [self.search_command]
        if self.search_command == "yt-dlp" and importlib.util.find_spec("yt_dlp"):
            return [sys.executable, "-m", "yt_dlp"]
        raise TrendDiscoveryError("Install yt-dlp in the API environment to search YouTube.")

    def capabilities(self) -> list[dict[str, object]]:
        public_search = bool(self.search_url) or importlib.util.find_spec("ddgs") is not None
        try:
            self._command()
            youtube = True
        except TrendDiscoveryError:
            youtube = False
        return [
            {
                "id": "youtube",
                "name": "YouTube Shorts",
                "available": youtube or public_search,
                "detail": "Video search and captions, with public search as a fallback",
            },
            *[
                {"id": platform, "name": name, "available": public_search, "detail": detail}
                for platform, name, detail in (
                    ("instagram", "Instagram Reels", "Public indexed reels and caption excerpts"),
                    ("facebook", "Facebook", "Public indexed reels and videos"),
                    ("x", "X / Twitter", "Public indexed posts; video presence may be unverified"),
                    ("tiktok", "TikTok", "Public indexed videos and description excerpts"),
                )
            ],
        ]

    def _extract(self, target: str, *, flat: bool = False) -> dict[str, object]:
        args = [
            *self._command(),
            "--ignore-config",
            "--no-warnings",
            "--skip-download",
            "--dump-single-json",
            "--socket-timeout",
            "12",
            "--retries",
            "1",
        ]
        args += ["--flat-playlist"] if flat else ["--no-playlist"]
        try:
            completed = subprocess.run(
                [*args, "--", target], check=True, capture_output=True, text=True, timeout=60
            )
            payload = json.loads(completed.stdout)
            if not isinstance(payload, dict):
                raise ValueError("Expected metadata object")
            return payload
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise TrendDiscoveryError(
                "YouTube discovery failed. Check connectivity and the API's yt-dlp installation."
            ) from error

    def search(self, niche: str, prompt: str, limit: int = 5) -> list[SocialReference]:
        results: list[SocialReference] = []
        seen: set[str] = set()
        failures: list[str] = []
        attempts = 0
        # Retry broader topic queries instead of submitting the whole production brief.
        for query in search_queries(niche, prompt):
            try:
                payload = self._extract(f"ytsearch{min(limit * 3, 15)}:{query} shorts", flat=True)
            except TrendDiscoveryError as error:
                failures.append(str(error))
                continue
            entries = payload.get("entries", [])
            if not isinstance(entries, list):
                failures.append("YouTube returned invalid search results")
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                video_id = str(entry.get("id", ""))
                if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) or video_id in seen:
                    continue
                seen.add(video_id)
                item = dict(entry)
                duration = _integer(item.get("duration"))
                if duration is not None and not 0 < duration <= 180:
                    continue
                url = f"https://www.youtube.com/watch?v={video_id}"
                if attempts < max(limit, 4):
                    attempts += 1
                    try:
                        item.update(self._extract(url))
                    except TrendDiscoveryError as error:
                        # Search metadata can still supply context without full extraction.
                        if duration is None:
                            failures.append(str(error))
                duration = _integer(item.get("duration"))
                if duration is None or not 0 < duration <= 180 or not item.get("title"):
                    continue
                published = str(item.get("upload_date") or "")
                try:
                    published = (
                        datetime.strptime(published, "%Y%m%d").replace(tzinfo=UTC).isoformat()
                    )
                except ValueError:
                    published = ""
                results.append(
                    SocialReference(
                        id=self.source_id(url),
                        url=url,
                        title=str(item["title"])[:500],
                        channel=str(item.get("channel") or item.get("uploader") or "Unknown")[:200],
                        duration_seconds=duration,
                        view_count=_integer(item.get("view_count")),
                        published_at=published or None,
                        description=str(item.get("description") or "")[:6000],
                        transcript=self._transcript(item),
                        basis="YouTube search metadata and available captions; no visual analysis",
                    )
                )
                if len(results) >= limit:
                    return results
            if results:
                return results
        if failures:
            raise TrendDiscoveryError(failures[0])
        return results

    @staticmethod
    def _transcript(item: dict[str, object]) -> str:
        for key in ("subtitles", "automatic_captions"):
            captions = item.get(key)
            if not isinstance(captions, dict):
                continue
            tracks = captions.get("en") or captions.get("en-orig") or []
            if not isinstance(tracks, list):
                continue
            for track in tracks:
                if not isinstance(track, dict) or track.get("ext") != "json3":
                    continue
                try:
                    url = validate_public_media_url(str(track["url"]), ("youtube.com",))
                    with (
                        httpx.Client(timeout=15, follow_redirects=False) as client,
                        client.stream("GET", url) as response,
                    ):
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 500_000:
                                return ""
                    payload = json.loads(data)
                    return " ".join(
                        str(segment.get("utf8", ""))
                        for event in payload.get("events", [])
                        for segment in event.get("segs", [])
                    )[:12000]
                except (httpx.HTTPError, MediaError, ValueError, KeyError, TypeError):
                    continue
        return ""

    def _public_results(self, query: str) -> list[dict[str, object]]:
        if self.search_url:
            with httpx.Client(timeout=20) as client:
                response = client.get(self.search_url, params={"q": query, "format": "json"})
                response.raise_for_status()
            return [
                item for item in response.json().get("results", [])[:15] if isinstance(item, dict)
            ]
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException

        try:
            return list(
                DDGS(timeout=12).text(query, max_results=12, backend="google,bing,duckduckgo,brave")
            )
        except DDGSException as error:
            if str(error) == "No results found.":
                return []
            raise TrendDiscoveryError(
                "Public search is unavailable or rate limited. "
                "Retry shortly or configure another search provider."
            ) from error

    @staticmethod
    def _reference_url(platform: Platform, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or parsed.port not in (None, 443)
            ):
                return False
        except ValueError:
            return False
        hosts = {
            "youtube": ("youtube.com", "youtu.be"),
            "instagram": ("instagram.com",),
            "facebook": ("facebook.com", "fb.watch"),
            "x": ("x.com", "twitter.com"),
            "tiktok": ("tiktok.com",),
        }[platform]
        if not any(
            parsed.hostname == h or (parsed.hostname or "").endswith("." + h) for h in hosts
        ):
            return False
        if platform == "instagram":
            return bool(re.search(r"/(?:reel|reels)/[^/]+", parsed.path))
        if platform == "facebook":
            return (
                bool(re.search(r"/(?:reel|videos|share/[rv])/[^/]+", parsed.path))
                or (parsed.path.rstrip("/") == "/watch" and "v=" in parsed.query)
                or parsed.hostname == "fb.watch"
            )
        if platform == "x":
            return bool(re.search(r"/[^/]+/status/\d+", parsed.path))
        if platform == "tiktok":
            return "/video/" in parsed.path
        # A canonical Shorts URL identifies its format even when full metadata is unavailable.
        return bool(re.search(r"/shorts/[a-zA-Z0-9_-]{11}(?:/|$)", parsed.path))

    def _public_search(self, platform: Platform, niche: str, prompt: str) -> list[SocialReference]:
        sites = {
            "youtube": "site:youtube.com/shorts",
            "instagram": "site:instagram.com/reel",
            "facebook": "site:facebook.com",
            "x": "site:x.com",
            "tiktok": "site:tiktok.com",
        }
        for query in search_queries(niche, prompt):
            items = self._public_results(f"{sites[platform]} {query}")
            results: list[SocialReference] = []
            for item in items:
                url = str(item.get("url") or item.get("href") or "")
                if (
                    not self._reference_url(platform, url)
                    or not item.get("title")
                    or any(r.url == url for r in results)
                ):
                    continue
                description = str(item.get("content") or item.get("body") or "")
                results.append(
                    SocialReference(
                        id=self.source_id(url),
                        url=url,
                        title=str(item["title"])[:500],
                        platform=platform,
                        description=unescape(re.sub(r"<[^>]+>", " ", description))[:6000],
                        basis=(
                            "Public indexed reference excerpt; "
                            "duration, engagement and transcript unverified"
                        ),
                    )
                )
                if len(results) == 3:
                    return results
            if results:
                return results
        return []

    def search_platform(self, platform: Platform, niche: str, prompt: str) -> list[SocialReference]:
        failure = None
        if platform == "youtube":
            try:
                results = self.search(niche, prompt, limit=3)
                if results:
                    return results
            except TrendDiscoveryError as error:
                failure = error
        try:
            results = self._public_search(platform, niche, prompt)
        except (TrendDiscoveryError, httpx.HTTPError) as error:
            if failure:
                raise TrendDiscoveryError(
                    f"{failure} Public search fallback also failed."
                ) from error
            raise
        if not results and failure:
            raise failure
        return results

    @staticmethod
    def source_id(url: str) -> str:
        return fingerprint(url)[:16]


def _integer(value: object) -> int | None:
    try:
        return (
            max(0, int(value))
            if isinstance(value, int | float)
            else max(0, int(str(value)))
            if value is not None
            else None
        )
    except (ValueError, OverflowError):
        return None
