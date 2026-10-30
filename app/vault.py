"""Encrypted storage for portal IDs, receipts and uploaded documents."""
import base64
import binascii
import hashlib
import hmac
import os
import re
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.db import connect
from contracts.vault import Receipt

NONCE_BYTES = 12


def decode_master_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("VAULT_KEY must be base64") from exc
    if len(key) != 32:
        raise ValueError("VAULT_KEY must decode to 32 bytes")
    return key


def derive_key(master: bytes, purpose: str) -> bytes:
    """Give each store its own key, so one setting covers all of them."""
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()
    ).derive(master)


def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)


class Vault:
    def __init__(self, path: Path, master_key: bytes) -> None:
        self._key = derive_key(master_key, "vault")
        self._db = connect(path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS vault (
                owner TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                PRIMARY KEY (owner, kind, name)
            )"""
        )
        self._db.commit()

    def _owner(self, owner: str) -> str:
        """Hash the owner, so the table does not list phone numbers."""
        return hmac.new(self._key, owner.encode(), hashlib.sha256).hexdigest()

    def _put(self, owner: str, kind: str, name: str, value: str) -> None:
        owner_id = self._owner(owner)
        blob = _encrypt(self._key, value.encode(), f"{owner_id}|{kind}|{name}".encode())
        self._db.execute(
            "INSERT OR REPLACE INTO vault (owner, kind, name, ciphertext) "
            "VALUES (?, ?, ?, ?)",
            (owner_id, kind, name, blob),
        )
        self._db.commit()

    def _get(self, owner: str, kind: str, name: str) -> str | None:
        owner_id = self._owner(owner)
        row = self._db.execute(
            "SELECT ciphertext FROM vault WHERE owner = ? AND kind = ? AND name = ?",
            (owner_id, kind, name),
        ).fetchone()
        if row is None:
            return None
        aad = f"{owner_id}|{kind}|{name}".encode()
        return _decrypt(self._key, row[0], aad).decode()

    def put_portal_id(self, owner: str, portal_id: str, value: str) -> None:
        self._put(owner, "portal_id", portal_id, value)

    def get_portal_id(self, owner: str, portal_id: str) -> str | None:
        return self._get(owner, "portal_id", portal_id)

    def put_receipt(self, owner: str, receipt: Receipt) -> None:
        self._put(
            owner,
            "receipt",
            f"{receipt.portal_id}:{receipt.receipt_number}",
            receipt.model_dump_json(),
        )

    def list_receipts(self, owner: str) -> list[Receipt]:
        rows = self._db.execute(
            "SELECT name FROM vault WHERE owner = ? AND kind = 'receipt' ORDER BY name",
            (self._owner(owner),),
        ).fetchall()
        return [
            Receipt.model_validate_json(self._get(owner, "receipt", name))
            for (name,) in rows
        ]

    def close(self) -> None:
        self._db.close()


class FileStore:
    """Keeps uploaded documents and screenshots encrypted on disk."""

    def __init__(self, directory: Path, master_key: bytes) -> None:
        self._key = derive_key(master_key, "files")
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path(self, ref: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", ref):
            raise ValueError("Invalid file reference")
        return self._directory / f"{ref}.bin"

    def put(self, data: bytes, mime_type: str) -> str:
        ref = uuid.uuid4().hex
        plaintext = mime_type.encode() + b"\0" + data
        self._path(ref).write_bytes(_encrypt(self._key, plaintext, ref.encode()))
        return ref

    def get(self, ref: str) -> tuple[bytes, str]:
        blob = self._path(ref).read_bytes()
        mime_type, data = _decrypt(self._key, blob, ref.encode()).split(b"\0", 1)
        return data, mime_type.decode()
