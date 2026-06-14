# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""LocalFS-specific tests (beyond the cross-backend contract)."""

from __future__ import annotations

from vulis_storage import LocalFSBackend


def test_local_fs_creates_root_if_missing(tmp_path) -> None:
    root = tmp_path / "does" / "not" / "exist" / "yet"
    assert not root.exists()
    b = LocalFSBackend(root)
    try:
        assert root.exists()
        assert root.is_dir()
    finally:
        b.close()


def test_local_fs_creates_intermediate_dirs(tmp_path) -> None:
    b = LocalFSBackend(tmp_path)
    b.put_bytes("a/very/deep/nested/key.bin", b"x")
    assert (tmp_path / "a" / "very" / "deep" / "nested" / "key.bin").exists()
    b.close()


def test_local_fs_atomic_write_no_partial_file(tmp_path) -> None:
    # If put_bytes fails mid-write, no .part file should remain.
    b = LocalFSBackend(tmp_path)
    # Successful write leaves no .part.
    b.put_bytes("ok", b"data")
    assert not list(tmp_path.glob("*.part"))
    b.close()


def test_local_fs_rejects_path_traversal(tmp_path) -> None:
    # normalize_key drops "..", so the key is safe; but if someone bypassed
    # it, _path_for has a second guard.
    b = LocalFSBackend(tmp_path / "root")
    # ".." is stripped by normalize_key, so this lands inside the root.
    b.put_bytes("etc/passwd", b"x")
    assert b.exists("etc/passwd")
    b.close()


def test_local_fs_kind() -> None:
    assert LocalFSBackend.kind == "local-fs"


def test_local_fs_with_root_prefix_isolates(tmp_path) -> None:
    b = LocalFSBackend(tmp_path, root_prefix="vulis/blobs")
    b.put_bytes("file", b"x")
    # The file lives under vulis/blobs/ within the root.
    assert (tmp_path / "vulis" / "blobs" / "file").exists()
    # But is visible under the empty prefix.
    objs = list(b.list())
    assert objs[0].key == "file"
    b.close()


def test_local_fs_close_is_noop(tmp_path) -> None:
    b = LocalFSBackend(tmp_path)
    # close() must not raise.
    b.close()
