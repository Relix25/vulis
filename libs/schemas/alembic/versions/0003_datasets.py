"""Add datasets, dataset_versions, dataset_samples, dataset_import_jobs (M1.4).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15

The M1.4 dataset service introduces four tables:

* ``datasets`` — named, tenant-scoped, soft-deletable, FK to projects.
* ``dataset_versions`` — SemVer-released children of a dataset, with a
  unique constraint on ``(dataset_id, major, minor, patch)`` and a
  content-addressed manifest. CASCADE on dataset delete.
* ``dataset_samples`` — individual sample rows. Tenant-scoped for
  isolation, FK to version with CASCADE, ``blob_key`` indexed for
  content-addressed lookups, composite ``(version_id, split)`` index
  for the "give me the train split" hot read.
* ``dataset_import_jobs`` — async import tracking. Indexed by status
  for the fleet worker's polling and by version for the UI.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── datasets ───────────────────────────────────────────────
    op.create_table(
        "datasets",
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
            name=op.f("fk_datasets_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_datasets_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_index(op.f("ix_datasets_tenant_id"), "datasets", ["tenant_id"])
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"])
    op.create_index(op.f("ix_datasets_deleted_at"), "datasets", ["deleted_at"])
    op.create_index(op.f("ix_datasets_task_kind"), "datasets", ["task_kind"])

    # ─── dataset_versions ───────────────────────────────────────
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("major", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("patch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("manifest_key", sa.String(length=512), nullable=True),
        sa.Column("manifest_digest", sa.String(length=128), nullable=True),
        sa.Column(
            "sample_count", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "size_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
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
            name=op.f("fk_dataset_versions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_versions_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "major",
            "minor",
            "patch",
            name=op.f("uq_dataset_versions_semver"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
    )
    op.create_index(
        op.f("ix_dataset_versions_tenant_id"), "dataset_versions", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_dataset_versions_dataset_id"), "dataset_versions", ["dataset_id"]
    )
    op.create_index(
        op.f("ix_dataset_versions_is_published"),
        "dataset_versions",
        ["is_published"],
    )

    # ─── dataset_samples ────────────────────────────────────────
    op.create_table(
        "dataset_samples",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("blob_key", sa.String(length=512), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("annotation_key", sa.String(length=512), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "size_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "split",
            sa.Enum("TRAIN", "VAL", "TEST", name="datasplit"),
            nullable=False,
            server_default="TRAIN",
        ),
        sa.Column("blob_digest", sa.String(length=128), nullable=False),
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
            ["dataset_versions.id"],
            name=op.f("fk_dataset_samples_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_dataset_samples_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_samples")),
    )
    op.create_index(
        op.f("ix_dataset_samples_tenant_id"), "dataset_samples", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_dataset_samples_version_id"), "dataset_samples", ["version_id"]
    )
    op.create_index(
        op.f("ix_dataset_samples_blob_key"), "dataset_samples", ["blob_key"]
    )
    op.create_index(
        op.f("ix_dataset_samples_label"), "dataset_samples", ["label"]
    )
    # Composite — "give me the train samples of this version".
    op.create_index(
        "ix_dataset_samples_version_split",
        "dataset_samples",
        ["version_id", "split"],
    )

    # ─── dataset_import_jobs ────────────────────────────────────
    op.create_table(
        "dataset_import_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column(
            "source_kind",
            sa.Enum("LOCAL", "ZIP", "CVAT", "S3", name="importsourcekind"),
            nullable=False,
        ),
        sa.Column(
            "source_descriptor",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "DONE", "FAILED", name="importstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "total_samples",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "processed_samples",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_dataset_import_jobs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_import_jobs_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_import_jobs")),
    )
    op.create_index(
        op.f("ix_dataset_import_jobs_tenant_id"),
        "dataset_import_jobs",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_dataset_import_jobs_version_id"),
        "dataset_import_jobs",
        ["version_id"],
    )
    op.create_index(
        "ix_dataset_import_jobs_status",
        "dataset_import_jobs",
        ["status"],
    )


def downgrade() -> None:
    # Drop in reverse order (children first because of FKs).
    op.drop_index("ix_dataset_import_jobs_status", table_name="dataset_import_jobs")
    op.drop_index(op.f("ix_dataset_import_jobs_version_id"), table_name="dataset_import_jobs")
    op.drop_index(op.f("ix_dataset_import_jobs_tenant_id"), table_name="dataset_import_jobs")
    op.drop_table("dataset_import_jobs")

    op.drop_index("ix_dataset_samples_version_split", table_name="dataset_samples")
    op.drop_index(op.f("ix_dataset_samples_label"), table_name="dataset_samples")
    op.drop_index(op.f("ix_dataset_samples_blob_key"), table_name="dataset_samples")
    op.drop_index(op.f("ix_dataset_samples_version_id"), table_name="dataset_samples")
    op.drop_index(op.f("ix_dataset_samples_tenant_id"), table_name="dataset_samples")
    op.drop_table("dataset_samples")
    # Drop the split enum created implicitly by the column type.
    op.execute("DROP TYPE IF EXISTS datasplit")

    op.drop_index(op.f("ix_dataset_versions_is_published"), table_name="dataset_versions")
    op.drop_index(op.f("ix_dataset_versions_dataset_id"), table_name="dataset_versions")
    op.drop_index(op.f("ix_dataset_versions_tenant_id"), table_name="dataset_versions")
    op.drop_table("dataset_versions")

    op.drop_index(op.f("ix_datasets_task_kind"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_deleted_at"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_project_id"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_tenant_id"), table_name="datasets")
    op.drop_table("datasets")

    # Drop the other enums created implicitly.
    op.execute("DROP TYPE IF EXISTS importstatus")
    op.execute("DROP TYPE IF EXISTS importsourcekind")
