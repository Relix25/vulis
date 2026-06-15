"""Tests for the manifest builder + digest / verification."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import json

import pytest
from vulis_core import ChecksumMismatchError

from vulis_dataset.manifest import (
    MANIFEST_SCHEMA,
    build_manifest,
    manifest_digest,
    serialize_manifest,
    verify_manifest_blob,
)


def _sample(key: str, path: str, label: str | None = "ok", split: str = "TRAIN", size: int = 10):
    return {
        "key": f"sha256/{key}",
        "path": path,
        "label": label,
        "split": split,
        "size_bytes": size,
    }


def test_build_manifest_basic():
    samples = [
        _sample("a", "train/x.png"),
        _sample("b", "train/y.png", label="ko"),
    ]
    m = build_manifest(
        version="1.2.0",
        dataset_id="ds_abc",
        task_kind="DETECTION",
        samples=samples,
    )
    assert m["schema"] == MANIFEST_SCHEMA
    assert m["version"] == "1.2.0"
    assert m["dataset_id"] == "ds_abc"
    assert m["task_kind"] == "DETECTION"
    assert m["sample_count"] == 2
    assert m["size_bytes"] == 20
    assert len(m["samples"]) == 2


def test_build_manifest_sorts_samples_for_reproducibility():
    """Order of input must not affect the digest."""
    a = _sample("a", "train/x.png")
    b = _sample("b", "train/y.png")
    c = _sample("c", "train/z.png")
    m1 = build_manifest(version="1.0.0", dataset_id="d", task_kind="DETECTION", samples=[a, b, c])
    m2 = build_manifest(version="1.0.0", dataset_id="d", task_kind="DETECTION", samples=[c, a, b])
    m3 = build_manifest(version="1.0.0", dataset_id="d", task_kind="DETECTION", samples=[b, c, a])
    assert manifest_digest(m1) == manifest_digest(m2) == manifest_digest(m3)


def test_serialize_manifest_is_canonical_json():
    m = build_manifest(
        version="1.0.0",
        dataset_id="d",
        task_kind="DETECTION",
        samples=[_sample("a", "p")],
    )
    blob = serialize_manifest(m)
    # Round-trip — sort_keys + compact separators give us a parseable, stable doc.
    parsed = json.loads(blob)
    assert parsed["version"] == "1.0.0"
    # No whitespace from compact separators.
    assert b": " not in blob  # no key-value space
    assert b", " not in blob  # no item separator space


def test_manifest_digest_is_sha256_hex():
    m = build_manifest(
        version="0.0.1",
        dataset_id="d",
        task_kind="DETECTION",
        samples=[_sample("a", "p")],
    )
    d = manifest_digest(m)
    assert len(d) == 64
    int(d, 16)  # parses as hex


def test_verify_manifest_blob_passes_on_match():
    m = build_manifest(
        version="1.0.0",
        dataset_id="d",
        task_kind="DETECTION",
        samples=[_sample("a", "p")],
    )
    blob = serialize_manifest(m)
    digest = manifest_digest(m)
    # Should not raise.
    verify_manifest_blob(blob, digest)


def test_verify_manifest_blob_raises_on_mismatch():
    m = build_manifest(
        version="1.0.0",
        dataset_id="d",
        task_kind="DETECTION",
        samples=[_sample("a", "p")],
    )
    blob = serialize_manifest(m)
    with pytest.raises(ChecksumMismatchError) as exc:
        verify_manifest_blob(blob, "deadbeef" * 8)
    assert "deadbeef" in str(exc.value)


def test_build_manifest_empty_samples():
    m = build_manifest(
        version="0.0.1",
        dataset_id="d",
        task_kind="DETECTION",
        samples=[],
    )
    assert m["sample_count"] == 0
    assert m["size_bytes"] == 0
    assert m["samples"] == []
