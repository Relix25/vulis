"""Storage backend interface and value types.

Every concrete backend (SMB, local FS, S3, ...) implements the
``StorageBackend`` protocol. Service code depends on this protocol only,
never on a concrete class.

Design notes
------------
- Keys are forward-slash-joined strings, **POSIX-style**, regardless of the
  underlying OS. Backends translate keys to the native form (e.g. backslash
  on SMB when needed).
- Backends raise the exceptions from ``vulis_core.exceptions``:
  ``ObjectNotFoundError``, ``StorageError``, ``ChecksumMismatchError``.
- ``put_blob`` is content-addressed: it hashes the content and uses the hash
  as the key (``"<algo>/<hex>"``). This deduplicates blobs and makes dataset
  manifests reproducible.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import IO, Any, Protocol, runtime_checkable

from vulis_core.exceptions import ObjectNotFoundError, StorageError

__all__ = [
    "BackendConfig",
    "BackendKind",
    "ObjectInfo",
    "StorageBackend",
    "content_addressed_key",
    "hash_bytes",
    "hash_stream",
]


# ─── Value types ─────────────────────────────────────────────


@dataclass(frozen=True)
class ObjectInfo:
    """Metadata about a stored object."""

    key: str
    size: int
    last_modified: datetime
    etag: str | None = None
    """Opaque object version tag (e.g. SMB ETag, S3 ETag, mtime for local)."""
    content_type: str | None = None
    metadata: dict[str, str] | None = None


# ─── Backend protocol ────────────────────────────────────────


@runtime_checkable
class StorageBackend(Protocol):
    """Backend-agnostic blob store.

    Keys are POSIX-style forward-slash paths. Implementations are NOT
    required to be thread-safe; callers should serialize concurrent access
    to the same backend instance, or use one instance per worker.
    """

    kind: str
    """Short identifier of the backend kind (``"local-fs"``, ``"smb-protocol"``, ...)."""

    # ── writes ────────────────────────────────────────────────
    def put_bytes(self, key: str, data: bytes, *, overwrite: bool = True) -> str:
        """Store ``data`` under ``key``. Returns the key.

        Raises ``AlreadyExistsError`` (from vulis-core) if ``overwrite=False``
        and the key already exists.
        """

    def put_stream(self, key: str, stream: IO[bytes], *, overwrite: bool = True) -> str:
        """Store a binary stream under ``key``. Returns the key."""

    def put_blob(self, data: bytes, *, algo: str = "sha256") -> str:
        """Content-addressed put: hash the content, use the hash as the key.

        Returns the content-addressed key (``"<algo>/<hex>"``). Idempotent:
        calling twice with the same bytes returns the same key.
        """

    # ── reads ─────────────────────────────────────────────────
    def get_bytes(self, key: str) -> bytes:
        """Return the full object content as bytes.

        Raises ``ObjectNotFoundError`` if the key does not exist.
        """

    def get_stream(self, key: str) -> IO[bytes]:
        """Return a readable binary stream for ``key``.

        Caller is responsible for closing the stream (use ``with``).
        """

    # ── metadata ──────────────────────────────────────────────
    def stat(self, key: str) -> ObjectInfo:
        """Return metadata for ``key``. Raises ``ObjectNotFoundError``."""

    def exists(self, key: str) -> bool:
        """Return True if ``key`` exists."""

    # ── listing ───────────────────────────────────────────────
    def list(self, prefix: str = "", *, recursive: bool = True) -> Iterator[ObjectInfo]:
        """Yield objects whose key starts with ``prefix``.

        If ``recursive=False``, only the immediate children of ``prefix`` are
        returned (directory-like listing).
        """

    # ── deletion ──────────────────────────────────────────────
    def delete(self, key: str) -> None:
        """Delete ``key``. Idempotent: missing keys do not raise."""

    # ── lifecycle ─────────────────────────────────────────────
    def close(self) -> None:
        """Release any underlying resources (sessions, sockets, ...)."""


# ─── Configuration ───────────────────────────────────────────


BackendKind = str
"""Backend kind identifier (e.g. ``"smb-protocol"``, ``"local-fs"``)."""


@dataclass(frozen=True)
class BackendConfig:
    """Declarative configuration for a storage backend.

    Use ``build_backend`` (in ``factory.py``) to instantiate the right
    backend from a config + secrets.
    """

    backend: BackendKind
    root_prefix: str = ""
    """Optional logical root applied to all keys (e.g. ``"vulis/blobs"``)."""

    # SMB
    smb_host: str | None = None
    smb_share: str | None = None
    smb_username: str | None = None
    smb_password: str | None = None
    smb_domain: str | None = None
    smb_port: int = 445

    # Local FS
    local_root: str | None = None

    # S3
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None


# ─── Content-addressing helpers ──────────────────────────────


def hash_bytes(data: bytes, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    h.update(data)
    return h.hexdigest()


def hash_stream(stream: IO[bytes], algo: str = "sha256") -> str:
    """Hash a stream without loading it entirely in memory."""
    h = hashlib.new(algo)
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()


def content_addressed_key(hex_digest: str, algo: str = "sha256") -> str:
    return f"{algo}/{hex_digest}"


# ─── Shared small helpers used by concrete backends ──────────


def normalize_key(key: str) -> str:
    """Normalize a user-supplied key to a POSIX-style form.

    - strips leading/trailing slashes,
    - converts backslashes to forward slashes (Windows callers often pass
      backslashes by mistake),
    - collapses repeated slashes,
    - resolves ``.`` and ``..`` segments like a POSIX path, but **never**
      allows ``..`` to escape above the root (it is dropped instead, so the
      resulting key always stays inside the store).
    """
    if not key:
        raise StorageError("Empty storage key")
    k = key.replace("\\", "/")
    stack: list[str] = []
    for part in k.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            # Resolve ".." only if it cancels a previous segment; otherwise
            # drop it so we can never escape above the root.
            if stack:
                stack.pop()
            continue
        stack.append(part)
    if not stack:
        raise StorageError(f"Invalid storage key after normalization: {key!r}")
    return "/".join(stack)


def raise_not_found(key: str) -> Any:
    """Convenience to raise ``ObjectNotFoundError`` and satisfy type checkers."""
    raise ObjectNotFoundError(f"Object not found: {key}", details={"key": key})
