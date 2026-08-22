# ADR 0002: SQLite metadata and project-owned artifact directories

Status: accepted

Stage state and artifact metadata live in SQLite; media and large outputs live in project-scoped directories. Database writes use SQLAlchemy 2 and portable column types. This keeps restart recovery simple on one machine and leaves a path to PostgreSQL/object storage without putting video blobs in the database.

