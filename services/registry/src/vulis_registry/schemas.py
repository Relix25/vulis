"""Pydantic v2 request/response schemas for the registry service.

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

from vulis_registry.models import ModelStatus

# ─── Shared ─────────────────────────────────────────────────────

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]

TaskKindStr = Literal["DETECTION", "CLASSIFICATION", "SEGMENTATION"]

# Transition verb set (mirrors vulis_registry.state_machine.Verb).
TransitionVerbStr = Literal[
    "submit_for_review",
    "approve",
    "reject",
    "deploy",
    "archive",
]


_SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


def _parse_semver(s: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(s)
    if not m:
        raise ValueError(f"Invalid SemVer: {s!r} (expected '<major>.<minor>.<patch>')")
    return int(m["major"]), int(m["minor"]), int(m["patch"])


class ORMModel(BaseModel):
    """Base for response models that mirror an ORM row."""

    model_config = ConfigDict(from_attributes=True)


# ─── Model ──────────────────────────────────────────────────────


class ModelCreate(BaseModel):
    """Request body for ``POST /api/v1/models``."""

    project_id: NonEmptyStr
    name: NonEmptyStr
    description: str | None = Field(default=None, max_length=4096)
    task_kind: TaskKindStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelUpdate(BaseModel):
    """Request body for ``PATCH /api/v1/models/{id}`` (all fields optional)."""

    name: NonEmptyStr | None = None
    description: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] | None = None


class ModelRead(ORMModel):
    """Response model for a Model."""

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


# ─── ModelVersion ──────────────────────────────────────────────


class ModelVersionCreate(BaseModel):
    """First half of the multipart upload body for ``POST ...:upload``.

    The actual ONNX file is sent as the ``file`` multipart field. The
    metadata fields (semver, dataset link, ...) are sent as form
    fields alongside it. Either ``version`` (string) or explicit
    ``major``/``minor``/``patch`` may be provided; defaults are
    ``0.0.1`` (first draft).
    """

    version: str | None = Field(default=None, description="SemVer string 'major.minor.patch'")
    major: int | None = Field(default=None, ge=0)
    minor: int | None = Field(default=None, ge=0)
    patch: int | None = Field(default=None, ge=0)
    created_by: NonEmptyStr
    trained_on_dataset_version_id: str | None = None
    mlflow_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolve_semver(self) -> tuple[int, int, int]:
        if self.version is not None:
            return _parse_semver(self.version)
        return (
            self.major if self.major is not None else 0,
            self.minor if self.minor is not None else 0,
            self.patch if self.patch is not None else 1,
        )


class ModelVersionRead(ORMModel):
    """Response model for a ModelVersion."""

    id: str
    tenant_id: str
    model_id: str
    major: int
    minor: int
    patch: int
    status: ModelStatus
    artifact_key: str
    artifact_digest: str
    artifact_size_bytes: int
    trained_on_dataset_version_id: str | None
    mlflow_run_id: str | None
    onnx_opset: int
    model_card: str | None
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _translate_metadata_(cls, data):
        if hasattr(data, "metadata_"):
            return {
                "id": data.id,
                "tenant_id": data.tenant_id,
                "model_id": data.model_id,
                "major": data.major,
                "minor": data.minor,
                "patch": data.patch,
                "status": data.status,
                "artifact_key": data.artifact_key,
                "artifact_digest": data.artifact_digest,
                "artifact_size_bytes": data.artifact_size_bytes,
                "trained_on_dataset_version_id": data.trained_on_dataset_version_id,
                "mlflow_run_id": data.mlflow_run_id,
                "onnx_opset": data.onnx_opset,
                "model_card": data.model_card,
                "created_by": data.created_by,
                "metadata": data.metadata_,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class PromoteRequest(BaseModel):
    """Request body for ``POST .../versions/{vid}:promote``.

    The ``verb`` is the action to apply (e.g. ``submit_for_review``,
    ``approve``, ``reject``, ``deploy``, ``archive``). The state
    machine in ``state_machine.apply_transition`` validates the
    transition given the current ``ModelVersion.status``.
    """

    verb: TransitionVerbStr


# ─── OnnxTensorSpec ────────────────────────────────────────────


class OnnxTensorSpecRead(ORMModel):
    """Response model for an OnnxTensorSpec."""

    id: str
    version_id: str
    direction: str
    name: str
    dtype: str
    shape: list[int]


__all__ = [
    "ModelCreate",
    "ModelRead",
    "ModelUpdate",
    "ModelVersionCreate",
    "ModelVersionRead",
    "ORMModel",
    "OnnxTensorSpecRead",
    "PromoteRequest",
]
