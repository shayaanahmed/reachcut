"""Shared social-reference metadata for content-series style research."""

from typing import Literal

from pydantic import Field

from clipper.shorts.contracts import Strict

Platform = Literal["youtube", "instagram", "tiktok", "facebook", "x"]


class SocialReference(Strict):
    id: str
    url: str = Field(pattern=r"^https://", max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    platform: Platform = "youtube"
    channel: str = "Unknown"
    duration_seconds: int | None = None
    view_count: int | None = None
    published_at: str | None = None
    description: str = Field(default="", max_length=6000)
    transcript: str = Field(default="", max_length=12000)
    basis: str
