"""FastAPI dependencies for the registry service.

Exposes:
    * ``get_db``            — SQLAlchemy session bound to the request.
    * ``get_storage``       — a process-wide ``StorageBackend`` instance.
    * ``get_current_user``  — header-based auth stub (M1.5) / JWT later (M1.6).
    * ``require_role``      — RBAC gate, builds on ``get_current_user``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker
from vulis_core import ForbiddenError, UnauthorizedError
from vulis_storage import StorageBackend

# ─── Auth principal ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated principal for the current request."""

    tenant_id: str
    actor: str
    roles: frozenset[str]


# ─── DB session ────────────────────────────────────────────────


def get_db(request: Request) -> Session:
    """Yield a SQLAlchemy session for the duration of the request."""
    sessionmaker: sessionmaker[Session] = request.app.state.db_sessionmaker
    session = sessionmaker()
    try:
        yield session
    finally:
        session.close()


# ─── Storage backend ───────────────────────────────────────────


def get_storage(request: Request) -> StorageBackend:
    """Return the process-wide ``StorageBackend`` instance."""
    storage: StorageBackend = request.app.state.storage
    return storage


# ─── Auth (header stub) ────────────────────────────────────────


def _parse_roles_header(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(r.strip() for r in value.split(",") if r.strip())


def get_current_user(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    x_roles: str | None = Header(default=None, alias="X-Roles"),
) -> CurrentUser:
    """Return the current principal, or raise 401.

    In M1.5 we trust the headers verbatim — the gateway doesn't run
    yet. In M1.6 this dependency will validate a JWT and build the
    principal from the claims.
    """
    if not x_tenant_id or not x_actor:
        raise UnauthorizedError(
            "Missing X-Tenant-Id and/or X-Actor headers. "
            "Set them on every request (see services/registry/README.md)."
        )
    return CurrentUser(
        tenant_id=x_tenant_id,
        actor=x_actor,
        roles=_parse_roles_header(x_roles),
    )


def require_role(*allowed: str):
    """Build a FastAPI dependency that gates an endpoint on role membership."""
    allowed_set = frozenset(allowed)

    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not (user.roles & allowed_set):
            raise ForbiddenError(
                f"Required role(s) {sorted(allowed_set)}; user has {sorted(user.roles) or 'none'}"
            )
        return user

    return _check


def require_any_role(allowed: Iterable[str]):
    """Like :func:`require_role` but takes a runtime iterable."""
    return require_role(*allowed)


__all__ = [
    "CurrentUser",
    "get_current_user",
    "get_db",
    "get_storage",
    "require_any_role",
    "require_role",
]
