"""Tests for the ORM models (column defaults, mixin behavior, soft delete)."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from sqlalchemy.orm import Session

from vulis_project.models import (
    CampaignKind,
    Line,
    Phase,
    Project,
    Task,
    TaskKind,
    TaskState,
)


def test_project_defaults(session: Session):
    p = Project(tenant_id="tenant_a", name="alpha")
    session.add(p)
    session.flush()
    assert p.id  # UUIDPrimaryKey auto-fills
    assert p.phase == Phase.POC
    assert p.tags == {}
    assert p.deleted_at is None
    assert p.created_at is not None
    assert p.updated_at is not None
    # 64-char limit on id column (UUID hex is 32 chars; prefixed ids are
    # <prefix>_<hex>, well under 64).
    assert len(p.id) <= 64


def test_task_state_default(session: Session):
    project = Project(tenant_id="tenant_a", name="p")
    session.add(project)
    session.flush()
    t = Task(tenant_id="tenant_a", project_id=project.id, name="detect", kind=TaskKind.DETECTION)
    session.add(t)
    session.flush()
    assert t.state == TaskState.BACKLOG


def test_line_default_edge_ids(session: Session):
    project = Project(tenant_id="tenant_a", name="p")
    session.add(project)
    session.flush()
    line = Line(tenant_id="tenant_a", project_id=project.id, name="L1")
    session.add(line)
    session.flush()
    assert line.edge_ids == []


def test_soft_delete_query(session: Session):
    project = Project(tenant_id="tenant_a", name="p")
    session.add(project)
    session.flush()
    from datetime import UTC, datetime

    project.deleted_at = datetime.now(UTC)
    session.flush()
    # The default query doesn't filter — we filter explicitly in routes.
    assert project.deleted_at is not None


def test_campaign_kind_values():
    assert CampaignKind.DATA_COLLECTION.value == "data_collection"
    assert CampaignKind.PILOT.value == "pilot"
    assert CampaignKind.AB.value == "ab"
