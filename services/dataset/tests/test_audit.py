"""Tests for the dataset audit helper."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import json

from sqlalchemy import select
from vulis_schemas import Base

from vulis_dataset.audit import log_audit


def test_log_audit_writes_one_row(session):
    log_audit(
        session,
        tenant_id="tenant_test",
        actor="alice",
        action="dataset.create",
        target_type="dataset",
        target_id="ds_abc",
        diff={"name": "alpha"},
    )
    session.commit()

    table = Base.metadata.tables["audit_events"]
    rows = list(session.execute(select(table)))
    assert len(rows) == 1
    row = rows[0]
    assert row.tenant_id == "tenant_test"
    assert row.actor == "alice"
    assert row.action == "dataset.create"
    assert row.target_type == "dataset"
    assert row.target_id == "ds_abc"
    assert json.loads(row.diff) == {"name": "alpha"}


def test_log_audit_without_diff_writes_null(session):
    log_audit(
        session,
        tenant_id="tenant_test",
        actor="alice",
        action="dataset.delete",
        target_type="dataset",
        target_id="ds_abc",
    )
    session.commit()
    table = Base.metadata.tables["audit_events"]
    row = session.execute(select(table)).first()
    assert row.diff is None
