import os
from pathlib import Path


def directory_size(path: Path) -> int:
    """Return the logical size of a directory without following symbolic links."""

    total = 0
    try:
        entries = list(os.scandir(path))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_symlink():
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += directory_size(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def project_storage_bytes(
    projects_root: Path,
    project_id: str,
    source_path: str,
) -> int:
    """Measure an owned project directory, returning zero for an invalid path."""

    root = projects_root.resolve()
    expected = root / project_id
    if expected.parent != root:
        return 0
    try:
        project_root = Path(source_path).resolve().parent.parent
    except OSError:
        return 0
    if project_root != expected:
        return 0
    return directory_size(project_root)
