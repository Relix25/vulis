# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Tests for the non-backend parts: hashing, key normalization, config."""

from __future__ import annotations

import io

import pytest
from vulis_core.exceptions import StorageError

from vulis_storage import (
    BackendConfig,
    content_addressed_key,
    hash_bytes,
    hash_stream,
    normalize_key,
)

# ─── hashing ─────────────────────────────────────────────────


def test_hash_bytes_sha256() -> None:
    assert (
        hash_bytes(b"hello")
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_hash_bytes_other_algo() -> None:
    assert hash_bytes(b"hello", algo="sha1") == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"


def test_hash_stream_matches_bytes() -> None:
    data = b"x" * (64 * 1024 * 3 + 17)  # multi-chunk
    assert hash_stream(io.BytesIO(data)) == hash_bytes(data)


def test_hash_stream_empty() -> None:
    assert hash_stream(io.BytesIO(b"")) == hash_bytes(b"")


# ─── content-addressed key ───────────────────────────────────


def test_content_addressed_key_format() -> None:
    key = content_addressed_key("abc123", algo="sha256")
    assert key == "sha256/abc123"


def test_content_addressed_key_other_algo() -> None:
    assert content_addressed_key("xyz", algo="sha1") == "sha1/xyz"


# ─── key normalization ───────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("simple/key.onnx", "simple/key.onnx"),
        ("a/b/c", "a/b/c"),
        ("/leading/slash", "leading/slash"),
        ("trailing/", "trailing"),
        ("a//b", "a/b"),
        ("a/./b", "a/b"),
        ("back\\slash", "back/slash"),
        ("mix\\of/slashes", "mix/of/slashes"),
        ("a/b/", "a/b"),
        ("///a///b///", "a/b"),
    ],
)
def test_normalize_key_cases(raw: str, expected: str) -> None:
    assert normalize_key(raw) == expected


def test_normalize_key_rejects_empty() -> None:
    with pytest.raises(StorageError):
        normalize_key("")


def test_normalize_key_rejects_only_slashes() -> None:
    with pytest.raises(StorageError):
        normalize_key("///")


def test_normalize_key_strips_dotdot() -> None:
    # ".." is dropped to prevent escaping the root.
    assert normalize_key("a/../b") == "b"
    assert normalize_key("../etc/passwd") == "etc/passwd"


# ─── BackendConfig ───────────────────────────────────────────


def test_backend_config_defaults() -> None:
    cfg = BackendConfig(backend="local-fs")
    assert cfg.backend == "local-fs"
    assert cfg.root_prefix == ""
    assert cfg.local_root is None


def test_backend_config_immutable() -> None:
    cfg = BackendConfig(backend="local-fs")
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.backend = "s3"  # type: ignore[misc]
