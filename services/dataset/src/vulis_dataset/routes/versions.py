"""DatasetVersion detail / manifest / publish / split routes."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import ConflictError, NotFoundError, ValidationError
from vulis_storage import StorageBackend

from vulis_dataset.audit import log_audit
from vulis_dataset.dependencies import (
    CurrentUser,
    get_db,
    get_storage,
    require_role,
)
from vulis_dataset.manifest import (
    build_manifest,
    manifest_digest,
    serialize_manifest,
    verify_manifest_blob,
)
from vulis_dataset.models import Dataset, DatasetVersion, Sample, Split
from vulis_dataset.schemas import (
    DatasetVersionRead,
    ManifestResponse,
    SplitRequest,
)

# Two routers: one nested under /datasets/{id}/versions/{vid}, one
# top-level. FastAPI matches in registration order, so the wildcard
# {vid}:action routes must be registered before any /{vid} catch-all.

nested = APIRouter(prefix="/datasets/{dataset_id}/versions", tags=["dataset-versions"])
root = APIRouter(prefix="/dataset-versions", tags=["dataset-versions"])


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


def _check_unpublished(version: DatasetVersion) -> None:
    if version.is_published:
        raise ConflictError(
            f"DatasetVersion {version.id} is already published (immutable)",
            details={"version_id": version.id, "is_published": True},
        )


# ─── GET /datasets/{id}/versions/{vid} ──────────────────────────


@nested.get("/{version_id}", response_model=DatasetVersionRead)
async def get_version(
    dataset_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> DatasetVersion:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    return _get_version(session, version_id, user.tenant_id)


# ─── GET /datasets/{id}/versions/{vid}/manifest ─────────────────


@nested.get(
    "/{version_id}/manifest",
    response_model=ManifestResponse,
    responses={409: {"description": "Version not published"}},
)
async def get_manifest(
    dataset_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    storage: StorageBackend = Depends(get_storage),
) -> ManifestResponse:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    if not version.is_published or not version.manifest_key or not version.manifest_digest:
        raise ConflictError(
            f"DatasetVersion {version.id} is not published yet",
            details={"version_id": version.id, "is_published": False},
        )
    blob = storage.get_bytes(version.manifest_key)
    # Verify integrity — fail loud if the stored blob drifted from the
    # recorded digest (storage corruption or tampering).
    verify_manifest_blob(blob, version.manifest_digest)
    import json

    data = json.loads(blob)
    return ManifestResponse(
        manifest_schema=data["schema"],
        manifest_version=data["version"],
        dataset_id=data["dataset_id"],
        task_kind=data["task_kind"],
        sample_count=data["sample_count"],
        size_bytes=data["size_bytes"],
        samples=data["samples"],
    )


# ─── POST /datasets/{id}/versions/{vid}:publish ─────────────────


@nested.post(
    "/{version_id}:publish",
    response_model=DatasetVersionRead,
    responses={
        409: {"description": "Already published, or zero samples"},
        422: {"description": "No samples to publish"},
    },
)
async def publish_version(
    dataset_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
    storage: StorageBackend = Depends(get_storage),
) -> DatasetVersion:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    _check_unpublished(version)

    # Collect samples (locked to this version).
    samples_rows = list(
        session.execute(
            select(Sample).where(Sample.version_id == version.id).order_by(Sample.id)
        ).scalars()
    )
    if not samples_rows:
        raise ValidationError(
            f"Cannot publish version {version.id}: no samples recorded",
            details={"version_id": version.id},
        )

    dataset = _get_active_dataset(session, dataset_id, user.tenant_id)
    manifest = build_manifest(
        version=f"{version.major}.{version.minor}.{version.patch}",
        dataset_id=version.dataset_id,
        task_kind=dataset.task_kind,
        samples=[
            {
                "key": s.blob_key,
                "path": s.relative_path,
                "label": s.label,
                "split": s.split.value,
                "size_bytes": s.size_bytes,
            }
            for s in samples_rows
        ],
    )
    blob = serialize_manifest(manifest)
    digest = manifest_digest(manifest)
    # Content-addressed put — the storage key will be "sha256/<digest>".
    key = storage.put_blob(blob)
    # Sanity: the put key should match our digest.
    if not key.endswith(digest):
        # Different algo or key encoding — fail loud.
        raise ConflictError(
            f"Storage key {key!r} does not match manifest digest {digest!r}",
            details={"key": key, "digest": digest},
        )

    version.is_published = True
    version.manifest_key = key
    version.manifest_digest = digest
    version.sample_count = manifest["sample_count"]
    version.size_bytes = manifest["size_bytes"]
    session.add(version)
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset_version.publish",
        target_type="dataset_version",
        target_id=version.id,
        diff={
            "version": f"{version.major}.{version.minor}.{version.patch}",
            "manifest_digest": digest,
            "sample_count": manifest["sample_count"],
            "size_bytes": manifest["size_bytes"],
        },
    )
    session.commit()
    session.refresh(version)
    return version


# ─── POST /datasets/{id}/versions/{vid}:split ──────────────────


@nested.post("/{version_id}:split", response_model=DatasetVersionRead)
async def split_version(
    dataset_id: str,
    version_id: str,
    body: SplitRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> DatasetVersion:
    _get_active_dataset(session, dataset_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    _check_unpublished(version)  # Splitting a published version → 409.

    samples_rows = list(
        session.execute(select(Sample).where(Sample.version_id == version.id)).scalars()
    )
    if not samples_rows:
        raise ValidationError(
            f"Cannot split version {version.id}: no samples recorded",
            details={"version_id": version.id},
        )

    if body.strategy == "manual":
        if not body.assignments:
            raise ValidationError("strategy=manual requires 'assignments' list")
        by_id = {s.id: s for s in samples_rows}
        for a in body.assignments:
            sid = a.get("sample_id")
            new_split = a.get("split")
            if sid not in by_id:
                raise ValidationError(
                    f"Sample {sid} not found in version {version.id}",
                    details={"sample_id": sid, "version_id": version.id},
                )
            try:
                split_enum = Split(new_split)
            except ValueError as e:
                raise ValidationError(
                    f"Invalid split {new_split!r}; expected one of {[s.value for s in Split]}",
                ) from e
            by_id[sid].split = split_enum
    elif body.strategy == "stratified":
        if not body.ratios:
            raise ValidationError("strategy=stratified requires 'ratios' dict")
        total = sum(body.ratios.values())
        if abs(total - 1.0) > 1e-6:
            raise ValidationError(
                f"stratified ratios must sum to 1.0 (got {total})",
                details={"ratios": body.ratios, "sum": total},
            )
        # Validate splits names.
        for s_name in body.ratios:
            try:
                Split(s_name)
            except ValueError as e:
                raise ValidationError(
                    f"Invalid split {s_name!r}; expected one of {[s.value for s in Split]}",
                ) from e

        # Group by stratify key (default: no stratification).
        stratify_field = body.stratify_by  # "label" or None
        groups: dict[Any, list[Sample]] = defaultdict(list)
        if stratify_field == "label":
            for s in samples_rows:
                groups[s.label or "<none>"].append(s)
        else:
            groups["<all>"] = list(samples_rows)

        rng = random.Random(body.seed)
        for grp in groups.values():
            rng.shuffle(grp)
            n = len(grp)
            # Walk ratios in stable order: TRAIN, VAL, TEST.
            cursor = 0
            for split_name in ("TRAIN", "VAL", "TEST"):
                if split_name not in body.ratios:
                    continue
                ratio = body.ratios[split_name]
                end = cursor + round(n * ratio)
                # Clip to n so floating-point rounding doesn't overflow.
                end = min(end, n)
                for s in grp[cursor:end]:
                    s.split = Split(split_name)
                cursor = end
            # Assign any remaining (due to rounding) to the last seen split.
            if cursor < n:
                last_split = Split(list(body.ratios.keys())[-1])
                for s in grp[cursor:]:
                    s.split = last_split
    else:  # pragma: no cover — guarded by Literal
        raise ValidationError(f"Unknown split strategy: {body.strategy!r}")

    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="dataset_version.split",
        target_type="dataset_version",
        target_id=version.id,
        diff={
            "strategy": body.strategy,
            "ratios": body.ratios,
            "stratify_by": body.stratify_by,
            "assignments_count": len(body.assignments) if body.assignments else None,
        },
    )
    session.commit()
    session.refresh(version)
    return version


# Collect the routers.
router = APIRouter()
router.include_router(nested)
router.include_router(root)


__all__ = ["router"]
