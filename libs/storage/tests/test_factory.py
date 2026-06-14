# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Factory tests: build_backend / build_from_settings."""

from __future__ import annotations

import pytest
from vulis_core import VulisError
from vulis_core.exceptions import ValidationError

from vulis_storage import (
    BackendConfig,
    LocalFSBackend,
    SmbMountBackend,
    SmbProtocolBackend,
    build_backend,
    build_from_settings,
)


def test_build_local_fs(tmp_path) -> None:
    cfg = BackendConfig(backend="local-fs", local_root=str(tmp_path / "store"))
    b = build_backend(cfg)
    assert isinstance(b, LocalFSBackend)
    assert b.kind == "local-fs"
    b.close()


def test_build_local_fs_with_prefix(tmp_path) -> None:
    cfg = BackendConfig(
        backend="local-fs",
        local_root=str(tmp_path / "store"),
        root_prefix="blobs",
    )
    b = build_backend(cfg)
    b.put_bytes("x", b"1")
    assert b.get_bytes("x") == b"1"
    b.close()


def test_build_local_fs_missing_root_raises() -> None:
    cfg = BackendConfig(backend="local-fs")
    with pytest.raises(ValidationError):
        build_backend(cfg)


def test_build_smb_protocol_requires_all_fields() -> None:
    cfg = BackendConfig(backend="smb-protocol")  # nothing set
    with pytest.raises(ValidationError) as ei:
        build_backend(cfg)
    msg = str(ei.value)
    assert "smb_host" in msg
    assert "smb_share" in msg
    assert "smb_username" in msg
    assert "smb_password" in msg


def test_build_smb_protocol_partial_fields() -> None:
    cfg = BackendConfig(backend="smb-protocol", smb_host="h", smb_share="s")
    with pytest.raises(ValidationError) as ei:
        build_backend(cfg)
    assert "smb_username" in str(ei.value)


def test_build_smb_protocol_returns_right_type() -> None:
    # We don't connect on construction; the type check is enough.
    cfg = BackendConfig(
        backend="smb-protocol",
        smb_host="h",
        smb_share="s",
        smb_username="u",
        smb_password="p",
    )
    b = build_backend(cfg)
    assert isinstance(b, SmbProtocolBackend)
    assert b.kind == "smb-protocol"


def test_build_smb_mount_requires_mount_path() -> None:
    cfg = BackendConfig(backend="smb-mount")
    with pytest.raises(ValidationError):
        build_backend(cfg)


def test_build_smb_mount_returns_right_type(tmp_path) -> None:
    cfg = BackendConfig(
        backend="smb-mount",
        local_root=str(tmp_path / "mount"),
        smb_host="h",
        smb_share="s",
    )
    b = build_backend(cfg)
    assert isinstance(b, SmbMountBackend)
    assert b.kind == "smb-mount"
    assert b.smb_host == "h"


def test_build_s3_raises_stub() -> None:
    cfg = BackendConfig(backend="s3")
    with pytest.raises(Exception):  # StorageError raised in __init__
        build_backend(cfg)


def test_build_unknown_backend_raises_vulis_error() -> None:
    cfg = BackendConfig(backend="ftp")
    with pytest.raises(VulisError):
        build_backend(cfg)


# ─── build_from_settings ─────────────────────────────────────


def test_build_from_settings_local_fs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("VULIS_STORAGE_BACKEND", "local-fs")
    monkeypatch.setenv("VULIS_STORAGE_LOCAL_ROOT", str(tmp_path / "store"))
    from vulis_core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    b = build_from_settings(s)
    assert isinstance(b, LocalFSBackend)
    b.close()
    get_settings.cache_clear()


def test_build_from_settings_smb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VULIS_STORAGE_BACKEND", "smb-protocol")
    monkeypatch.setenv("VULIS_STORAGE_SMB_HOST", "nas")
    monkeypatch.setenv("VULIS_STORAGE_SMB_SHARE", "vulis")
    monkeypatch.setenv("VULIS_STORAGE_SMB_USERNAME", "u")
    monkeypatch.setenv("VULIS_STORAGE_SMB_PASSWORD", "p")
    from vulis_core.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    b = build_from_settings(s)
    assert isinstance(b, SmbProtocolBackend)
    get_settings.cache_clear()
