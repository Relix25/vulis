"""Build / verify the JSON manifest of a ``DatasetVersion``.

The manifest is a deterministic JSON document that lists every sample
of the version. It is content-addressed (``sha256``) and stored via
``vulis_storage``; the digest is recorded on the ``DatasetVersion``
row.

Schema (v1)::

    {
        "schema": "vulis.dataset.manifest/v1",
        "version": "1.2.0",                       # semver
        "dataset_id": "ds_abc",                   # hex
        "task_kind": "DETECTION",                 # from Project.task_kind
        "sample_count": 100,
        "size_bytes": 12345678,
        "samples": [
            {
                "key": "sha256/abcd...",          # content-addressed
                "path": "train/img_001.png",      # relative
                "label": "ok",
                "split": "TRAIN",
                "size_bytes": 12345
            },
            ...
        ]
    }

The samples list is **sorted** (by ``key`` then ``path``) before
serialization, so the digest is reproducible for an identical set of
samples.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from vulis_storage import hash_bytes

MANIFEST_SCHEMA = "vulis.dataset.manifest/v1"


def build_manifest(
    *,
    version: str,
    dataset_id: str,
    task_kind: str,
    samples: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build a manifest dict from a sequence of sample descriptors.

    The samples list is sorted (by ``key``, then ``path``) for
    reproducibility — the same set of samples always produces the same
    bytes / digest. Sample dicts must each contain at least
    ``key``, ``path``, ``split``, ``size_bytes``; ``label`` is optional.
    """
    sorted_samples = sorted(samples, key=lambda s: (s["key"], s["path"]))
    sample_count = len(sorted_samples)
    size_bytes = sum(int(s.get("size_bytes", 0)) for s in sorted_samples)
    return {
        "schema": MANIFEST_SCHEMA,
        "version": version,
        "dataset_id": dataset_id,
        "task_kind": task_kind,
        "sample_count": sample_count,
        "size_bytes": size_bytes,
        "samples": sorted_samples,
    }


def serialize_manifest(manifest: dict[str, Any]) -> bytes:
    """Serialize a manifest dict to canonical bytes.

    Uses ``sort_keys=True`` and a compact separator so the digest is
    stable across runs and platforms.
    """
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Return the sha256 hex digest of the serialized manifest."""
    return hash_bytes(serialize_manifest(manifest))


def verify_manifest_blob(blob: bytes, expected_digest: str) -> None:
    """Raise :class:`ChecksumMismatchError` if ``blob`` doesn't match the digest.

    This is what the publish endpoint uses to confirm a published
    version's stored blob is byte-identical to what was computed at
    publish time.
    """
    from vulis_core import ChecksumMismatchError

    actual = hash_bytes(blob)
    if actual != expected_digest:
        raise ChecksumMismatchError(
            f"Manifest digest mismatch: expected {expected_digest}, got {actual}",
            details={"expected": expected_digest, "actual": actual},
        )


__all__ = [
    "MANIFEST_SCHEMA",
    "build_manifest",
    "manifest_digest",
    "serialize_manifest",
    "verify_manifest_blob",
]
