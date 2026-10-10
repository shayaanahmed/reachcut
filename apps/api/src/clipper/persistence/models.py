from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    stages: Mapped[list[StageRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    clips: Mapped[list[Clip]] = relationship(back_populates="project", cascade="all, delete-orphan")


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
    publications: Mapped[list[Publication]] = relationship(
        back_populates="clip", cascade="all, delete-orphan"
    )


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
    followers_gained: Mapped[int] = mapped_column(Integer, default=0)
    affiliate_clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    publication: Mapped[Publication] = relationship(back_populates="metric_snapshots")


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    platform: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(100), default="")
    profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    default_hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_cta: Mapped[str] = mapped_column(String(500), default="")
    default_campaign_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    connection_status: Mapped[str] = mapped_column(String(32), default="manual")
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )
    publication_links: Mapped[list[PublicationAccountLink]] = relationship(back_populates="account")


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
