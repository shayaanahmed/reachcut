from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from clipper.media import StoredUpload
from clipper.persistence import Project, ProjectStatus, now_utc


class ProjectService:
    """Manage project records and their project-owned artifact directories."""

    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()

    def create(
        self,
        session: Session,
        project_id: str,
        title: str,
        original_filename: str,
        stored: StoredUpload,
    ) -> Project:
        project = Project(
            id=project_id,
            title=title.strip(),
            original_filename=original_filename,
            source_path=str(stored.path),
            media_sha256=stored.sha256,
            authorization_confirmed_at=now_utc(),
        )
        session.add(project)
        session.commit()
        return project

    def rename(self, session: Session, project: Project, title: str) -> Project:
        project.title = title.strip()
        session.commit()
        return project

    def delete(self, session: Session, project: Project) -> None:
        if project.status in (ProjectStatus.PROCESSING, "cancel_requested"):
            raise ValueError("active projects cannot be deleted")
        project_root = Path(project.source_path).resolve().parent.parent
        expected_root = self.projects_root / project.id
        if project_root != expected_root:
            raise RuntimeError("project source path is outside its owned directory")
        session.delete(project)
        session.commit()
        shutil.rmtree(project_root, ignore_errors=True)
