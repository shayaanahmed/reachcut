from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CountryOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=r"^[A-Z]{2}$")
    name: str = Field(min_length=1, max_length=80)


class TrendTopic(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=200)
    approximate_traffic: str | None = Field(default=None, max_length=80)
    news_title: str | None = Field(default=None, max_length=300)
    news_url: HttpUrl | None = None


class SourceCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    channel: str | None = Field(default=None, max_length=200)
    thumbnail_url: HttpUrl | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    view_count: int | None = Field(default=None, ge=0)
    published_at: datetime | None = None
    opportunity_type: Literal["trending_interview", "upcoming_interview"]
    topic: str = Field(min_length=1, max_length=200)
    is_upcoming: bool = False
    source_score: int = Field(ge=0, le=100)


class DiscoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country: CountryOption
    query: str | None = Field(default=None, max_length=120)
    category: str = Field(default="trending", min_length=1, max_length=40)
    fetched_at: datetime
    topics: list[TrendTopic]
    sources: list[SourceCandidate]
    note: str = (
        "Sources are from the last 7 days or genuinely upcoming. "
        "Confirm media rights before importing."
    )
