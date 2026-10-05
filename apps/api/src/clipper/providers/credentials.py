from __future__ import annotations

import json
import os
from pathlib import Path

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
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(
            {
                "refresh_token": connection.refresh_token,
                "access_token": connection.access_token,
                "external_account_id": connection.external_account_id,
            }
        ).encode()
        target = self._directory / f"{account_id}.token"
        target.write_bytes(self._cipher().encrypt(payload))
        target.chmod(0o600)

    def load(self, account_id: str) -> OAuthConnection | None:
        target = self._directory / f"{account_id}.token"
        if not target.exists():
            return None
        try:
            payload = json.loads(self._cipher().decrypt(target.read_bytes()))
            return OAuthConnection(
                refresh_token=str(payload.get("refresh_token", "")),
                access_token=str(payload.get("access_token", "")),
                external_account_id=str(payload.get("external_account_id", "")),
            )
        except (InvalidToken, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError("stored publishing credentials could not be read") from error

    def delete(self, account_id: str) -> None:
        target = self._directory / f"{account_id}.token"
        if target.exists():
            target.unlink()

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
