import socket
from collections.abc import Callable, Sequence
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

from clipper.media.errors import MediaError

AddressResolver = Callable[[str, int, int, int], Sequence[tuple[object, ...]]]


def validate_public_media_url(
    value: str,
    allowed_hosts: Sequence[str],
    resolver: AddressResolver = socket.getaddrinfo,
) -> str:
    """Return a normalized HTTPS URL after host allowlist and DNS safety checks."""

    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise MediaError("media URL must be a valid HTTPS URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise MediaError("media URL port is invalid") from error
    if parsed.username or parsed.password or port not in (None, 443):
        raise MediaError("media URL credentials and custom ports are not allowed")

    hostname = parsed.hostname.rstrip(".").lower()
    normalized_hosts = tuple(host.rstrip(".").lower() for host in allowed_hosts if host.strip())
    if not any(hostname == host or hostname.endswith(f".{host}") for host in normalized_hosts):
        raise MediaError("media URL host is not enabled for import")

    try:
        addresses = resolver(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except OSError as error:
        raise MediaError("media URL host could not be resolved") from error
    if not addresses:
        raise MediaError("media URL host could not be resolved")
    for address in addresses:
        raw_address = address[4]
        if not isinstance(raw_address, tuple) or not raw_address:
            raise MediaError("media URL resolved to an invalid address")
        resolved = ip_address(str(raw_address[0]))
        if not resolved.is_global:
            raise MediaError("media URL must resolve only to public addresses")

    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))
