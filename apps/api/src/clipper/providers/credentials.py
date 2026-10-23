from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from cryptography.fernet import Fernet, InvalidToken

from clipper.publishing import OAuthConnection


class CredentialStoreError(RuntimeError):
    pass


class EncryptedCredentialStore:
    """Keep provider refresh tokens encrypted outside the application database."""

    def __init__(self, data_dir: Path) -> None:
        self._directory = data_dir / "credentials"
        self._key_path = data_dir / "credentials.key"

    def save(self, account_id: str, connection: OAuthConnection) -> None:
        with self._locked(account_id):
            self._save(account_id, connection)

    def _save(self, account_id: str, connection: OAuthConnection) -> None:
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(asdict(connection)).encode()
        target = self._directory / f"{account_id}.token"
        with NamedTemporaryFile(dir=self._directory, delete=False) as temporary:
            temporary.write(self._cipher().encrypt(payload))
            temporary_path = Path(temporary.name)
        try:
            temporary_path.chmod(0o600)
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)

    def save_if_present(
        self, account_id: str, connection: OAuthConnection, expected: OAuthConnection
    ) -> bool:
        """Persist upload results without undoing a disconnect made during upload."""
        with self._locked(account_id):
            if self.load(account_id) != expected:
                return False
            self._save(account_id, connection)
            return True

    def load(self, account_id: str) -> OAuthConnection | None:
        target = self._directory / f"{account_id}.token"
        if not target.exists():
            return None
        try:
            payload = json.loads(self._cipher().decrypt(target.read_bytes()))
            return OAuthConnection(
                refresh_token=str(payload.get("refresh_token", "")),
                management_access_token=str(payload.get("management_access_token", "")),
                access_token=str(payload.get("access_token", "")),
                external_account_id=str(payload.get("external_account_id", "")),
                display_name=str(payload.get("display_name", "")),
                username=str(payload.get("username", "")),
                profile_url=str(payload.get("profile_url", "")),
                parent_page_id=str(payload.get("parent_page_id", "")),
                parent_page_name=str(payload.get("parent_page_name", "")),
                granted_scopes=tuple(payload["granted_scopes"])
                if isinstance(payload.get("granted_scopes"), list)
                else None,
                access_token_expires_at=(
                    float(payload["access_token_expires_at"])
                    if payload.get("access_token_expires_at") is not None
                    else None
                ),
            )
        except (InvalidToken, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError("stored publishing credentials could not be read") from error

    def refresh(
        self, account_id: str, renew: Callable[[OAuthConnection], OAuthConnection]
    ) -> OAuthConnection:
        """Serialize rotation across workers and save before returning credentials."""
        with self._locked(account_id):
            connection = self.load(account_id)
            if connection is None:
                raise CredentialStoreError("publishing account is no longer connected")
            updated = renew(connection)
            self._save(account_id, updated)
            return updated

    def delete(self, account_id: str) -> None:
        with self._locked(account_id):
            (self._directory / f"{account_id}.token").unlink(missing_ok=True)

    @contextmanager
    def _locked(self, account_id: str) -> Iterator[None]:
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self._directory / f"{account_id}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def seal_state(self, account_id: str) -> str:
        return self._cipher().encrypt(account_id.encode()).decode()

    def open_state(self, state: str, *, ttl_seconds: int = 600) -> str:
        try:
            return self._cipher().decrypt(state.encode(), ttl=ttl_seconds).decode()
        except InvalidToken as error:
            raise CredentialStoreError("authorization state is invalid or expired") from error

    def _cipher(self) -> Fernet:
        return Fernet(self._key())

    def _key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        descriptor = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(key)
        return key
