from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from clipper.config import settings


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


settings.data_dir.mkdir(parents=True, exist_ok=True)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
