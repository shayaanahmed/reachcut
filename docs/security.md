# Security and media rights

Only submit media you own, license, or are authorized to repurpose. Accessibility of a URL is not evidence of publication rights. Clipper records the user's confirmation and source provenance; it does not determine ownership.

Uploads are streamed with byte limits, sanitized names, signature checks, and project-generated storage paths. URL import is designed around an allowlist, DNS resolution checks, private/link-local address blocking, redirect revalidation, and a downloader subprocess with fixed arguments; trusted local-network access must be an explicit opt-in. The first slice exposes upload only until that full policy is integrated.

Media tools run with argument arrays and `shell=False`. Plans reject extra keys, unknown effects, invalid source-relative timestamps, and unsafe effect values. Logs redact credentials and avoid raw private paths. Secrets belong in environment variables or the future OS-keychain credential store and must never enter manifests.

The local HTTP service binds to loopback by default. Do not expose it to a network without authentication, TLS, request limits, and a reverse proxy. Configure cleanup and backups for `CLIPPER_DATA_DIR`; source and intermediate media can be sensitive.

Run `uv run pip-audit` and `pnpm audit` in a networked development environment. Review model and asset licenses before distribution. Publishing must use official APIs, encrypted OAuth tokens, explicit clip approval, and a separate user-confirmed publish action.

