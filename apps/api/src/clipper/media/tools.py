import shutil

from clipper.media.errors import MediaError


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise MediaError(f"{name} is required but was not found on PATH; run pnpm doctor")
    return executable
