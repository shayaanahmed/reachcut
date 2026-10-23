from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from clipper.config import settings
from clipper.persistence.models import Base

settings.data_dir.mkdir(parents=True, exist_ok=True)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema() -> None:
    Base.metadata.create_all(engine)
    if "processing_mode" not in {
        column["name"] for column in inspect(engine).get_columns("project_jobs")
    }:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE project_jobs ADD COLUMN processing_mode "
                    "VARCHAR(24) NOT NULL DEFAULT 'clips'"
                )
            )

    columns = {column["name"] for column in inspect(engine).get_columns("metric_snapshots")}
    with engine.begin() as connection:
        for name, sql_type in {
            "reach": "BIGINT",
            "sends": "BIGINT",
            "average_watch_seconds": "FLOAT",
            "opening_retention_percent": "FLOAT",
            "completion_rate_percent": "FLOAT",
            "search_views": "BIGINT",
        }.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE metric_snapshots ADD COLUMN {name} {sql_type}")
                )


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
