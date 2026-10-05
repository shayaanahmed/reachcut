from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.media import StoredUpload
from clipper.persistence import Base
from clipper.projects import ProjectService


def test_project_crud_updates_record_and_removes_owned_artifacts(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = ProjectService(tmp_path / "projects")
    project_id = "project-1"
    source = tmp_path / "projects" / project_id / "source" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x00\x00\x00\x18ftypisom")

    with Session(engine) as session:
        created = service.create(
            session,
            project_id,
            "First title",
            source.name,
            StoredUpload(source, "a" * 64, source.stat().st_size),
        )
        assert created.title == "First title"
        assert service.rename(session, created, "Renamed project").title == "Renamed project"

        service.delete(session, created)

        assert session.get(type(created), project_id) is None
        assert not source.parent.parent.exists()
