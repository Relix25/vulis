"""Tests for the dataset ORM models (column defaults, mixin behavior)."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from sqlalchemy.orm import Session

from vulis_dataset.models import (
    Dataset,
    DatasetVersion,
    ImportJob,
    ImportSourceKind,
    ImportStatus,
    Sample,
    Split,
)


def _make_dataset(session: Session, project_id: str = "project_test") -> Dataset:
    d = Dataset(
        tenant_id="tenant_test",
        project_id=project_id,
        name="alpha",
        task_kind="DETECTION",
    )
    session.add(d)
    session.flush()
    return d


def test_dataset_defaults(session: Session):
    d = _make_dataset(session)
    assert d.id
    assert len(d.id) <= 64
    assert d.metadata_ == {}
    assert d.deleted_at is None
    assert d.created_at is not None
    assert d.updated_at is not None


def test_dataset_soft_delete(session: Session):
    d = _make_dataset(session)
    from datetime import UTC, datetime

    d.deleted_at = datetime.now(UTC)
    session.flush()
    assert d.deleted_at is not None


def test_dataset_version_defaults(session: Session):
    d = _make_dataset(session)
    v = DatasetVersion(
        tenant_id="tenant_test",
        dataset_id=d.id,
        major=0,
        minor=0,
        patch=1,
        created_by="alice",
    )
    session.add(v)
    session.flush()
    assert v.id
    assert v.is_published is False
    assert v.manifest_key is None
    assert v.manifest_digest is None
    assert v.sample_count == 0
    assert v.size_bytes == 0
    assert v.metadata_ == {}


def test_dataset_version_semver_unique(session: Session):
    d = _make_dataset(session)
    a = DatasetVersion(
        tenant_id="tenant_test",
        dataset_id=d.id,
        major=1,
        minor=2,
        patch=3,
        created_by="alice",
    )
    b = DatasetVersion(
        tenant_id="tenant_test",
        dataset_id=d.id,
        major=1,
        minor=2,
        patch=3,
        created_by="bob",
    )
    session.add_all([a, b])
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_sample_defaults(session: Session):
    d = _make_dataset(session)
    v = DatasetVersion(
        tenant_id="tenant_test",
        dataset_id=d.id,
        major=0,
        minor=0,
        patch=1,
        created_by="alice",
    )
    session.add(v)
    session.flush()
    s = Sample(
        tenant_id="tenant_test",
        version_id=v.id,
        blob_key="sha256/abc",
        relative_path="train/x.png",
        size_bytes=100,
        split=Split.TRAIN,
        blob_digest="abc",
    )
    session.add(s)
    session.flush()
    assert s.id
    assert s.split == Split.TRAIN
    assert s.label is None
    assert s.blob_key == "sha256/abc"


def test_import_job_defaults(session: Session):
    d = _make_dataset(session)
    v = DatasetVersion(
        tenant_id="tenant_test",
        dataset_id=d.id,
        major=0,
        minor=0,
        patch=1,
        created_by="alice",
    )
    session.add(v)
    session.flush()
    j = ImportJob(
        tenant_id="tenant_test",
        version_id=v.id,
        source_kind=ImportSourceKind.LOCAL,
    )
    session.add(j)
    session.flush()
    assert j.id
    assert j.status == ImportStatus.PENDING
    assert j.total_samples == 0
    assert j.processed_samples == 0
    assert j.error_message is None
    assert j.started_at is None
    assert j.completed_at is None


def test_split_enum_values():
    assert Split.TRAIN.value == "TRAIN"
    assert Split.VAL.value == "VAL"
    assert Split.TEST.value == "TEST"
