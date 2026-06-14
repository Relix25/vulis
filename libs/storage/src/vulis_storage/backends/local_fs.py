"""Local filesystem backend.

Used for dev, tests, and single-node deployments. Implements the
``StorageBackend`` protocol on top of a plain directory.

Keys are POSIX-style; on Windows they are translated to native paths via
``pathlib``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from vulis_core.exceptions import AlreadyExistsError, StorageError

from vulis_storage.base import (
    ObjectInfo,
    content_addressed_key,
    hash_bytes,
    normalize_key,
    raise_not_found,
)

__all__ = ["LocalFSBackend"]


class LocalFSBackend:
    """Storage backend backed by a local directory.

    Parameters
    ----------
    root:
        Directory that backs the store. Created if missing.
    root_prefix:
        Optional logical prefix applied to all keys (joined with ``root``).
    """

    kind = "local-fs"

    def __init__(self, root: str | os.PathLike[str], *, root_prefix: str = "") -> None:
        base = Path(root).resolve()
        if root_prefix:
            base = base / normalize_key(root_prefix)
        self._root = base
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StorageError(
                f"Cannot initialize LocalFS root at {self._root}", details={"error": str(e)}
            ) from e

    # ─── path helpers ─────────────────────────────────────────
    def _path_for(self, key: str) -> Path:
        nk = normalize_key(key)
        p = (self._root / nk).resolve()
        # Defense-in-depth against path traversal beyond root_prefix.
        try:
            p.relative_to(self._root)
        except ValueError as e:
            raise StorageError(f"Key escapes storage root: {key!r}") from e
        return p

    # ─── writes ───────────────────────────────────────────────
    def put_bytes(self, key: str, data: bytes, *, overwrite: bool = True) -> str:
        p = self._path_for(key)
        if not overwrite and p.exists():
            raise AlreadyExistsError(f"Object already exists: {key}", details={"key": key})
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, p)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Failed to write {key}", details={"error": str(e)}) from e
        return key

    def put_stream(self, key: str, stream: IO[bytes], *, overwrite: bool = True) -> str:
        p = self._path_for(key)
        if not overwrite and p.exists():
            raise AlreadyExistsError(f"Object already exists: {key}", details={"key": key})
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        try:
            with tmp.open("wb") as f:
                shutil.copyfileobj(stream, f, length=64 * 1024)
            os.replace(tmp, p)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Failed to write {key}", details={"error": str(e)}) from e
        return key

    def put_blob(self, data: bytes, *, algo: str = "sha256") -> str:
        digest = hash_bytes(data, algo)
        key = content_addressed_key(digest, algo)
        # Content-addressed writes are idempotent; always overwrite (same bytes).
        self.put_bytes(key, data, overwrite=True)
        return key

    # ─── reads ────────────────────────────────────────────────
    def get_bytes(self, key: str) -> bytes:
        p = self._path_for(key)
        if not p.exists() or not p.is_file():
            raise_not_found(key)
        try:
            return p.read_bytes()
        except OSError as e:
            raise StorageError(f"Failed to read {key}", details={"error": str(e)}) from e

    def get_stream(self, key: str) -> IO[bytes]:
        p = self._path_for(key)
        if not p.exists() or not p.is_file():
            raise_not_found(key)
        try:
            return p.open("rb")
        except OSError as e:
            raise StorageError(f"Failed to open {key}", details={"error": str(e)}) from e

    # ─── metadata ─────────────────────────────────────────────
    def stat(self, key: str) -> ObjectInfo:
        p = self._path_for(key)
        if not p.exists() or not p.is_file():
            raise_not_found(key)
        st = p.stat()
        return ObjectInfo(
            key=key,
            size=st.st_size,
            last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
            etag=f'"{st.st_mtime_ns:x}-{st.st_size:x}"',
            content_type=None,
            metadata=None,
        )

    def exists(self, key: str) -> bool:
        p = self._path_for(key)
        return p.exists() and p.is_file()

    # ─── listing ──────────────────────────────────────────────
    def list(self, prefix: str = "", *, recursive: bool = True) -> Iterator[ObjectInfo]:
        if prefix:
            base = self._path_for(prefix)
            rel_prefix = normalize_key(prefix)
        else:
            base = self._root
            rel_prefix = ""

        if not base.exists():
            return
        if base.is_file():
            yield self._info_for(base, rel_prefix or base.name)
            return

        for path in self._walk(base, recursive=recursive):
            if path.is_file():
                rel = path.relative_to(self._root).as_posix()
                yield ObjectInfo(
                    key=rel,
                    size=path.stat().st_size,
                    last_modified=datetime.fromtimestamp(
                        path.stat().st_mtime, tz=UTC
                    ),
                    etag=f'"{path.stat().st_mtime_ns:x}-{path.stat().st_size:x}"',
                )

    def _walk(self, base: Path, *, recursive: bool) -> Iterator[Path]:
        if recursive:
            yield from base.rglob("*")
        else:
            yield from base.iterdir()

    def _info_for(self, path: Path, key: str) -> ObjectInfo:
        st = path.stat()
        return ObjectInfo(
            key=key,
            size=st.st_size,
            last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC),
        )

    # ─── deletion ─────────────────────────────────────────────
    def delete(self, key: str) -> None:
        p = self._path_for(key)
        if not p.exists():
            return
        try:
            p.unlink()
        except OSError as e:
            raise StorageError(f"Failed to delete {key}", details={"error": str(e)}) from e

    # ─── lifecycle ────────────────────────────────────────────
    def close(self) -> None:
        # Nothing to release for a plain directory.
        return
