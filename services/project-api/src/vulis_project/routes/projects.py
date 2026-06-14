"""Project CRUD routes."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import NotFoundError

from vulis_project.audit import log_audit
from vulis_project.dependencies import CurrentUser, get_db, require_role
from vulis_project.models import Project
from vulis_project.schemas import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


# ─── Helpers ────────────────────────────────────────────────────


def _get_project_or_404(session: Session, project_id: str, tenant_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError(f"Project {project_id} not found")
    if project.tenant_id != tenant_id:
        # Hide cross-tenant existence (don't leak).
        raise NotFoundError(f"Project {project_id} not found")
    return project


# ─── Routes ─────────────────────────────────────────────────────


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Project:
    project = Project(
        tenant_id=user.tenant_id,
        name=body.name,
        description=body.description,
        phase=body.phase,
        tags=body.tags,
    )
    session.add(project)
    session.flush()  # populate project.id
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="project.create",
        target_type="project",
        target_id=project.id,
        diff={"name": body.name, "phase": body.phase.value},
    )
    session.commit()
    session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    project_id: str | None = Query(default=None, description="Filter by exact project id."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.tenant_id == user.tenant_id)
        .where(Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    return list(session.execute(stmt).scalars())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> Project:
    return _get_project_or_404(session, project_id, user.tenant_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Project:
    project = _get_project_or_404(session, project_id, user.tenant_id)
    diff: dict = {}
    for field in ("name", "description", "phase", "tags"):
        new = getattr(body, field)
        if new is None:
            continue
        old = getattr(project, field)
        if old != new:
            diff[field] = {"from": old.value if hasattr(old, "value") else old, "to": new}
            setattr(project, field, new)
    if diff:
        log_audit(
            session,
            tenant_id=user.tenant_id,
            actor=user.actor,
            action="project.update",
            target_type="project",
            target_id=project.id,
            diff=diff,
        )
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Response:
    project = _get_project_or_404(session, project_id, user.tenant_id)
    if project.deleted_at is not None:
        # Idempotent delete — already gone.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    from datetime import UTC, datetime

    project.deleted_at = datetime.now(UTC)
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="project.delete",
        target_type="project",
        target_id=project.id,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
