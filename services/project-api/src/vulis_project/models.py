"""SQLAlchemy ORM models for the project-api.

Tables created by migration 0002_projects.py. If you change a model, you
MUST change the migration in lockstep — the project doesn't rely on
Alembic autogenerate for this service.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from vulis_schemas import Base, SoftDelete, TenantScoped, Timestamped, UUIDPrimaryKey

# ─── Enums ─────────────────────────────────────────────────────


class Phase(str, enum.Enum):
    """Project lifecycle phase."""

    POC = "POC"
    PILOT = "PILOT"
    PRE_PROD = "PRE_PROD"
    PROD = "PROD"
    ARCHIVED = "ARCHIVED"


class TaskKind(str, enum.Enum):
    """Kind of ML task attached to a project."""

    DETECTION = "DETECTION"
    CLASSIFICATION = "CLASSIFICATION"
    SEGMENTATION = "SEGMENTATION"


class TaskState(str, enum.Enum):
    """Lifecycle state of a Task. Transitions are governed by state_machine.py."""

    BACKLOG = "BACKLOG"
    IN_PROGRESS = "IN_PROGRESS"
    IN_VALIDATION = "IN_VALIDATION"
    DEPLOYED = "DEPLOYED"
    MONITORING = "MONITORING"
    RETRAINING = "RETRAINING"


class CampaignKind(str, enum.Enum):
    """Kind of in-factory campaign attached to a project."""

    DATA_COLLECTION = "data_collection"
    VALIDATION = "validation"
    PILOT = "pilot"
    AB = "ab"


# ─── Tables ────────────────────────────────────────────────────


class Project(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    """A Vulis project — a container for lines, tasks, and campaigns.

    `tags` is a free-form JSONB dict (e.g. ``{"plant": "Lyon", "BU": "auto"}``)
    for filtering / grouping in the UI.
    """

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    phase: Mapped[Phase] = mapped_column(SAEnum(Phase), nullable=False, default=Phase.POC)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    lines: Mapped[list[Line]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Line(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """A production line attached to a project.

    `edge_ids` lists the edge nodes (M1.6 fleet) currently running this
    line. Stored as JSONB (not a relational table) for M1.3 — replaced by
    an association table once the fleet service lands.
    """

    __tablename__ = "lines"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    edge_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    project: Mapped[Project] = relationship(back_populates="lines")


class Task(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """A single ML task on a project, with its own lifecycle state.

    The state machine is enforced in ``state_machine.py`` — never
    mutate ``state`` directly from a route.
    """

    __tablename__ = "tasks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[TaskKind] = mapped_column(SAEnum(TaskKind), nullable=False)
    state: Mapped[TaskState] = mapped_column(
        SAEnum(TaskState), nullable=False, default=TaskState.BACKLOG
    )

    project: Mapped[Project] = relationship(back_populates="tasks")


class Campaign(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """An in-factory campaign (data collection, validation, pilot, A/B).

    A campaign runs for a bounded period on one or more production lines.
    """

    __tablename__ = "campaigns"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[CampaignKind] = mapped_column(SAEnum(CampaignKind), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    project: Mapped[Project] = relationship(back_populates="campaigns")


__all__ = [
    "Base",
    "Campaign",
    "CampaignKind",
    "Line",
    "Phase",
    "Project",
    "Task",
    "TaskKind",
    "TaskState",
]
