# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Backend contract tests.

Every StorageBackend implementation must satisfy this contract. The tests
are parametrized over a list of (backend-name, factory) so we can exercise
LocalFS now and SMB later without duplicating the assertions.

To add a new backend to the contract suite, append a tuple to
``BACKENDS`` below.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from typing import Protocol

import pytest
from vulis_core.exceptions import (
    AlreadyExistsError,
    ObjectNotFoundError,
)

from vulis_storage import LocalFSBackend, StorageBackend

# ─── Backend factories for the parametrized tests ────────────


class BackendFactory(Protocol):
    def __call__(self, tmp_path) -> StorageBackend: ...


def _local_fs(tmp_path) -> StorageBackend:
    return LocalFSBackend(tmp_path / "store")


def _local_fs_prefixed(tmp_path) -> StorageBackend:
    return LocalFSBackend(tmp_path / "store", root_prefix="vulis/blobs")


BACKENDS: list[tuple[str, BackendFactory]] = [
    ("local-fs", _local_fs),
    ("local-fs-prefixed", _local_fs_prefixed),
]


@pytest.fixture(params=[f for _, f in BACKENDS], ids=[n for n, _ in BACKENDS])
def backend(request: pytest.FixtureRequest, tmp_path) -> Iterator[StorageBackend]:
    factory: BackendFactory = request.param
    b = factory(tmp_path)
    try:
        yield b
    finally:
        b.close()


# ─── Protocol structural checks ──────────────────────────────


def test_backend_has_kind(backend: StorageBackend) -> None:
    assert isinstance(backend.kind, str)
    assert backend.kind


def test_backend_satisfies_protocol(backend: StorageBackend) -> None:
    # StorageBackend is a runtime-checkable Protocol.
    assert isinstance(backend, StorageBackend)


# ─── put/get round-trip ──────────────────────────────────────


def test_put_get_bytes_roundtrip(backend: StorageBackend) -> None:
    payload = b"\x00\x01\x02hello world\xff\xfe"
    key = backend.put_bytes("dir1/file.bin", payload)
    assert key == "dir1/file.bin"
    assert backend.get_bytes(key) == payload


def test_put_get_empty_bytes(backend: StorageBackend) -> None:
    key = backend.put_bytes("empty", b"")
    assert backend.get_bytes(key) == b""


def test_put_get_large_bytes(backend: StorageBackend) -> None:
    # Larger than the internal chunk size (64 KiB) to exercise multi-chunk.
    payload = bytes(range(256)) * 1024  # 256 KiB
    key = backend.put_bytes("big", payload)
    assert backend.get_bytes(key) == payload


def test_put_overwrite_replaces_content(backend: StorageBackend) -> None:
    backend.put_bytes("k", b"old")
    backend.put_bytes("k", b"new", overwrite=True)
    assert backend.get_bytes("k") == b"new"


def test_put_no_overwrite_raises_when_exists(backend: StorageBackend) -> None:
    backend.put_bytes("k", b"first")
    with pytest.raises(AlreadyExistsError):
        backend.put_bytes("k", b"second", overwrite=False)


def test_put_no_overwrite_ok_when_missing(backend: StorageBackend) -> None:
    backend.put_bytes("k", b"first", overwrite=False)
    assert backend.get_bytes("k") == b"first"


# ─── stream API ──────────────────────────────────────────────


def test_put_stream_roundtrip(backend: StorageBackend) -> None:
    payload = b"stream-content" * 1000
    key = backend.put_stream("s/obj", io.BytesIO(payload))
    assert backend.get_bytes(key) == payload


def test_get_stream_roundtrip(backend: StorageBackend) -> None:
    payload = b"\xab\xcd" * 5000
    backend.put_bytes("s/obj2", payload)
    stream = backend.get_stream("s/obj2")
    try:
        buf = io.BytesIO()
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            buf.write(chunk)
        assert buf.getvalue() == payload
    finally:
        stream.close()


def test_put_stream_empty(backend: StorageBackend) -> None:
    backend.put_stream("empty-stream", io.BytesIO(b""))
    assert backend.get_bytes("empty-stream") == b""


# ─── content-addressed put_blob ──────────────────────────────


def test_put_blob_returns_hash_key(backend: StorageBackend) -> None:
    key = backend.put_blob(b"hello")
    assert key.startswith("sha256/")
    assert (
        key
        == "sha256/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_put_blob_is_idempotent(backend: StorageBackend) -> None:
    k1 = backend.put_blob(b"same")
    k2 = backend.put_blob(b"same")
    assert k1 == k2
    assert backend.get_bytes(k1) == b"same"


def test_put_blob_different_content_different_key(backend: StorageBackend) -> None:
    a = backend.put_blob(b"a")
    b = backend.put_blob(b"b")
    assert a != b


# ─── stat / exists ───────────────────────────────────────────


def test_stat_returns_size_and_key(backend: StorageBackend) -> None:
    payload = b"0123456789" * 100  # 1000 bytes
    backend.put_bytes("stat-target", payload)
    info = backend.stat("stat-target")
    assert info.key == "stat-target"
    assert info.size == len(payload)
    assert info.last_modified is not None


def test_stat_missing_raises_not_found(backend: StorageBackend) -> None:
    with pytest.raises(ObjectNotFoundError):
        backend.stat("does/not/exist")


def test_exists_true_after_put(backend: StorageBackend) -> None:
    backend.put_bytes("e", b"x")
    assert backend.exists("e") is True


def test_exists_false_for_missing(backend: StorageBackend) -> None:
    assert backend.exists("missing") is False


# ─── get on missing ──────────────────────────────────────────


def test_get_bytes_missing_raises(backend: StorageBackend) -> None:
    with pytest.raises(ObjectNotFoundError):
        backend.get_bytes("nope")


def test_get_stream_missing_raises(backend: StorageBackend) -> None:
    with pytest.raises(ObjectNotFoundError):
        backend.get_stream("nope")


# ─── listing ─────────────────────────────────────────────────


def test_list_empty_when_nothing_stored(backend: StorageBackend) -> None:
    assert list(backend.list()) == []


def test_list_returns_all_keys(backend: StorageBackend) -> None:
    for k in ("a", "b", "c"):
        backend.put_bytes(k, b"x")
    keys = sorted(o.key for o in backend.list())
    assert keys == ["a", "b", "c"]


def test_list_with_prefix(backend: StorageBackend) -> None:
    backend.put_bytes("models/a.onnx", b"x")
    backend.put_bytes("models/b.onnx", b"y")
    backend.put_bytes("datasets/d.zip", b"z")
    keys = sorted(o.key for o in backend.list("models"))
    assert keys == ["models/a.onnx", "models/b.onnx"]


def test_list_non_recursive_returns_immediate_children(
    backend: StorageBackend,
) -> None:
    backend.put_bytes("dir/a", b"1")
    backend.put_bytes("dir/sub/b", b"2")
    backend.put_bytes("dir/c", b"3")
    # Non-recursive under "dir" should NOT include "dir/sub/b".
    keys = sorted(o.key for o in backend.list("dir", recursive=False))
    assert "dir/a" in keys
    assert "dir/c" in keys
    assert all(not k.startswith("dir/sub/") for k in keys)


def test_list_yields_object_info_with_size(backend: StorageBackend) -> None:
    backend.put_bytes("big-file", b"q" * 1234)
    objs = list(backend.list())
    assert len(objs) == 1
    assert objs[0].key == "big-file"
    assert objs[0].size == 1234


# ─── delete ──────────────────────────────────────────────────


def test_delete_removes_object(backend: StorageBackend) -> None:
    backend.put_bytes("gone", b"x")
    assert backend.exists("gone") is True
    backend.delete("gone")
    assert backend.exists("gone") is False


def test_delete_is_idempotent(backend: StorageBackend) -> None:
    # Deleting a missing key must NOT raise.
    backend.delete("never-existed")


def test_get_after_delete_raises_not_found(backend: StorageBackend) -> None:
    backend.put_bytes("temp", b"x")
    backend.delete("temp")
    with pytest.raises(ObjectNotFoundError):
        backend.get_bytes("temp")


# ─── overwrite semantics across nested keys ─────────────────


def test_nested_keys_roundtrip(backend: StorageBackend) -> None:
    for depth in range(1, 6):
        key = "/".join(f"lvl{i}" for i in range(depth)) + "/file.bin"
        backend.put_bytes(key, str(depth).encode())
        assert backend.get_bytes(key) == str(depth).encode()


def test_key_with_extension_preserved(backend: StorageBackend) -> None:
    backend.put_bytes("models/det/v3/weights.onnx", b"x")
    objs = list(backend.list("models"))
    assert objs[0].key == "models/det/v3/weights.onnx"
