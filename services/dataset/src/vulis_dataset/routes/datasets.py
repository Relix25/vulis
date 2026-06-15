"""Dataset CRUD + nested DatasetVersion create/list routes."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from vulis_core import AlreadyExistsError, NotFoundError

from vulis_dataset.audit import log_audit
from vulis_dataset.dependencies import CurrentUser, get_db, require_role
from vulis_dataset.models import Dataset, DatasetVersion, ImportJob
from vulis_dataset.schemas import (
    DatasetCreate,
    DatasetRead,
    DatasetUpdate,
    DatasetVersionCreate,
    DatasetVersionRead,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ─── Helpers ────────────────────────────────────────────────────


def _get_active_dataset(session: Session, dataset_id: str, tenant_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.deleted_at is not None or dataset.tenant_id != tenant_id:
        # Hide cross-tenant existence (don't leak).
        raise NotFoundError(f"Dataset {dataset_id} not found")
    return dataset


def _check_project_exists(session: Session, project_id: str, tenant_id: str) -> None:
    """Raise 404 if the referenced Project doesn't exist in this tenant.

    Done as a raw ``SELECT 1`` so we don't import vulis_project — the
    Project table is part of the shared metadata.
    """
    from sqlalchemy import text

    row = session.execute(
        text("SELECT 1 FROM projects WHERE id = :pid AND tenant_id = :tid AND deleted_at IS NULL"),
        {"pid": project_id, "tid": tenant_id},
    ).first()
    if row is None:
        raise NotFoundError(f"Project {project_id} not found")


# ─── Datasets ───────────────────────────────────────────────────


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    body: DatasetCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Dataset:
    _check_project_exists(session, body.project_id, user.tenant_id)
    dataset = Dataset(
        tenant_id=user.tenant_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        task_kind=body.task_kind,
        metadata_=body.metadata,
    )
    session.add(dataset)
    try:
        session.flush()
    except IntegrityError as e:  # pragma: no cover — defensive
        raise AlreadyExistsError(
            f"Dataset {body.name!r} in project {body.project_id} already exists",
            details={"project_id": body.project_id, "name": body.name},
        ) from e
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset.create",
        target_type="dataset",
        target_id=dataset.id,
        diff={
            "project_id": body.project_id,
            "name": body.name,
            "task_kind": body.task_kind,
        },
    )
    session.commit()
    session.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetRead])
async def list_datasets(
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    project_id: str | None = Query(default=None, description="Filter by exact project id."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Dataset]:
    stmt = (
        select(Dataset)
        .where(Dataset.tenant_id == user.tenant_id)
        .where(Dataset.deleted_at.is_(None))
        .order_by(Dataset.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if project_id is not None:
        stmt = stmt.where(Dataset.project_id == project_id)
    return list(session.execute(stmt).scalars())


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> Dataset:
    return _get_active_dataset(session, dataset_id, user.tenant_id)


@router.patch("/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: str,
    body: DatasetUpdate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Dataset:
    dataset = _get_active_dataset(session, dataset_id, user.tenant_id)
    diff: dict = {}
    for field in ("name", "description", "metadata"):
        new = getattr(body, field)
        if new is None:
            continue
        old = getattr(dataset, "metadata_" if field == "metadata" else field)
        if old != new:
            diff[field] = {"from": old, "to": new}
            setattr(dataset, "metadata_" if field == "metadata" else field, new)
    if diff:
        log_audit(
            session,
            tenant_id=user.tenant_id,
            actor=user.actor,
            action="dataset.update",
            target_type="dataset",
            target_id=dataset.id,
            diff=diff,
        )
    session.commit()
    session.refresh(dataset)
    return dataset


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Response:
    from datetime import UTC, datetime

    dataset = _get_active_dataset(session, dataset_id, user.tenant_id)
    if dataset.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    dataset.deleted_at = datetime.now(UTC)
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset.delete",
        target_type="dataset",
        target_id=dataset.id,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── DatasetVersions (nested create / list) ─────────────────────


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    dataset_id: str,
    body: DatasetVersionCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> DatasetVersion:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    major, minor, patch = body.resolve_semver()
    # ``created_by`` defaults to the actor from the auth header; clients
    # can override it (e.g. admin creating a version on behalf of
    # someone else — useful for the M1.4 CLI relay).
    created_by = body.created_by or user.actor
    version = DatasetVersion(
        tenant_id=user.tenant_id,
        dataset_id=dataset_id,
        major=major,
        minor=minor,
        patch=patch,
        created_by=created_by,
        metadata_=body.metadata,
        is_published=False,
    )
    session.add(version)
    try:
        session.flush()
    except IntegrityError as e:
        # The semver unique constraint will trip on duplicate versions.
        raise AlreadyExistsError(
            f"Version {major}.{minor}.{patch} already exists for dataset {dataset_id}",
            details={"dataset_id": dataset_id, "version": f"{major}.{minor}.{patch}"},
        ) from e
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset_version.create",
        target_type="dataset_version",
        target_id=version.id,
        diff={
            "dataset_id": dataset_id,
            "version": f"{major}.{minor}.{patch}",
        },
    )
    session.commit()
    session.refresh(version)
    return version


@router.get(
    "/{dataset_id}/versions",
    response_model=list[DatasetVersionRead],
)
async def list_versions(
    dataset_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[DatasetVersion]:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    stmt = (
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .where(DatasetVersion.tenant_id == user.tenant_id)
        .order_by(DatasetVersion.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


# Suppress unused-import warning for ImportJob — referenced transitively
# via the imports router.
_ = ImportJob


__all__ = ["router"]
