"""Tests for the audit helper."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import json

from sqlalchemy import select
from vulis_schemas import Base

from vulis_project.audit import log_audit


def test_log_audit_writes_one_row(session):
    log_audit(
        session,
        tenant_id="tenant_a",
        actor="alice",
        action="project.create",
        target_type="project",
        target_id="proj_abc",
        diff={"name": "alpha"},
    )
    session.commit()

    # Query the audit_events table via the shared metadata.
    table = Base.metadata.tables["audit_events"]
    rows = list(session.execute(select(table)))
    assert len(rows) == 1
    row = rows[0]  # Row object (tuple-like) with named attributes
    assert row.tenant_id == "tenant_a"
    assert row.actor == "alice"
    assert row.action == "project.create"
    assert row.target_type == "project"
    assert row.target_id == "proj_abc"
    # diff was JSON-serialized
    assert json.loads(row.diff) == {"name": "alpha"}


def test_log_audit_without_diff_writes_null(session):
    log_audit(
        session,
        tenant_id="tenant_a",
        actor="alice",
        action="project.delete",
        target_type="project",
        target_id="proj_abc",
    )
    session.commit()
    table = Base.metadata.tables["audit_events"]
    row = session.execute(select(table)).first()
    assert row.diff is None


def test_log_audit_includes_correlation_id_from_context(session, monkeypatch):
    from vulis_core import set_correlation_id

    set_correlation_id("corr-xyz")
    log_audit(
        session,
        tenant_id="tenant_a",
        actor="alice",
        action="project.create",
        target_type="project",
        target_id="proj_abc",
    )
    session.commit()
    table = Base.metadata.tables["audit_events"]
    row = session.execute(select(table)).first()
    assert row.correlation_id == "corr-xyz"
    set_correlation_id(None)  # cleanup
