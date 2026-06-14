"""Add projects, lines, tasks, campaigns (M1.3).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

The first four business tables of the project-api service. Each row is
multi-tenant (``tenant_id`` FK → ``tenants.id``) and most children CASCADE
off their parent project.

Indexes:
    * ``ix_lines_project_id``, ``ix_tasks_project_id``, ``ix_campaigns_project_id``
      — the hot read path is "give me the children of this project".
    * The shared ``ix_*_tenant_id`` indexes (created by TenantScoped) handle
      tenant scoping; we don't add redundant composite indexes here.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── projects ───────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "phase",
            sa.Enum(
                "POC", "PILOT", "PRE_PROD", "PROD", "ARCHIVED",
                name="phase",
            ),
            nullable=False,
            server_default="POC",
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_projects_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_tenant_id"), "projects", ["tenant_id"])
    op.create_index(op.f("ix_projects_deleted_at"), "projects", ["deleted_at"])
    op.create_index(op.f("ix_projects_phase"), "projects", ["phase"])

    # ─── lines ──────────────────────────────────────────────────
    op.create_table(
        "lines",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "edge_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_lines_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_lines_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lines")),
    )
    op.create_index(op.f("ix_lines_tenant_id"), "lines", ["tenant_id"])
    op.create_index(op.f("ix_lines_project_id"), "lines", ["project_id"])

    # ─── tasks ──────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "DETECTION", "CLASSIFICATION", "SEGMENTATION",
                name="taskkind",
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "BACKLOG", "IN_PROGRESS", "IN_VALIDATION", "DEPLOYED",
                "MONITORING", "RETRAINING",
                name="taskstate",
            ),
            nullable=False,
            server_default="BACKLOG",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_tasks_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_tenant_id"), "tasks", ["tenant_id"])
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"])
    op.create_index(op.f("ix_tasks_state"), "tasks", ["state"])

    # ─── campaigns ──────────────────────────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "data_collection", "validation", "pilot", "ab",
                name="campaignkind",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_campaigns_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_campaigns_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
    )
    op.create_index(op.f("ix_campaigns_tenant_id"), "campaigns", ["tenant_id"])
    op.create_index(op.f("ix_campaigns_project_id"), "campaigns", ["project_id"])
    op.create_index(op.f("ix_campaigns_kind"), "campaigns", ["kind"])


def downgrade() -> None:
    # Drop in reverse order (children first because of FKs).
    op.drop_index(op.f("ix_campaigns_kind"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_project_id"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_tenant_id"), table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_index(op.f("ix_tasks_state"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_tenant_id"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_lines_project_id"), table_name="lines")
    op.drop_index(op.f("ix_lines_tenant_id"), table_name="lines")
    op.drop_table("lines")

    op.drop_index(op.f("ix_projects_phase"), table_name="projects")
    op.drop_index(op.f("ix_projects_deleted_at"), table_name="projects")
    op.drop_index(op.f("ix_projects_tenant_id"), table_name="projects")
    op.drop_table("projects")
