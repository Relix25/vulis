"""Task routes — CRUD + state-machine transition.

Transition RBAC:
    start      → data-scientist, admin
    submit     → data-scientist, admin
    approve    → reviewer, admin
    reject     → reviewer, admin
    deploy     → operator, admin
    retrain    → data-scientist, admin
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from vulis_core import NotFoundError

from vulis_project.audit import log_audit
from vulis_project.dependencies import CurrentUser, get_db, require_role
from vulis_project.models import Project, Task
from vulis_project.schemas import TaskCreate, TaskRead, TaskTransitionRequest
from vulis_project.state_machine import ALL_VERBS, apply_transition

router = APIRouter(tags=["tasks"])

# Per-verb role gates. Roles not in this map accept the verb (admin +
# any future roles get full access by default).
_VERB_ROLES: dict[str, tuple[str, ...]] = {
    "start": ("data-scientist",),
    "submit": ("data-scientist",),
    "approve": ("reviewer",),
    "reject": ("reviewer",),
    "deploy": ("operator",),
    "retrain": ("data-scientist",),
}


def _require_verb_role(verb: str, user: CurrentUser) -> None:
    """Raise 403 unless the user has a role allowed to invoke ``verb``.

    Admins are always allowed.
    """
    if "admin" in user.roles:
        return
    allowed = _VERB_ROLES.get(verb, ())
    if not (user.roles & set(allowed)):
        from vulis_core import ForbiddenError

        raise ForbiddenError(
            f"Role(s) {sorted(user.roles) or 'none'} cannot perform transition "
            f"{verb!r}; required one of {sorted(allowed)} or admin"
        )


def _get_active_project(session: Session, project_id: str, tenant_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None or project.tenant_id != tenant_id:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def _get_task_or_404(session: Session, task_id: str, tenant_id: str) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.tenant_id != tenant_id:
        raise NotFoundError(f"Task {task_id} not found")
    return task


# ─── Nested under /projects/{pid}/tasks ────────────────────────

nested = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])


@nested.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: str,
    body: TaskCreate,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
) -> Task:
    _get_active_project(session, project_id, user.tenant_id)
    task = Task(
        tenant_id=user.tenant_id,
        project_id=project_id,
        name=body.name,
        kind=body.kind,
    )
    session.add(task)
    session.flush()
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="task.create",
        target_type="task",
        target_id=task.id,
        diff={"project_id": project_id, "name": body.name, "kind": body.kind.value},
    )
    session.commit()
    session.refresh(task)
    return task


@nested.get("", response_model=list[TaskRead])
async def list_tasks(
    project_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[Task]:
    _get_active_project(session, project_id, user.tenant_id)
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .where(Task.tenant_id == user.tenant_id)
        .order_by(Task.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


# ─── Top-level /tasks/{tid}:transition ─────────────────────────

root = APIRouter(prefix="/tasks", tags=["tasks"])


@root.post("/{task_id}:transition", response_model=TaskRead)
async def transition_task(
    task_id: str,
    body: TaskTransitionRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist", "reviewer", "operator")),
) -> Task:
    task = _get_task_or_404(session, task_id, user.tenant_id)
    _require_verb_role(body.verb, user)
    new_state = apply_transition(task.state, body.verb)  # raises InvalidTransitionError → 409
    old_state = task.state
    task.state = new_state
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="task.transition",
        target_type="task",
        target_id=task.id,
        diff={"verb": body.verb, "from": old_state.value, "to": new_state.value},
    )
    session.commit()
    session.refresh(task)
    return task


# Collect both into the module-level router (with explicit order so the
# /tasks/{id}:transition path is registered before the wildcard fallback
# would shadow it — FastAPI matches in registration order).
router.include_router(nested)
router.include_router(root)


__all__ = ["ALL_VERBS", "router"]
