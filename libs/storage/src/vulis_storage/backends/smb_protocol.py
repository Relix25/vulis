"""SMB backend (pure-Python via ``smbprotocol``).

This is the default backend in the Vulis deployment context (Windows SMB
shares). It needs no OS-level mount, so it works identically on Linux and
Windows without admin privileges.

Connection handling
-------------------
A single ``smbprotocol.session.Session`` is opened lazily on first use and
reused for subsequent operations. ``close()`` logs the session off.

Backslash translation
---------------------
SMB paths use backslashes internally; we expose POSIX-style keys to callers
and translate on the boundary (see ``normalize_key``).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import IO

from vulis_core.exceptions import AlreadyExistsError, StorageError

# ``smbprotocol`` is a hard runtime dependency of this backend; import lazily
# inside methods so the rest of the lib (LocalFS, factory) remains importable
# even if smbprotocol is absent in a minimal install.
from vulis_storage.base import (
    ObjectInfo,
    content_addressed_key,
    hash_bytes,
    normalize_key,
    raise_not_found,
)

__all__ = ["SmbProtocolBackend"]

log = logging.getLogger("vulis.storage.smb")

_DEFAULT_CHUNK = 64 * 1024


class SmbProtocolBackend:
    """Storage backend over an SMB share (pure Python).

    Parameters
    ----------
    host, share, username, password, domain, port:
        SMB connection parameters.
    root_prefix:
        Optional subfolder inside the share used as the logical root.
    """

    kind = "smb-protocol"

    def __init__(
        self,
        *,
        host: str,
        share: str,
        username: str,
        password: str,
        domain: str | None = None,
        port: int = 445,
        root_prefix: str = "",
    ) -> None:
        self._host = host
        self._share = share
        self._username = username
        self._password = password
        self._domain = domain
        self._port = port
        self._root_prefix = normalize_key(root_prefix) if root_prefix else ""
        self._client = None  # type: ignore[assignment]
        self._session = None  # type: ignore[assignment]
        self._tree = None  # type: ignore[assignment]

    # ─── connection lifecycle ─────────────────────────────────
    def _ensure_connected(self) -> None:
        if self._tree is not None:
            return
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - defensive
            raise StorageError(
                "smbprotocol is not installed; install vulis-storage[smb] or smbprotocol",
                details={"missing": "smbprotocol"},
            ) from e

        # smbclient is the high-level, thread-pooled API of smbprotocol.
        # It caches sessions per (host, user, ...) tuple.
        try:
            smbclient.ClientConfig(
                username=self._username,
                password=self._password,
                domain=self._domain or "",
                port=self._port,
            )
            # Force a session to validate the connection eagerly.
            self._client = smbclient
            # Trigger the actual connect by listing the share root.
            try:
                next(iter(smbclient.scandir(self._unc_root())), None)
            except Exception as e:  # pragma: no cover - depends on env
                # Some servers reject scandir on missing dir; that's fine as
                # long as we authenticated. We only raise on auth failures.
                msg = str(e).lower()
                if "logon failure" in msg or "access" in msg:
                    raise
        except StorageError:
            raise
        except Exception as e:
            unc_share = "\\\\" + self._host + "\\" + self._share
            raise StorageError(
                f"Cannot connect to SMB share {unc_share}",
                details={"host": self._host, "share": self._share, "error": str(e)},
            ) from e

    def _unc_root(self) -> str:
        # smbclient expects UNC paths like \\host\share\folder
        # Backslashes are not allowed in f-strings before Python 3.12, so we
        # build the path with plain string concatenation.
        root = "\\\\" + self._host + "\\" + self._share
        if self._root_prefix:
            root = root + "\\" + self._root_prefix
        return root

    def _unc_for(self, key: str) -> str:
        nk = normalize_key(key).replace("/", "\\")
        return self._unc_root() + "\\" + nk

    # ─── writes ───────────────────────────────────────────────
    def put_bytes(self, key: str, data: bytes, *, overwrite: bool = True) -> str:
        self._ensure_connected()
        unc = self._unc_for(key)
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e

        if not overwrite and self._exists_raw(unc):
            raise AlreadyExistsError(f"Object already exists: {key}", details={"key": key})

        self._ensure_parent_dir(unc)
        try:
            with smbclient.open_file(unc, mode="wb") as f:
                f.write(data)
        except Exception as e:
            raise StorageError(f"Failed to write {key}", details={"error": str(e)}) from e
        return key

    def put_stream(self, key: str, stream: IO[bytes], *, overwrite: bool = True) -> str:
        self._ensure_connected()
        unc = self._unc_for(key)
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e

        if not overwrite and self._exists_raw(unc):
            raise AlreadyExistsError(f"Object already exists: {key}", details={"key": key})

        self._ensure_parent_dir(unc)
        try:
            with smbclient.open_file(unc, mode="wb") as f:
                while True:
                    chunk = stream.read(_DEFAULT_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as e:
            raise StorageError(f"Failed to write {key}", details={"error": str(e)}) from e
        return key

    def put_blob(self, data: bytes, *, algo: str = "sha256") -> str:
        digest = hash_bytes(data, algo)
        key = content_addressed_key(digest, algo)
        self.put_bytes(key, data, overwrite=True)
        return key

    # ─── reads ────────────────────────────────────────────────
    def get_bytes(self, key: str) -> bytes:
        f = self.get_stream(key)
        try:
            buf = io.BytesIO()
            while True:
                chunk = f.read(_DEFAULT_CHUNK)
                if not chunk:
                    break
                buf.write(chunk)
            return buf.getvalue()
        finally:
            f.close()

    def get_stream(self, key: str) -> IO[bytes]:
        self._ensure_connected()
        unc = self._unc_for(key)
        if not self._exists_raw(unc):
            raise_not_found(key)
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e
        try:
            return smbclient.open_file(unc, mode="rb")  # type: ignore[return-value]
        except Exception as e:
            raise StorageError(f"Failed to open {key}", details={"error": str(e)}) from e

    # ─── metadata ─────────────────────────────────────────────
    def stat(self, key: str) -> ObjectInfo:
        self._ensure_connected()
        unc = self._unc_for(key)
        if not self._exists_raw(unc):
            raise_not_found(key)
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e
        try:
            info = smbclient.stat(unc)
            return ObjectInfo(
                key=key,
                size=int(getattr(info, "st_size", 0)),
                last_modified=datetime.fromtimestamp(
                    getattr(info, "st_mtime", 0.0), tz=UTC
                ),
                etag=None,
                content_type=None,
                metadata=None,
            )
        except Exception as e:
            raise StorageError(f"Failed to stat {key}", details={"error": str(e)}) from e

    def exists(self, key: str) -> bool:
        self._ensure_connected()
        return self._exists_raw(self._unc_for(key))

    def _exists_raw(self, unc: str) -> bool:
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e
        try:
            smbclient.stat(unc)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            # A connection error is not "does not exist".
            raise

    # ─── listing ──────────────────────────────────────────────
    def list(self, prefix: str = "", *, recursive: bool = True) -> Iterator[ObjectInfo]:
        self._ensure_connected()
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e

        base_unc = self._unc_root()
        if prefix:
            base_unc = base_unc + "\\" + normalize_key(prefix).replace("/", "\\")
        if not self._exists_raw(base_unc):
            return

        import os as _os

        def _walk(root: str) -> Iterator[tuple[str, object]]:
            try:
                with smbclient.scandir(root) as it:
                    for entry in it:
                        full = _os.path.join(root, entry.name)
                        if entry.is_dir():
                            if recursive:
                                yield from _walk(full)
                        else:
                            yield full, entry.stat()
            except (FileNotFoundError, NotADirectoryError):
                return

        root_len = len(self._unc_root()) + 1
        for full_unc, info in _walk(base_unc):
            # Convert back to a key relative to root_prefix.
            rel = full_unc[root_len:].replace("\\", "/")
            yield ObjectInfo(
                key=rel,
                size=int(getattr(info, "st_size", 0)),
                last_modified=datetime.fromtimestamp(
                    getattr(info, "st_mtime", 0.0), tz=UTC
                ),
            )

    # ─── deletion ─────────────────────────────────────────────
    def delete(self, key: str) -> None:
        self._ensure_connected()
        unc = self._unc_for(key)
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e
        try:
            smbclient.remove(unc)
        except FileNotFoundError:
            return  # idempotent
        except Exception as e:
            raise StorageError(f"Failed to delete {key}", details={"error": str(e)}) from e

    # ─── helpers ──────────────────────────────────────────────
    def _ensure_parent_dir(self, unc: str) -> None:
        import os as _os

        parent = _os.path.dirname(unc)
        if not parent:
            return
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise StorageError("smbprotocol missing") from e

        # Walk the path components and mkdir what's missing.
        # smbclient.mkdir raises if the dir exists; we ignore that case.
        parts = parent.split("\\")
        # Reconstruct incrementally.
        # The first parts are "", "", host, share, ...
        cur = ""
        for i, part in enumerate(parts):
            if part == "":
                cur = cur + "\\"
                continue
            cur = part if i == 0 else cur.rstrip("\\") + "\\" + part
            try:
                smbclient.mkdir(cur)
            except FileExistsError:
                continue
            except Exception:
                # Other errors (permission, ...) propagate lazily on the
                # actual write; we don't want to over-engineer mkdir.
                continue

    # ─── lifecycle ────────────────────────────────────────────
    def close(self) -> None:
        try:
            import smbclient  # type: ignore[import-not-found]
        except ImportError:
            return
        try:
            # Drop cached sessions for this server.
            smbclient.reset_connection_cache()
        except Exception:  # pragma: no cover - best-effort
            log.debug("smbclient reset_connection_cache failed", exc_info=True)
