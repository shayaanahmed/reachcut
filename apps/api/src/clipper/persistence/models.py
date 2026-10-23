from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ProjectStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    REVIEW = "review"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(1024))
    media_sha256: Mapped[str] = mapped_column(String(64))
    authorization_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.CREATED)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_info: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    transcript: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    job: Mapped[ProjectJob | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    stages: Mapped[list[StageRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    clips: Mapped[list[Clip]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectJob(Base):
    """One durable processing request per project; retries reuse its saved inputs."""

    __tablename__ = "project_jobs"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(64), default="Waiting to start")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    processing_mode: Mapped[str] = mapped_column(
        String(24), default="clips", server_default="clips"
    )
    clip_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    project: Mapped[Project] = relationship(back_populates="job")


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class AutomationPipeline(Base):
    __tablename__ = "automation_pipelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    social_account_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    clip_selection: Mapped[str] = mapped_column(String(16), default="best")
    clip_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    schedule: Mapped[str] = mapped_column(String(16), default="once")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=True)
    title_template: Mapped[str] = mapped_column(String(200), default="{clip_title}")
    description_template: Mapped[str] = mapped_column(Text, default="{hashtags}")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class StageRun(Base):
    __tablename__ = "stage_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=StageStatus.PENDING)
    progress: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cache_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[Project] = relationship(back_populates="stages")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    plan: Mapped[dict[str, object]] = mapped_column(JSON)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending")
    preview_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    final_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    project: Mapped[Project] = relationship(back_populates="clips")
    growth_brief: Mapped[ClipGrowthBrief | None] = relationship(
        cascade="all, delete-orphan", uselist=False
    )
    growth_preparation: Mapped[GrowthPreparation | None] = relationship(
        cascade="all, delete-orphan", uselist=False
    )
    publications: Mapped[list[Publication]] = relationship(
        back_populates="clip", cascade="all, delete-orphan"
    )


class StoryDraft(Base):
    __tablename__ = "story_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class StoryVideo(Base):
    __tablename__ = "story_videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(64))
    aspect_ratio: Mapped[str] = mapped_column(String(8))
    quality: Mapped[str] = mapped_column(String(16))
    target_duration_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(120), default="Queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    plan: Mapped[dict[str, object]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(100), default="ltx-2.5-fast-local")
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    scenes: Mapped[list[StoryVideoScene]] = relationship(
        back_populates="story_video",
        cascade="all, delete-orphan",
        order_by="StoryVideoScene.scene_index",
    )


class StoryVideoScene(Base):
    __tablename__ = "story_video_scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_video_id: Mapped[str] = mapped_column(
        ForeignKey("story_videos.id", ondelete="CASCADE"), index=True
    )
    scene_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    narration: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    reference_image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    story_video: Mapped[StoryVideo] = relationship(back_populates="scenes")


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="ready")
    post_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    clip: Mapped[Clip] = relationship(back_populates="publications")
    growth_context: Mapped[PublicationGrowthContext | None] = relationship(
        cascade="all, delete-orphan", uselist=False
    )
    metric_snapshots: Mapped[list[MetricSnapshot]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="MetricSnapshot.recorded_at",
    )
    account_link: Mapped[PublicationAccountLink | None] = relationship(
        back_populates="publication", cascade="all, delete-orphan", uselist=False
    )
    provider_reference: Mapped[PublicationProviderReference | None] = relationship(
        back_populates="publication", cascade="all, delete-orphan", uselist=False
    )

    management: Mapped[PostManagement | None] = relationship(
        cascade="all, delete-orphan", uselist=False
    )
    changes: Mapped[list[PostChange]] = relationship(cascade="all, delete-orphan")
    failure: Mapped[PublicationFailure | None] = relationship(
        back_populates="publication", cascade="all, delete-orphan", uselist=False
    )

    @property
    def error(self) -> str | None:
        return self.failure.message if self.failure else None

    @property
    def social_account_id(self) -> str | None:
        return self.account_link.social_account_id if self.account_link else None

    @property
    def account_label(self) -> str | None:
        return self.account_link.account_label_snapshot if self.account_link else None

    @property
    def account_username(self) -> str | None:
        return self.account_link.account_username_snapshot if self.account_link else None

    @property
    def provider_publication_id(self) -> str | None:
        return self.provider_reference.external_id if self.provider_reference else None


class PublicationDestination(Base):
    """Reserve a clip/account pair while queued, processing, or published."""

    __tablename__ = "publication_destinations"
    __table_args__ = (UniqueConstraint("clip_id", "social_account_id"),)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"))
    social_account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE")
    )


class PublicationFailure(Base):
    """Keep safe provider diagnostics without altering existing publication columns."""

    __tablename__ = "publication_failures"

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    publication: Mapped[Publication] = relationship(back_populates="failure")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    watch_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sends: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    average_watch_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_retention_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    followers_gained: Mapped[int] = mapped_column(Integer, default=0)
    affiliate_clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    publication: Mapped[Publication] = relationship(back_populates="metric_snapshots")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    issue: Mapped[AccountIssue | None] = relationship(cascade="all, delete-orphan", uselist=False)

    @property
    def health_issue(self) -> str | None:
        return self.issue.message if self.issue else None

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    platform: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(100), default="")
    profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    default_hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_cta: Mapped[str] = mapped_column(String(500), default="")
    default_campaign_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    connection_status: Mapped[str] = mapped_column(String(32), default="disconnected")
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    identity: Mapped[SocialAccountIdentity | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )

    @property
    def external_account_id(self) -> str | None:
        return self.identity.external_account_id if self.identity else None

    @property
    def parent_page_name(self) -> str | None:
        return self.identity.parent_page_name if self.identity else None

    publication_links: Mapped[list[PublicationAccountLink]] = relationship(back_populates="account")


class SocialAccountGroup(Base):
    __tablename__ = "social_account_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    members: Mapped[list[SocialAccountGroupMember]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def account_ids(self) -> list[str]:
        return sorted(member.account_id for member in self.members)


class SocialAccountGroupMember(Base):
    __tablename__ = "social_account_group_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("social_account_groups.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True
    )


class SocialAccountIdentity(Base):
    __tablename__ = "social_account_identities"
    __table_args__ = (UniqueConstraint("platform", "external_account_id"),)

    account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(32))
    external_account_id: Mapped[str] = mapped_column(String(200))
    parent_page_id: Mapped[str] = mapped_column(String(200), default="")
    parent_page_name: Mapped[str] = mapped_column(String(200), default="")
    account: Mapped[SocialAccount] = relationship(back_populates="identity")


class OAuthAccountSelection(Base):
    __tablename__ = "oauth_account_selections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    encrypted_payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PublicationAccountLink(Base):
    __tablename__ = "publication_account_links"

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    social_account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="RESTRICT"), index=True
    )
    account_label_snapshot: Mapped[str] = mapped_column(String(100))
    account_username_snapshot: Mapped[str] = mapped_column(String(100), default="")
    publication: Mapped[Publication] = relationship(back_populates="account_link")
    account: Mapped[SocialAccount] = relationship(back_populates="publication_links")


class PublicationProviderReference(Base):
    __tablename__ = "publication_provider_references"

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    external_id: Mapped[str] = mapped_column(String(255))
    publication: Mapped[Publication] = relationship(back_populates="provider_reference")


class InformativeShort(Base):
    """Additive schema: legacy projects, stories and publication FKs remain intact."""

    __tablename__ = "informative_shorts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    topic: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, object]] = mapped_column(JSON)
    sources: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    script: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    approved_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    phase: Mapped[str] = mapped_column(String(200), default="Review script and sources")
    artifacts: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    usage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    publication_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class ChannelPreset(Base):
    __tablename__ = "channel_presets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    settings: Mapped[dict[str, object]] = mapped_column(JSON)


class PublicationOptions(Base):
    """Persist recoverable upload inputs without altering legacy publication rows."""

    __tablename__ = "publication_options"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    privacy_status: Mapped[str] = mapped_column(String(16))


class GrowthProfile(Base):
    __tablename__ = "growth_profiles"
    account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class ClipGrowthBrief(Base):
    __tablename__ = "clip_growth_briefs"
    clip_id: Mapped[str] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PublicationGrowthContext(Base):
    __tablename__ = "publication_growth_contexts"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class GrowthPreparation(Base):
    __tablename__ = "growth_preparations"
    clip_id: Mapped[str] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AccountIssue(Base):
    __tablename__ = "account_issues"
    account_id: Mapped[str] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    message: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PostManagement(Base):
    __tablename__ = "post_management"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(24), default="idle")
    action: Mapped[str] = mapped_column(String(24), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PostChange(Base):
    __tablename__ = "post_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    publication_id: Mapped[str] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(24))
    before: Mapped[dict[str, object]] = mapped_column(JSON)
    after: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SourceWorkflowRun(Base):
    __tablename__ = "source_workflow_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    target_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clip_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    narration_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
