"""Model CRUD routes (no version management — see routes/versions.py)."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from vulis_core import AlreadyExistsError, NotFoundError

from vulis_registry.audit import log_audit
from vulis_registry.dependencies import CurrentUser, get_db, require_role
from vulis_registry.models import Model
from vulis_registry.schemas import ModelCreate, ModelRead, ModelUpdate

router = APIRouter(prefix="/models", tags=["models"])


# ─── Helpers ────────────────────────────────────────────────────


def _get_active_model(session: Session, model_id: str, tenant_id: str) -> Model:
    model = session.get(Model, model_id)
    if model is None or model.deleted_at is not None or model.tenant_id != tenant_id:
        raise NotFoundError(f"Model {model_id} not found")
    return model


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


# ─── Routes ─────────────────────────────────────────────────────


@router.post("", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Model:
    _check_project_exists(session, body.project_id, user.tenant_id)
    model = Model(
        tenant_id=user.tenant_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        task_kind=body.task_kind,
        metadata_=body.metadata,
    )
    session.add(model)
    try:
        session.flush()
    except IntegrityError as e:  # pragma: no cover — defensive
        raise AlreadyExistsError(
            f"Model {body.name!r} in project {body.project_id} already exists",
            details={"project_id": body.project_id, "name": body.name},
        ) from e
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="model.create",
        target_type="model",
        target_id=model.id,
        diff={
            "project_id": body.project_id,
            "name": body.name,
            "task_kind": body.task_kind,
        },
    )
    session.commit()
    session.refresh(model)
    return model


@router.get("", response_model=list[ModelRead])
async def list_models(
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    project_id: str | None = Query(default=None, description="Filter by exact project id."),
    task_kind: str | None = Query(default=None, description="Filter by task kind."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Model]:
    stmt = (
        select(Model)
        .where(Model.tenant_id == user.tenant_id)
        .where(Model.deleted_at.is_(None))
        .order_by(Model.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if project_id is not None:
        stmt = stmt.where(Model.project_id == project_id)
    if task_kind is not None:
        stmt = stmt.where(Model.task_kind == task_kind)
    return list(session.execute(stmt).scalars())


@router.get("/{model_id}", response_model=ModelRead)
async def get_model(
    model_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> Model:
    return _get_active_model(session, model_id, user.tenant_id)


@router.patch("/{model_id}", response_model=ModelRead)
async def update_model(
    model_id: str,
    body: ModelUpdate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Model:
    model = _get_active_model(session, model_id, user.tenant_id)
    diff: dict = {}
    for field in ("name", "description", "metadata"):
        new = getattr(body, field)
        if new is None:
            continue
        old = getattr(model, "metadata_" if field == "metadata" else field)
        if old != new:
            diff[field] = {"from": old, "to": new}
            setattr(model, "metadata_" if field == "metadata" else field, new)
    if diff:
        log_audit(
            session,
            tenant_id=user.tenant_id,
            actor=user.actor,
            action="model.update",
            target_type="model",
            target_id=model.id,
            diff=diff,
        )
    session.commit()
    session.refresh(model)
    return model


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Response:
    from datetime import UTC, datetime

    model = _get_active_model(session, model_id, user.tenant_id)
    if model.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    model.deleted_at = datetime.now(UTC)
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="model.delete",
        target_type="model",
        target_id=model.id,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
