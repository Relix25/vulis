"""Factory: build a ``StorageBackend`` from configuration.

This is the single entry point services should use to obtain a backend.
It reads a ``BackendConfig`` (or a ``vulis_core.VulisSettings``) and returns
the right backend instance.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_core import VulisError, VulisSettings
from vulis_core.exceptions import ValidationError

from vulis_storage.backends import (
    LocalFSBackend,
    S3Backend,
    SmbMountBackend,
    SmbProtocolBackend,
)
from vulis_storage.base import BackendConfig, StorageBackend

__all__ = ["build_backend", "build_from_settings"]


def build_backend(config: BackendConfig) -> StorageBackend:
    """Instantiate the backend described by ``config``.

    Raises ``ValidationError`` for missing required fields.
    """
    backend = config.backend

    if backend == "local-fs":
        if not config.local_root:
            raise ValidationError(
                "local-fs backend requires 'local_root'",
                details={"backend": "local-fs"},
            )
        return LocalFSBackend(config.local_root, root_prefix=config.root_prefix)

    if backend == "smb-protocol":
        missing = [
            f
            for f in ("smb_host", "smb_share", "smb_username", "smb_password")
            if not getattr(config, f)
        ]
        if missing:
            raise ValidationError(
                f"smb-protocol backend requires: {', '.join(missing)}",
                details={"backend": "smb-protocol", "missing": missing},
            )
        return SmbProtocolBackend(
            host=config.smb_host or "",
            share=config.smb_share or "",
            username=config.smb_username or "",
            password=config.smb_password or "",
            domain=config.smb_domain,
            port=config.smb_port,
            root_prefix=config.root_prefix,
        )

    if backend == "smb-mount":
        if not config.local_root:
            raise ValidationError(
                "smb-mount backend requires 'local_root' (the mount path)",
                details={"backend": "smb-mount"},
            )
        return SmbMountBackend(
            config.local_root,
            root_prefix=config.root_prefix,
            smb_host=config.smb_host,
            smb_share=config.smb_share,
        )

    if backend == "s3":
        # Stub: raises immediately at construction.
        return S3Backend()  # type: ignore[return-value]

    raise VulisError(f"Unknown storage backend: {backend!r}", details={"backend": backend})


def build_from_settings(settings: VulisSettings) -> StorageBackend:
    """Build a backend from the process-wide ``VulisSettings``.

    Convenience wrapper that translates the flat settings fields into a
    ``BackendConfig`` and calls ``build_backend``.
    """
    cfg = BackendConfig(
        backend=settings.storage_backend,
        local_root=settings.storage_local_root,
        smb_host=settings.storage_smb_host,
        smb_share=settings.storage_smb_share,
        smb_username=settings.storage_smb_username,
        smb_password=(
            settings.storage_smb_password.get_secret_value()
            if settings.storage_smb_password
            else None
        ),
        smb_domain=settings.storage_smb_domain,
    )
    return build_backend(cfg)
