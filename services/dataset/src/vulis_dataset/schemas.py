"""Pydantic v2 request/response schemas for the dataset service.

These are the API contract — keep them stable. ORM models can change as
needed; schemas should only change with a deprecation cycle.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from vulis_dataset.models import (
    ImportSourceKind,
    ImportStatus,
    Split,
)

# ─── Shared ─────────────────────────────────────────────────────

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]

# TaskKind value set — duplicated from vulis_project.models.TaskKind to
# keep this service decoupled at the Python level. The set is the
# contract; treat additions as a breaking change.
TaskKindStr = Literal["DETECTION", "CLASSIFICATION", "SEGMENTATION"]


class ORMModel(BaseModel):
    """Base for response models that mirror an ORM row."""

    model_config = ConfigDict(from_attributes=True)


# ─── Dataset ────────────────────────────────────────────────────


class DatasetCreate(BaseModel):
    """Request body for ``POST /api/v1/datasets``."""

    project_id: NonEmptyStr
    name: NonEmptyStr
    description: str | None = Field(default=None, max_length=4096)
    task_kind: TaskKindStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetUpdate(BaseModel):
    """Request body for ``PATCH /api/v1/datasets/{id}`` (all fields optional)."""

    name: NonEmptyStr | None = None
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] | None = None


class DatasetRead(ORMModel):
    """Response model for a Dataset.

    The ORM attribute is ``metadata_`` (the trailing underscore avoids
    clashing with SQLAlchemy ``Base.metadata``). We expose it as
    ``metadata`` in the API for ergonomics.
    """

    id: str
    tenant_id: str
    project_id: str
    name: str
    description: str | None
    task_kind: TaskKindStr
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @model_validator(mode="before")
    @classmethod
    def _translate_metadata_(cls, data):
        if hasattr(data, "metadata_"):
            # We got an ORM instance — build the dict ourselves so we can
            # map the ``metadata_`` attribute to the public ``metadata`` field.
            return {
                "id": data.id,
                "tenant_id": data.tenant_id,
                "project_id": data.project_id,
                "name": data.name,
                "description": data.description,
                "task_kind": data.task_kind,
                "metadata": data.metadata_,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "deleted_at": data.deleted_at,
            }
        return data


# ─── DatasetVersion ─────────────────────────────────────────────


_SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


def _parse_semver(s: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(s)
    if not m:
        raise ValueError(f"Invalid SemVer: {s!r} (expected '<major>.<minor>.<patch>')")
    return int(m["major"]), int(m["minor"]), int(m["patch"])


class VersionRef(BaseModel):
    """Helper: parses '1.2.0' into major/minor/patch ints."""

    @classmethod
    def parse(cls, s: str) -> tuple[int, int, int]:
        return _parse_semver(s)


class DatasetVersionCreate(BaseModel):
    """Request body for ``POST /api/v1/datasets/{id}/versions``.

    Either provide ``version`` as a SemVer string or set explicit
    ``major``/``minor``/``patch`` (defaults: 0.0.1 — first version of
    a brand-new dataset).
    """

    version: str | None = Field(
        default=None,
        description="SemVer string 'major.minor.patch'. Overrides major/minor/patch if set.",
    )
    major: int | None = Field(default=None, ge=0)
    minor: int | None = Field(default=None, ge=0)
    patch: int | None = Field(default=None, ge=0)
    created_by: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolve_semver(self) -> tuple[int, int, int]:
        if self.version is not None:
            return _parse_semver(self.version)
        # Defaults: 0.0.1 — first draft of a new dataset.
        return (
            self.major if self.major is not None else 0,
            self.minor if self.minor is not None else 0,
            self.patch if self.patch is not None else 1,
        )


class DatasetVersionRead(ORMModel):
    """Response model for a DatasetVersion."""

    id: str
    tenant_id: str
    dataset_id: str
    major: int
    minor: int
    patch: int
    is_published: bool
    manifest_key: str | None
    manifest_digest: str | None
    sample_count: int
    size_bytes: int
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @model_validator(mode="before")
    @classmethod
    def _translate_metadata_(cls, data):
        if hasattr(data, "metadata_"):
            return {
                "id": data.id,
                "tenant_id": data.tenant_id,
                "dataset_id": data.dataset_id,
                "major": data.major,
                "minor": data.minor,
                "patch": data.patch,
                "is_published": data.is_published,
                "manifest_key": data.manifest_key,
                "manifest_digest": data.manifest_digest,
                "sample_count": data.sample_count,
                "size_bytes": data.size_bytes,
                "created_by": data.created_by,
                "metadata": data.metadata_,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class ManifestResponse(BaseModel):
    """Response model for ``GET .../versions/{vid}/manifest``.

    The full JSON manifest is returned (small — even 100K samples at
    ~200 bytes each = ~20 MB which is fine for a single API call; if
    it grows past that we'll switch to streaming).

    NOTE: the manifest has ``schema`` and ``version`` fields at the
    protocol level; we rename them with a ``manifest_`` prefix here to
    avoid clashing with Pydantic ``BaseModel`` reserved names.
    """

    manifest_schema: str
    manifest_version: str
    dataset_id: str
    task_kind: str
    sample_count: int
    size_bytes: int
    samples: list[dict[str, Any]]


# ─── Sample ─────────────────────────────────────────────────────


class SampleRead(ORMModel):
    """Response model for a Sample."""

    id: str
    version_id: str
    tenant_id: str
    blob_key: str
    relative_path: str
    annotation_key: str | None
    label: str | None
    size_bytes: int
    split: Split
    blob_digest: str
    created_at: datetime


class SampleSplitUpdate(BaseModel):
    """Request body for changing a single sample's split."""

    split: Split


class SplitRequest(BaseModel):
    """Request body for ``POST .../versions/{vid}:split``.

    Two strategies:

    * ``manual`` — caller provides an explicit list of
      ``{"sample_id": "...", "split": "TRAIN"}`` pairs.  Useful for
      the UI's drag-and-drop assignment.
    * ``stratified`` — caller provides ``ratios`` and (optionally) a
      ``stratify_by`` field (``label`` is the only M1.4 value).
      Samples are assigned deterministically (sorted by id) to keep
      the split reproducible.
    """

    strategy: Literal["manual", "stratified"]
    # manual
    assignments: list[dict[str, str]] | None = None
    # stratified
    ratios: dict[str, float] | None = None
    stratify_by: Literal["label"] | None = None
    seed: int = 42


# ─── Import ─────────────────────────────────────────────────────


class ImportRequest(BaseModel):
    """Request body for ``POST .../versions/{vid}/import``.

    Two source kinds in M1.4:

    * ``LOCAL`` — ``source_descriptor.path`` points to a directory on
      the server. The server walks it, uploads each file via
      ``storage.put_blob``, and creates Sample rows.  The
      ``allowed_root`` field (optional) constrains the walk to a single
      subtree.
    * ``ZIP`` — a ZIP archive has already been uploaded via a separate
      ``PUT /api/v1/import-jobs/{job_id}/blob`` endpoint
      (out of scope for M1.4); in M1.4 we only support ZIPs that
      were uploaded as ``imports/{version_id}.zip`` via a future
      direct upload — for the test suite we exercise the LOCAL
      source and a directly-mounted ZIP key (set
      ``source_descriptor.blob_key``).
    """

    source_kind: Literal["LOCAL", "ZIP"]
    source_descriptor: dict[str, Any] = Field(default_factory=dict)


class ImportJobRead(ORMModel):
    """Response model for an ImportJob."""

    id: str
    tenant_id: str
    version_id: str
    source_kind: ImportSourceKind
    source_descriptor: dict[str, Any]
    status: ImportStatus
    total_samples: int
    processed_samples: int
    total_bytes: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImportJobCreated(BaseModel):
    """Response body for the 202 returned by ``.../import``."""

    job_id: str


__all__ = [
    "DatasetCreate",
    "DatasetRead",
    "DatasetUpdate",
    "DatasetVersionCreate",
    "DatasetVersionRead",
    "ImportJobCreated",
    "ImportJobRead",
    "ImportRequest",
    "ManifestResponse",
    "ORMModel",
    "SampleRead",
    "SampleSplitUpdate",
    "SplitRequest",
    "VersionRef",
]
