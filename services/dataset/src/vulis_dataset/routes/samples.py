"""Sample routes — read + single-sample split update.

Most sample creation happens via the import worker (which writes Sample
rows in batches). This router supports lightweight operations:
list samples of a version (for the UI), and patch a single sample's
split (drag-and-drop in the UI).

Published versions are immutable — patches on a published version
return 409.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import ConflictError, NotFoundError

from vulis_dataset.audit import log_audit
from vulis_dataset.dependencies import (
    CurrentUser,
    get_db,
    require_role,
)
from vulis_dataset.models import Dataset, DatasetVersion, Sample
from vulis_dataset.schemas import SampleRead, SampleSplitUpdate

router = APIRouter(prefix="/datasets/{dataset_id}/versions/{version_id}/samples", tags=["samples"])


def _get_active_dataset(session: Session, dataset_id: str, tenant_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.deleted_at is not None or dataset.tenant_id != tenant_id:
        raise NotFoundError(f"Dataset {dataset_id} not found")
    return dataset


def _get_version(session: Session, version_id: str, tenant_id: str) -> DatasetVersion:
    version = session.get(DatasetVersion, version_id)
    if version is None or version.tenant_id != tenant_id:
        raise NotFoundError(f"DatasetVersion {version_id} not found")
    return version


@router.get("", response_model=list[SampleRead])
async def list_samples(
    dataset_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    split: str | None = Query(default=None, description="Filter by split (TRAIN/VAL/TEST)."),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Sample]:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    _get_version(session, version_id, user.tenant_id)
    stmt = (
        select(Sample)
        .where(Sample.version_id == version_id)
        .where(Sample.tenant_id == user.tenant_id)
        .order_by(Sample.id)
        .limit(limit)
        .offset(offset)
    )
    if split is not None:
        stmt = stmt.where(Sample.split == split)
    return list(session.execute(stmt).scalars())


@router.patch("/{sample_id}", response_model=SampleRead)
async def update_sample_split(
    dataset_id: str,
    version_id: str,
    sample_id: str,
    body: SampleSplitUpdate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Sample:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    if version.is_published:
        raise ConflictError(
            f"Cannot modify a sample on published version {version.id}",
            details={"version_id": version.id, "is_published": True},
        )
    sample = session.get(Sample, sample_id)
    if sample is None or sample.version_id != version_id or sample.tenant_id != user.tenant_id:
        raise NotFoundError(f"Sample {sample_id} not found in version {version_id}")
    old_split = sample.split
    if old_split != body.split:
        sample.split = body.split
        log_audit(
            session,
            tenant_id=user.tenant_id,
            actor=user.actor,
            action="sample.split.update",
            target_type="sample",
            target_id=sample.id,
            diff={"from": old_split.value, "to": body.split.value},
        )
    session.commit()
    session.refresh(sample)
    return sample


__all__ = ["router"]
