"""vulis-storage — backend-agnostic blob storage for Vulis.

Public API::

    from vulis_storage import (
        build_backend,
        build_from_settings,
        BackendConfig,
        StorageBackend,
        ObjectInfo,
        LocalFSBackend,
        SmbProtocolBackend,
        SmbMountBackend,
    )

See the README for usage and ADR 0006 for the rationale.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_storage.backends import (
    LocalFSBackend,
    S3Backend,
    SmbMountBackend,
    SmbProtocolBackend,
)
from vulis_storage.base import (
    BackendConfig,
    BackendKind,
    ObjectInfo,
    StorageBackend,
    content_addressed_key,
    hash_bytes,
    hash_stream,
    normalize_key,
)
from vulis_storage.factory import build_backend, build_from_settings

__version__ = "0.1.0"

__all__ = [
    "BackendConfig",
    "BackendKind",
    # concrete backends
    "LocalFSBackend",
    "ObjectInfo",
    "S3Backend",
    "SmbMountBackend",
    "SmbProtocolBackend",
    # types & protocol
    "StorageBackend",
    "__version__",
    # factory
    "build_backend",
    "build_from_settings",
    "content_addressed_key",
    "hash_bytes",
    "hash_stream",
    "normalize_key",
]
