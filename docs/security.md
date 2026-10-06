# Security and media rights

Only submit media you own, license, or are authorized to repurpose. Accessibility of a URL is not evidence of publication rights. ReachCut records the user's confirmation and source provenance; it does not determine ownership.

Uploads are streamed with byte limits, sanitized names, signature checks, and project-generated storage paths. URL import requires HTTPS, an explicit host allowlist, DNS resolution checks, private/link-local address blocking, a single-item yt-dlp download, and a downloader subprocess with fixed arguments. Imported files receive the same size, signature, project-directory, probe, and rights-confirmation controls as uploads. Add hosts deliberately through `CLIPPER_YT_DLP_ALLOWED_HOSTS`; trusted local-network targets are not supported.

Media tools run with argument arrays and `shell=False`. Plans reject extra keys, unknown effects, invalid source-relative timestamps, and unsafe effect values. Logs redact credentials and avoid raw private paths. Secrets belong in environment variables or the future OS-keychain credential store and must never enter manifests.

Social-account rows store only public profile metadata, publishing defaults, and connection status. Do not store platform passwords, browser cookies, access tokens, or refresh tokens in account records. Provider access and refresh tokens are encrypted in the private data directory with a separately stored local Fernet key; both must remain private and must be backed up together.

The local HTTP service binds to loopback by default. Do not expose it to a network without authentication, TLS, request limits, and a reverse proxy. Configure cleanup and backups for `CLIPPER_DATA_DIR`; source and intermediate media can be sensitive.

Run `uv run pip-audit` and `pnpm audit` in a networked development environment. Review model and asset licenses before distribution. Publishing must use official APIs, encrypted OAuth tokens, explicit clip approval, and a separate user-confirmed publish action.
