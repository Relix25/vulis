"""Pydantic v2 request/response schemas for the project-api.

These are the API contract — keep them stable. ORM models can change as
needed; schemas should only change with a deprecation cycle.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from vulis_project.models import CampaignKind, Phase, TaskKind, TaskState

# ─── Shared ─────────────────────────────────────────────────────

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class ORMModel(BaseModel):
    """Base for response models that mirror an ORM row."""

    model_config = ConfigDict(from_attributes=True)


# ─── Project ────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    """Request body for ``POST /api/v1/projects``."""

    name: NonEmptyStr
    description: str | None = Field(default=None, max_length=4096)
    phase: Phase = Phase.POC
    tags: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    """Request body for ``PATCH /api/v1/projects/{id}`` (all fields optional)."""

    name: NonEmptyStr | None = None
    description: str | None = Field(default=None, max_length=4096)
    phase: Phase | None = None
    tags: dict[str, Any] | None = None


class ProjectRead(ORMModel):
    """Response model for a Project."""

    id: str
    tenant_id: str
    name: str
    description: str | None
    phase: Phase
    tags: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


# ─── Line ───────────────────────────────────────────────────────


class LineCreate(BaseModel):
    """Request body for ``POST /api/v1/projects/{pid}/lines``."""

    name: NonEmptyStr
    edge_ids: list[str] = Field(default_factory=list)


class LineRead(ORMModel):
    """Response model for a Line."""

    id: str
    tenant_id: str
    project_id: str
    name: str
    edge_ids: list[str]
    created_at: datetime
    updated_at: datetime


# ─── Task ───────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    """Request body for ``POST /api/v1/projects/{pid}/tasks``."""

    name: NonEmptyStr
    kind: TaskKind


class TaskTransitionRequest(BaseModel):
    """Request body for ``POST /api/v1/tasks/{tid}:transition``.

    The transition verb is the "what should happen" — e.g. ``start``,
    ``submit``, ``approve``. The current state + verb are validated by
    ``state_machine.apply_transition``.
    """

    verb: str = Field(min_length=1, max_length=32)


class TaskRead(ORMModel):
    """Response model for a Task."""

    id: str
    tenant_id: str
    project_id: str
    name: str
    kind: TaskKind
    state: TaskState
    created_at: datetime
    updated_at: datetime


# ─── Campaign ───────────────────────────────────────────────────


class CampaignCreate(BaseModel):
    """Request body for ``POST /api/v1/projects/{pid}/campaigns``."""

    name: NonEmptyStr
    kind: CampaignKind
    description: str | None = Field(default=None, max_length=4096)


class CampaignRead(ORMModel):
    """Response model for a Campaign."""

    id: str
    tenant_id: str
    project_id: str
    name: str
    kind: CampaignKind
    description: str | None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "CampaignCreate",
    "CampaignRead",
    "LineCreate",
    "LineRead",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "TaskCreate",
    "TaskRead",
    "TaskTransitionRequest",
]
