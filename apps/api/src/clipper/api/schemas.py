from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from clipper.domain.editing_plan import (
    CaptionConfig,
    ClipType,
    ContentMode,
    EditingPlanV1,
    Effect,
    EnhancementLevel,
    TimeRange,
    TrackingStrategy,
    TransitionStyle,
    TranslationMode,
)
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
    clip_types: list[ClipType] = Field(default_factory=list, max_length=9)


class ClipTypeSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clip_type: ClipType
    score: int
    reason: str


class ProjectUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class UrlImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2_048)
    authorization_confirmed: bool


class ClipStyleRequest(BaseModel):
    caption_config: CaptionConfig
    frame_style: Literal["blurred_background", "center_crop"]
    crop_focus_x: float = Field(default=0.5, ge=0, le=1)
    crop_focus_y: float = Field(default=0.5, ge=0, le=1)
    source_slices: list[TimeRange] | None = Field(default=None, min_length=1, max_length=12)
    hook_text: str | None = Field(default=None, min_length=1, max_length=160)
    hook_render: bool | None = None
    content_mode: ContentMode = ContentMode.AUTO
    enhancement_level: EnhancementLevel = EnhancementLevel.CLEAN
    tracking_enabled: bool | None = None
    tracking_strategy: TrackingStrategy | None = None
    transition_style: TransitionStyle = TransitionStyle.CUT
    transition_duration_seconds: float = Field(default=0.2, ge=0.05, le=1)
    cta_text: str | None = Field(default=None, min_length=1, max_length=160)
    cta_render: bool | None = None
    cta_style: Literal["follow", "comment", "part_two", "profile", "product", "campaign"] = "follow"
    effects: list[Effect] | None = Field(default=None, max_length=40)
    audio_track_index: int = Field(default=0, ge=0, le=32)


class CaptionTranslationRequest(BaseModel):
    target_language: str = Field(pattern=r"^[A-Za-z]{2,3}$")
    mode: TranslationMode = TranslationMode.TRANSLATED


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


class AccountConnectionReadinessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    account_id: str
    platform: SocialPlatform
    provider_configured: bool
    credentials_available: bool
    publishing_ready: bool
    issues: list[str]


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


class RuntimeSettingsResponse(BaseModel):
    ollama_base_url: str
    editorial_model: str


class RuntimeSettingsUpdateRequest(BaseModel):
    ollama_base_url: str = Field(min_length=8, max_length=2_048)
    editorial_model: str = Field(min_length=1, max_length=200)


class OllamaModelsResponse(BaseModel):
    models: list[str]


class AutomationPipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    project_id: str
    social_account_ids: list[str]
    clip_selection: Literal["all", "best"]
    clip_types: list[ClipType]
    schedule: Literal["once", "daily", "weekly"]
    next_run_at: datetime
    status: str
    auto_approve: bool
    title_template: str
    description_template: str
    last_run_at: datetime | None
    last_error: str | None
    created_at: datetime


class AutomationPipelineCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str = Field(min_length=1, max_length=36)
    social_account_ids: list[str] = Field(min_length=1, max_length=10)
    clip_selection: Literal["all", "best"] = "best"
    clip_types: list[ClipType] = Field(default_factory=list, max_length=9)
    schedule: Literal["once", "daily", "weekly"] = "once"
    next_run_at: datetime
    title_template: str = Field(default="{clip_title}", min_length=1, max_length=200)
    description_template: str = Field(default="{hashtags}", max_length=5_000)


class AutomationPipelineActiveRequest(BaseModel):
    active: bool
