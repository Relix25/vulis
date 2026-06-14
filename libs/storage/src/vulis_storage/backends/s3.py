"""S3-compatible backend (stub for M1).

Reserved for the future scale-out path (MinIO or cloud S3). Not implemented
in M1; ``boto3`` is an optional dependency (``pip install vulis-storage[s3]``).

This module exists so that:
- the factory has a stable target for ``backend="s3"``,
- contributors can flesh it out without touching the protocol.

Raises ``StorageError`` on any operation, so a misconfiguration fails loud
rather than silently writing to the wrong place.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Iterator
from typing import IO

from vulis_core.exceptions import StorageError

from vulis_storage.base import ObjectInfo

__all__ = ["S3Backend"]


class S3Backend:
    """S3-compatible backend — not yet implemented (M1 stub).

    Will be implemented when a MinIO/S3 deployment is available. Until then,
    every operation raises ``StorageError`` so misconfigurations fail loudly.
    """

    kind = "s3"

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise StorageError(
            "S3Backend is not implemented yet (M1 stub). "
            "Use 'smb-protocol' or 'local-fs' for now.",
            details={"backend": "s3"},
        )

    # The methods below exist only to satisfy type-checkers / IDEs that
    # expect the StorageBackend protocol; they all raise.

    def put_bytes(  # pragma: no cover
        self, key: str, data: bytes, *, overwrite: bool = True
    ) -> str:
        raise NotImplementedError

    def put_stream(  # pragma: no cover
        self, key: str, stream: IO[bytes], *, overwrite: bool = True
    ) -> str:
        raise NotImplementedError

    def put_blob(self, data: bytes, *, algo: str = "sha256") -> str:  # pragma: no cover
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    def get_stream(self, key: str) -> IO[bytes]:  # pragma: no cover
        raise NotImplementedError

    def stat(self, key: str) -> ObjectInfo:  # pragma: no cover
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def list(  # pragma: no cover
        self, prefix: str = "", *, recursive: bool = True
    ) -> Iterator[ObjectInfo]:
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError
