"""Import job routes.

The flow:

1. Client ``POST /api/v1/datasets/{id}/versions/{vid}/import`` with an
   ``ImportRequest`` body (source kind + descriptor).
2. Service creates an ``ImportJob`` row in PENDING and returns 202 +
   ``job_id``.
3. Service schedules an ``asyncio.create_task`` that walks the source
   and writes samples (see ``vulis_dataset.importers``).
4. Client polls ``GET /api/v1/import-jobs/{job_id}`` until
   ``status=DONE`` (or ``FAILED``).

The schedule happens in the same request as the create so the
``ImportJob.tenant_id`` is set under the request's session. The
asyncio task then uses its own session to do the actual work — see
``importers.schedule_import_job``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from vulis_core import NotFoundError, ValidationError

from vulis_dataset.audit import log_audit
from vulis_dataset.dependencies import (
    CurrentUser,
    get_db,
    require_role,
)
from vulis_dataset.importers import schedule_import_job
from vulis_dataset.models import (
    Dataset,
    DatasetVersion,
    ImportJob,
    ImportSourceKind,
    ImportStatus,
)
from vulis_dataset.schemas import ImportJobCreated, ImportJobRead, ImportRequest

# Nested under datasets/{id}/versions/{vid}/import
nested = APIRouter(prefix="/datasets/{dataset_id}/versions/{version_id}/import", tags=["imports"])
# Top-level /import-jobs/{id} for polling
root = APIRouter(prefix="/import-jobs", tags=["imports"])


# ─── Helpers ────────────────────────────────────────────────────


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


def _get_job(session: Session, job_id: str, tenant_id: str) -> ImportJob:
    job = session.get(ImportJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        raise NotFoundError(f"ImportJob {job_id} not found")
    return job


# ─── POST /datasets/{id}/versions/{vid}/import ─────────────────


@nested.post(
    "",
    response_model=ImportJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_import(
    dataset_id: str,
    version_id: str,
    body: ImportRequest,
    request: Request,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> ImportJobCreated:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    if version.is_published:
        raise ValidationError(
            f"Cannot import into a published version {version.id}",
            details={"version_id": version.id, "is_published": True},
        )

    # Source-specific sanity checks.
    if body.source_kind == "LOCAL" and "path" not in body.source_descriptor:
        raise ValidationError(
            "LOCAL import requires source_descriptor.path",
            details={"source_kind": "LOCAL"},
        )
    elif body.source_kind == "ZIP" and "blob_key" not in body.source_descriptor:
        raise ValidationError(
            "ZIP import requires source_descriptor.blob_key "
            "(the storage key of a previously-uploaded archive)",
            details={"source_kind": "ZIP"},
        )

    job = ImportJob(
        tenant_id=user.tenant_id,
        version_id=version.id,
        source_kind=ImportSourceKind(body.source_kind),
        source_descriptor={**body.source_descriptor, "actor": user.actor},
        status=ImportStatus.PENDING,
    )
    session.add(job)
    session.flush()  # populate job.id
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset.import.start",
        target_type="dataset_version",
        target_id=version.id,
        diff={
            "job_id": job.id,
            "source_kind": body.source_kind,
            "source_descriptor": {k: v for k, v in body.source_descriptor.items() if k != "actor"},
        },
    )
    session.commit()

    # Schedule the worker. The task uses the app's session factory and
    # storage backend (both stashed on app.state at startup).
    schedule_import_job(
        job_id=job.id,
        session_factory=request.app.state.db_sessionmaker,
        storage=request.app.state.storage,
    )

    return ImportJobCreated(job_id=job.id)


# ─── GET /import-jobs/{job_id} ──────────────────────────────────


@root.get("/{job_id}", response_model=ImportJobRead)
async def get_import_job(
    job_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> ImportJob:
    return _get_job(session, job_id, user.tenant_id)


# Collect.
router = APIRouter()
router.include_router(nested)
router.include_router(root)


__all__ = ["router"]
