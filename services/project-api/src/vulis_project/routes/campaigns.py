"""Campaign routes — sub-resource of Project."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import NotFoundError

from vulis_project.audit import log_audit
from vulis_project.dependencies import CurrentUser, get_db, require_role
from vulis_project.models import Campaign, Project
from vulis_project.schemas import CampaignCreate, CampaignRead

router = APIRouter(prefix="/projects/{project_id}/campaigns", tags=["campaigns"])


def _get_active_project(session: Session, project_id: str, tenant_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None or project.tenant_id != tenant_id:
        raise NotFoundError(f"Project {project_id} not found")
    return project


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    project_id: str,
    body: CampaignCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Campaign:
    _get_active_project(session, project_id, user.tenant_id)
    campaign = Campaign(
        tenant_id=user.tenant_id,
        project_id=project_id,
        name=body.name,
        kind=body.kind,
        description=body.description,
    )
    session.add(campaign)
    session.flush()
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="campaign.create",
        target_type="campaign",
        target_id=campaign.id,
        diff={
            "project_id": project_id,
            "name": body.name,
            "kind": body.kind.value,
        },
    )
    session.commit()
    session.refresh(campaign)
    return campaign


@router.get("", response_model=list[CampaignRead])
async def list_campaigns(
    project_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[Campaign]:
    _get_active_project(session, project_id, user.tenant_id)
    stmt = (
        select(Campaign)
        .where(Campaign.project_id == project_id)
        .where(Campaign.tenant_id == user.tenant_id)
        .order_by(Campaign.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


__all__ = ["router"]
