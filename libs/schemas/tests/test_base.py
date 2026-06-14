# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Smoke tests for the shared Base + mixins (no real DB required)."""

from __future__ import annotations

import uuid

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from vulis_schemas import Base, TenantScoped, Timestamped, UUIDPrimaryKey


def test_metadata_has_shared_tables() -> None:
    tables = set(Base.metadata.tables.keys())
    assert "tenants" in tables
    assert "audit_events" in tables


def test_naming_convention_applied_to_constraints() -> None:
    # Render the CREATE TABLE DDL and verify the FK follows the convention.
    from sqlalchemy.schema import CreateTable

    audit = Base.metadata.tables["audit_events"]
    engine = create_engine("sqlite:///:memory:")
    ddl = str(CreateTable(audit).compile(engine))
    assert "fk_audit_events_tenant_id_tenants" in ddl


def test_create_all_in_sqlite_in_memory() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insp_tables = set(engine.dialect.get_table_names(engine.connect()))
    assert {"tenants", "audit_events"}.issubset(insp_tables)


def test_mixin_combination_works() -> None:
    # Define a transient model that combines all mixins and verify it
    # materializes correctly against a fresh SQLite DB.
    class Widget(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
        __tablename__ = "test_widgets"
        name: Mapped[str] = mapped_column(String(255))

    engine = create_engine("sqlite:///:memory:")
    # Create ALL tables (tenants + audit_events + the new Widget).
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    tenant_id = uuid.uuid4().hex

    with Session() as s:
        # Need a tenant row first (FK).
        s.execute(
            Base.metadata.tables["tenants"].insert().values(
                id=tenant_id, display_name="t"
            )
        )
        w = Widget(name="hello")  # type: ignore[call-arg]
        w.tenant_id = tenant_id
        s.add(w)
        s.commit()
        rows = s.scalars(select(Widget)).all()
        assert len(rows) == 1
        assert rows[0].name == "hello"
        assert rows[0].created_at is not None
        assert rows[0].updated_at is not None


def test_audit_events_table_shape() -> None:
    audit = Base.metadata.tables["audit_events"]
    cols = set(audit.columns.keys())
    expected = {
        "id",
        "tenant_id",
        "actor",
        "action",
        "target_type",
        "target_id",
        "diff",
        "correlation_id",
        "occurred_at",
    }
    assert expected == cols
