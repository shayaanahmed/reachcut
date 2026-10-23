"""Evidence contracts and account-relative diagnostics; no platform ranking claims."""

from datetime import datetime
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from clipper.domain.editing_plan import Hashtag
from clipper.publishing.contracts import PublishingPlatform


class AudienceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    audience: str = Field(default="", max_length=500)
    niche: str = Field(default="", max_length=200)
    language: str = Field(default="", max_length=100)
    country: str = Field(default="", max_length=100)


class SearchEvidence(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    observed_at: datetime
    notes: str = Field(min_length=1, max_length=1000)


class GrowthInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    account_id: str | None = None
    profile: AudienceProfile = Field(default_factory=AudienceProfile)
    target_query: str = Field(default="", max_length=200)
    evidence: list[SearchEvidence] = Field(default_factory=list, max_length=20)


class OpeningOption(BaseModel):
    opening_line: str = Field(min_length=1, max_length=300)
    first_frame: str = Field(min_length=1, max_length=300)


class PlatformCopy(BaseModel):
    platform: PublishingPlatform
    title: str = Field(min_length=1, max_length=100)
    caption: str = Field(min_length=1, max_length=2000)
    cover_text: str = Field(min_length=1, max_length=100)
    hashtags: list[Hashtag] = Field(default_factory=list, max_length=5)


class GrowthCreative(BaseModel):
    openings: list[OpeningOption] = Field(min_length=3, max_length=3)
    packages: list[PlatformCopy] = Field(min_length=1, max_length=5)
    experiment: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_platforms(self) -> "GrowthCreative":
        if len({copy.platform for copy in self.packages}) != len(self.packages):
            raise ValueError("Use one publishing package per platform")
        return self


class GrowthBrief(GrowthInput):
    automatic: bool = False
    creative: GrowthCreative | None = None


class PostObservation(BaseModel):
    publication_id: str
    clip_id: str
    project_id: str
    title: str
    platform: str
    account_id: str | None
    published_at: datetime
    recorded_at: datetime
    views: int
    opening_retention_percent: float | None = None
    completion_rate_percent: float | None = None
    average_watch_seconds: float | None = None
    reach: int | None = None
    sends: int | None = None
    search_views: int | None = None


def age_bucket(post: PostObservation) -> int:
    hours = max(0, (post.recorded_at - post.published_at).total_seconds() / 3600)
    return 0 if hours < 24 else 1 if hours < 168 else 2 if hours < 720 else 3


def diagnose(post: PostObservation, peers: list[PostObservation]) -> dict[str, object]:
    # A publication may have many cumulative snapshots: count it once at a similar age.
    comparable: dict[str, PostObservation] = {}
    for peer in peers:
        if (
            post.account_id
            and peer.account_id == post.account_id
            and peer.platform == post.platform
            and peer.publication_id != post.publication_id
            and peer.published_at < post.published_at
            and age_bucket(peer) == age_bucket(post)
        ):
            previous = comparable.get(peer.publication_id)
            if previous is None or abs(
                (peer.recorded_at - peer.published_at) - (post.recorded_at - post.published_at)
            ) < abs(
                (previous.recorded_at - previous.published_at)
                - (post.recorded_at - post.published_at)
            ):
                comparable[peer.publication_id] = peer
    cohort = list(comparable.values())
    baseline = float(median(p.views for p in cohort)) if len(cohort) >= 5 else None
    findings: list[str] = []
    actions: list[str] = []
    if baseline is None:
        findings.append(
            "Need five earlier posts from this account at a similar age for a baseline."
        )
    else:
        findings.append(
            f"Account median: {baseline:g} views across {len(cohort)} earlier posts "
            "at a similar age."
        )
    if post.views < 100:
        findings.append("Small sample: treat any diagnosis as tentative.")
    for field, label, action in (
        (
            "opening_retention_percent",
            "Opening retention",
            "Test a clearer first frame and opening line.",
        ),
        (
            "completion_rate_percent",
            "Completion rate",
            "Bring the payoff forward and shorten the middle.",
        ),
    ):
        value = getattr(post, field)
        measured = [
            getattr(p, field) for p in cohort if getattr(p, field) is not None and p.views >= 100
        ]
        if value is not None and post.views >= 100 and len(measured) >= 5:
            typical = median(measured)
            findings.append(f"{label}: {value:g}% versus account median {typical:g}%.")
            if value < typical:
                actions.append(action)
    missing = [
        label
        for field, label in (
            ("opening_retention_percent", "opening retention"),
            ("completion_rate_percent", "completion rate"),
            ("search_views", "search traffic"),
        )
        if getattr(post, field) is None
    ]
    if missing:
        findings.append("Not measured: " + ", ".join(missing) + ".")
    if not actions:
        actions.append(
            "Test one change to the opening or topic across comparable posts; "
            "views alone cannot explain a stall."
        )
    return {
        **post.model_dump(mode="json"),
        "baseline_views": baseline,
        "baseline_posts": len(cohort),
        "relative_views": post.views / baseline if baseline else None,
        "sends_per_reach": post.sends / post.reach
        if post.sends is not None and post.reach
        else None,
        "search_share": post.search_views / post.views
        if post.search_views is not None and post.views
        else None,
        "findings": findings,
        "actions": actions,
        "confidence": "tentative" if post.views < 100 or baseline is None else "observational",
    }


class AutomaticGrowthDecision(BaseModel):
    profile: AudienceProfile
    target_query: str = Field(min_length=1, max_length=200)
    creative: GrowthCreative
    selected_opening: int = Field(ge=0, le=2)
    reasoning: str = Field(min_length=1, max_length=1000)
