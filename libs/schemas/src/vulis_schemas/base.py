"""SQLAlchemy declarative base + shared mixins for Vulis.

All Vulis ORM models derive from ``Base``. The naming convention below keeps
constraint names stable across services and makes Alembic autogenerate
predictable diffs.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "Base",
    "NamingConvention",
    "TenantScoped",
    "Timestamped",
    "UUIDPrimaryKey",
    "VulisMetaData",
]


# A consistent naming convention is essential for Alembic autogenerate to
# produce stable constraint names across revisions and across services.
NamingConvention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# A single MetaData with the Vulis naming convention. Shared by the
# declarative Base and by any explicit Table() definitions.
VulisMetaData = MetaData(naming_convention=NamingConvention)


# The single declarative base shared across Vulis services.
class Base(DeclarativeBase):
    metadata = VulisMetaData


# ─── Mixins ──────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDPrimaryKey:
    """Mixin: a UUID (hex string) primary key named ``id``.

    We store IDs as their string form (``"proj_<hex>"``) to keep the typed
    prefix visible at the database level — useful for debugging and for
    cross-table FK comprehension.
    """

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )


class TenantScoped:
    """Mixin: tenant_id column + FK to the tenants table.

    Multi-tenant isolation is enforced at the query layer (RLS or service-
    level filtering), not at the column level — but every row carries its
    tenant for that purpose.
    """

    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class Timestamped:
    """Mixin: created_at / updated_at columns (UTC, timezone-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )


class SoftDelete:
    """Mixin: deleted_at column for soft deletes (NULL = active)."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )


# ─── Core tables (created by the initial migration) ──────────
#
# We declare the bare minimum shared tables here (tenants, audit_events) so
# that mixins referencing them resolve cleanly. Service-specific tables
# (projects, datasets, ...) live in their service packages and import Base.


from sqlalchemy import Column, Table  # noqa: E402

# `tenants` — referenced by TenantScoped. Lightweight: id + display name.
Table(
    "tenants",
    Base.metadata,
    Column("id", String(64), primary_key=True),
    Column("display_name", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
    Column("keycloak_realm", String(128), nullable=True),
)

# `audit_events` — the append-only audit trail (ARCHITECTURE.md §6).
# Every state-changing operation in every service writes exactly one row.
Table(
    "audit_events",
    Base.metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "tenant_id",
        String(64),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    Column("actor", String(255), nullable=False),
    Column("action", String(128), nullable=False, index=True),
    Column("target_type", String(64), nullable=False, index=True),
    Column("target_id", String(64), nullable=False, index=True),
    Column("diff", String, nullable=True),  # JSON-encoded, see service code
    Column("correlation_id", String(64), nullable=True, index=True),
    Column(
        "occurred_at",
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        index=True,
    ),
)
