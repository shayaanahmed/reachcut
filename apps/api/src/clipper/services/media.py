"""Compatibility imports for :mod:`clipper.media`."""

from clipper.media import (
    MediaError,
    StoredUpload,
    detect_container,
    probe_media,
    require_tool,
    safe_filename,
    store_upload,
)

__all__ = [
    "MediaError",
    "StoredUpload",
    "detect_container",
    "probe_media",
    "require_tool",
    "safe_filename",
    "store_upload",
]
