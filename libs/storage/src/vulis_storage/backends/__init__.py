"""Concrete storage backends."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_storage.backends.local_fs import LocalFSBackend
from vulis_storage.backends.s3 import S3Backend
from vulis_storage.backends.smb_mount import SmbMountBackend
from vulis_storage.backends.smb_protocol import SmbProtocolBackend

__all__ = [
    "LocalFSBackend",
    "S3Backend",
    "SmbMountBackend",
    "SmbProtocolBackend",
]
