from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from clipper.domain.editing_plan import CaptionConfig, EditingPlanV1
from clipper.editorial import PublishRecommendation, recommend_for_publishing
from clipper.publishing import PublishingPlatform

SocialPlatform = PublishingPlatform


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    status: str
    progress: float
    attempts: int
    error: dict[str, object] | None


class MetricSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recorded_at: datetime
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_seconds: float | None
    followers_gained: int
    affiliate_clicks: int
    conversions: int
    revenue: float
    currency: str


class PublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    platform: str
    status: str
    post_url: str | None
    title: str
    description: str
    published_at: datetime | None
    created_at: datetime
    social_account_id: str | None
    account_label: str | None
    account_username: str | None
    provider_publication_id: str | None
    metric_snapshots: list[MetricSnapshotResponse]


class ClipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    approval_status: str
    plan: EditingPlanV1
    preview_path: str | None
    final_path: str | None
    publications: list[PublicationResponse]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def publish_recommendation(self) -> PublishRecommendation:
        return recommend_for_publishing(self.plan)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    original_filename: str
    status: str
    duration_seconds: float | None
    authorization_confirmed_at: datetime
    created_at: datetime
    stages: list[StageResponse]
    clips: list[ClipResponse]


class ApprovalRequest(BaseModel):
    approved: bool


class ProcessRequest(BaseModel):
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


class ProjectUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class UrlImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2_048)
    authorization_confirmed: bool


class ClipStyleRequest(BaseModel):
    caption_config: CaptionConfig
    frame_style: Literal["blurred_background", "center_crop"]


class PublicationCreateRequest(BaseModel):
    platform: SocialPlatform
    social_account_id: str | None = Field(default=None, max_length=36)
    status: Literal["ready", "published", "failed"] = "published"
    post_url: str | None = Field(default=None, max_length=2_048, pattern=r"^https://")
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5_000)
    published_at: datetime | None = None


class AutomaticPublicationRequest(BaseModel):
    social_account_id: str = Field(max_length=36)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5_000)
    privacy_status: Literal["public", "unlisted", "friends", "private"] = "public"


class MetricCreateRequest(BaseModel):
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    watch_time_seconds: float | None = Field(default=None, ge=0)
    followers_gained: int = Field(default=0, ge=0)
    affiliate_clicks: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0, ge=0)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")


class SocialAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    platform: SocialPlatform
    label: str
    username: str
    profile_url: str | None
    default_hashtags: list[str]
    default_cta: str
    default_campaign_url: str | None
    currency: str
    connection_status: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SocialAccountCreateRequest(BaseModel):
    platform: SocialPlatform
    label: str = Field(min_length=1, max_length=100)
    username: str = Field(default="", max_length=100)
    profile_url: str | None = Field(default=None, max_length=2_048, pattern=r"^https://")
    default_hashtags: list[str] = Field(default_factory=list, max_length=30)
    default_cta: str = Field(default="", max_length=500)
    default_campaign_url: str | None = Field(default=None, max_length=2_048, pattern=r"^https://")
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    is_default: bool = False


class SocialAccountUpdateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    username: str = Field(default="", max_length=100)
    profile_url: str | None = Field(default=None, max_length=2_048, pattern=r"^https://")
    default_hashtags: list[str] = Field(default_factory=list, max_length=30)
    default_cta: str = Field(default="", max_length=500)
    default_campaign_url: str | None = Field(default=None, max_length=2_048, pattern=r"^https://")
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    is_default: bool = False


class PublishingCapabilitiesResponse(BaseModel):
    youtube_configured: bool
    automatic_platforms: list[SocialPlatform]
    configured_platforms: list[SocialPlatform]


class ApiConnectionRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=8_192)
    refresh_token: str = Field(default="", max_length=8_192)
    external_account_id: str = Field(default="", max_length=255)


class HealthResponse(BaseModel):
    status: str
    ffmpeg: bool
    ffprobe: bool
    editorial_provider: str
    transcription_provider: str
