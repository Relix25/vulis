"""Tests for the registry ORM models."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vulis_registry.models import (
    Model,
    ModelStatus,
    ModelVersion,
    OnnxTensorSpec,
)


def _make_model(session: Session, project_id: str = "project_test") -> Model:
    m = Model(
        tenant_id="tenant_test",
        project_id=project_id,
        name="alpha",
        task_kind="DETECTION",
    )
    session.add(m)
    session.flush()
    return m


def test_model_defaults(session: Session):
    m = _make_model(session)
    assert m.id
    assert m.metadata_ == {}
    assert m.deleted_at is None
    assert m.created_at is not None


def test_model_soft_delete(session: Session):
    m = _make_model(session)
    from datetime import UTC, datetime

    m.deleted_at = datetime.now(UTC)
    session.flush()
    assert m.deleted_at is not None


def test_model_version_defaults(session: Session):
    m = _make_model(session)
    v = ModelVersion(
        tenant_id="tenant_test",
        model_id=m.id,
        major=1,
        minor=0,
        patch=0,
        artifact_key="sha256/abc",
        artifact_digest="abc",
        artifact_size_bytes=1024,
        onnx_opset=17,
        created_by="alice",
    )
    session.add(v)
    session.flush()
    assert v.id
    assert v.status == ModelStatus.DRAFT
    assert v.metadata_ == {}
    assert v.trained_on_dataset_version_id is None
    assert v.model_card is None


def test_model_version_semver_unique(session: Session):
    m = _make_model(session)
    a = ModelVersion(
        tenant_id="tenant_test",
        model_id=m.id,
        major=1,
        minor=2,
        patch=3,
        artifact_key="sha256/a",
        artifact_digest="a",
        onnx_opset=17,
        created_by="alice",
    )
    b = ModelVersion(
        tenant_id="tenant_test",
        model_id=m.id,
        major=1,
        minor=2,
        patch=3,
        artifact_key="sha256/b",
        artifact_digest="b",
        onnx_opset=17,
        created_by="bob",
    )
    session.add_all([a, b])
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_onnx_tensor_spec_defaults(session: Session):
    m = _make_model(session)
    v = ModelVersion(
        tenant_id="tenant_test",
        model_id=m.id,
        major=0,
        minor=0,
        patch=1,
        artifact_key="sha256/x",
        artifact_digest="x",
        onnx_opset=17,
        created_by="alice",
    )
    session.add(v)
    session.flush()
    s = OnnxTensorSpec(
        version_id=v.id,
        direction="input",
        name="input_0",
        dtype="FLOAT",
        shape=[-1, 3, 224, 224],
    )
    session.add(s)
    session.flush()
    assert s.id
    assert s.shape == [-1, 3, 224, 224]


def test_model_status_enum_values():
    assert ModelStatus.DRAFT.value == "DRAFT"
    assert ModelStatus.INTERNAL_REVIEW.value == "INTERNAL_REVIEW"
    assert ModelStatus.STAGING.value == "STAGING"
    assert ModelStatus.APPROVED.value == "APPROVED"
    assert ModelStatus.DEPLOYED.value == "DEPLOYED"
    assert ModelStatus.REJECTED.value == "REJECTED"
    assert ModelStatus.ARCHIVED.value == "ARCHIVED"
