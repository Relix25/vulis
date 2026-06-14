"""Line routes — sub-resource of Project."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import NotFoundError

from vulis_project.audit import log_audit
from vulis_project.dependencies import CurrentUser, get_db, require_role
from vulis_project.models import Line, Project
from vulis_project.schemas import LineCreate, LineRead

router = APIRouter(prefix="/projects/{project_id}/lines", tags=["lines"])


def _get_active_project(session: Session, project_id: str, tenant_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None or project.tenant_id != tenant_id:
        raise NotFoundError(f"Project {project_id} not found")
    return project


@router.post("", response_model=LineRead, status_code=status.HTTP_201_CREATED)
async def create_line(
    project_id: str,
    body: LineCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Line:
    _get_active_project(session, project_id, user.tenant_id)
    line = Line(
        tenant_id=user.tenant_id,
        project_id=project_id,
        name=body.name,
        edge_ids=body.edge_ids,
    )
    session.add(line)
    session.flush()
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="line.create",
        target_type="line",
        target_id=line.id,
        diff={"project_id": project_id, "name": body.name, "edge_ids": body.edge_ids},
    )
    session.commit()
    session.refresh(line)
    return line


@router.get("", response_model=list[LineRead])
async def list_lines(
    project_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[Line]:
    _get_active_project(session, project_id, user.tenant_id)
    stmt = (
        select(Line)
        .where(Line.project_id == project_id)
        .where(Line.tenant_id == user.tenant_id)
        .order_by(Line.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


__all__ = ["router"]
