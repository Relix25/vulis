"""Initial schema: tenants + audit_events.

Revision ID: 0001
Revises:
Create Date: 2026-06-14

The bulk of the business tables (projects, lines, tasks, datasets, models,
...) are added in later revisions as the corresponding services land
(M1.3+). This initial migration only creates the two shared, dependency-free
tables that mixins reference.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── tenants ──────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("keycloak_realm", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )

    # ─── audit_events (append-only) ──────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("diff", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )

    # Indexes — the audit trail is queried by tenant, action, target, time.
    op.create_index(op.f("ix_audit_events_tenant_id"), "audit_events", ["tenant_id"])
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"])
    op.create_index(op.f("ix_audit_events_target_type"), "audit_events", ["target_type"])
    op.create_index(op.f("ix_audit_events_target_id"), "audit_events", ["target_id"])
    op.create_index(op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"])
    op.create_index(op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"])

    # Prevent any UPDATE or DELETE on audit_events — it is append-only.
    # We enforce this at the DB layer with a trigger that raises on UPDATE/DELETE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION vulis_block_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only (action=%)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION vulis_block_audit_mutation();

        CREATE TRIGGER audit_events_no_delete
            BEFORE DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION vulis_block_audit_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events;
        DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;
        DROP FUNCTION IF EXISTS vulis_block_audit_mutation();
        """
    )
    op.drop_index(op.f("ix_audit_events_occurred_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_target_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_target_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_tenant_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("tenants")
