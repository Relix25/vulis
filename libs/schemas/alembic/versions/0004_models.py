"""Add models, model_versions, model_onnx_specs (M1.5).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-15

The M1.5 model registry introduces three tables:

* ``models``           — named, tenant-scoped, soft-deletable, FK to projects.
* ``model_versions``   — SemVer-released children of a Model, with a unique
                         constraint on ``(model_id, major, minor, patch)``,
                         status workflow, content-addressed artifact
                         reference, and a FK to ``dataset_versions``
                         (SET NULL on delete — we keep the model even if
                         the dataset is purged).
* ``model_onnx_specs`` — per-tensor input/output shape + dtype, captured
                         at upload from ``onnx.shape_inference``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── models ───────────────────────────────────────────────
    op.create_table(
        "models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata_",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_models_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_models_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
    )
    op.create_index(op.f("ix_models_tenant_id"), "models", ["tenant_id"])
    op.create_index(op.f("ix_models_project_id"), "models", ["project_id"])
    op.create_index(op.f("ix_models_deleted_at"), "models", ["deleted_at"])
    op.create_index(op.f("ix_models_task_kind"), "models", ["task_kind"])

    # ─── model_versions ───────────────────────────────────────
    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("major", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("patch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "INTERNAL_REVIEW",
                "STAGING",
                "APPROVED",
                "DEPLOYED",
                "REJECTED",
                "ARCHIVED",
                name="modelstatus",
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("artifact_key", sa.String(length=512), nullable=False),
        sa.Column("artifact_digest", sa.String(length=128), nullable=False),
        sa.Column(
            "artifact_size_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "trained_on_dataset_version_id", sa.String(length=64), nullable=True
        ),
        sa.Column("mlflow_run_id", sa.String(length=128), nullable=True),
        sa.Column(
            "onnx_opset", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("model_card", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata_",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_model_versions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_model_versions_model_id_models"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trained_on_dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_model_versions_trained_on_dataset_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "model_id",
            "major",
            "minor",
            "patch",
            name=op.f("uq_model_versions_semver"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_versions")),
    )
    op.create_index(
        op.f("ix_model_versions_tenant_id"), "model_versions", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_model_versions_model_id"), "model_versions", ["model_id"]
    )
    op.create_index(
        op.f("ix_model_versions_status"), "model_versions", ["status"]
    )
    op.create_index(
        op.f("ix_model_versions_trained_on_dataset_version_id"),
        "model_versions",
        ["trained_on_dataset_version_id"],
    )
    op.create_index(
        op.f("ix_model_versions_artifact_digest"),
        "model_versions",
        ["artifact_digest"],
    )

    # ─── model_onnx_specs ─────────────────────────────────────
    op.create_table(
        "model_onnx_specs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dtype", sa.String(length=64), nullable=False),
        sa.Column(
            "shape",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["model_versions.id"],
            name=op.f("fk_model_onnx_specs_version_id_model_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_onnx_specs")),
    )
    op.create_index(
        op.f("ix_model_onnx_specs_version_id"),
        "model_onnx_specs",
        ["version_id"],
    )


def downgrade() -> None:
    # Drop in reverse order (children first because of FKs).
    op.drop_index(
        op.f("ix_model_onnx_specs_version_id"), table_name="model_onnx_specs"
    )
    op.drop_table("model_onnx_specs")

    op.drop_index(
        op.f("ix_model_versions_artifact_digest"), table_name="model_versions"
    )
    op.drop_index(
        op.f("ix_model_versions_trained_on_dataset_version_id"),
        table_name="model_versions",
    )
    op.drop_index(op.f("ix_model_versions_status"), table_name="model_versions")
    op.drop_index(op.f("ix_model_versions_model_id"), table_name="model_versions")
    op.drop_index(op.f("ix_model_versions_tenant_id"), table_name="model_versions")
    op.drop_table("model_versions")
    # Drop the modelstatus enum created implicitly by the column type.
    op.execute("DROP TYPE IF EXISTS modelstatus")

    op.drop_index(op.f("ix_models_task_kind"), table_name="models")
    op.drop_index(op.f("ix_models_deleted_at"), table_name="models")
    op.drop_index(op.f("ix_models_project_id"), table_name="models")
    op.drop_index(op.f("ix_models_tenant_id"), table_name="models")
    op.drop_table("models")
