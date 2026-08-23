"""Backward-compatible persistence imports.

New code should import from :mod:`clipper.persistence`.
"""

from clipper.persistence import (
    Base,
    Clip,
    Project,
    ProjectStatus,
    SessionLocal,
    StageRun,
    StageStatus,
    create_schema,
    engine,
    get_session,
    now_utc,
)

__all__ = [
    "Base",
    "Clip",
    "Project",
    "ProjectStatus",
    "SessionLocal",
    "StageRun",
    "StageStatus",
    "create_schema",
    "engine",
    "get_session",
    "now_utc",
]
