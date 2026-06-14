"""FastAPI app factory + VulisError → HTTP exception handler.

The handler implements the exception → status mapping defined in
``docs/handoff/03-conventions.md`` § 2:

    NotFoundError / ObjectNotFoundError      → 404
    AlreadyExistsError                       → 409
    ConflictError / InvalidTransitionError   → 409
    ValidationError                          → 422
    UnauthorizedError                        → 401
    ForbiddenError                           → 403
    StorageError                             → 500
    ExternalServiceError                     → 502
    VulisError (catch-all)                   → 500

Every error response is JSON of the form::

    {
      "error": {
        "code": "NOT_FOUND",
        "message": "Project proj_abc not found",
        "details": {...},
        "correlation_id": "..."
      }
    }
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from vulis_core import (
    AlreadyExistsError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
    ObjectNotFoundError,
    StorageError,
    UnauthorizedError,
    ValidationError,
    VulisError,
    get_correlation_id,
    init_logging,
)
from vulis_obs import init_observability

from vulis_project.config import ProjectSettings, get_settings
from vulis_project.routes import api_router

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


# ─── Exception → status mapping ─────────────────────────────────


_STATUS_MAP: dict[type, int] = {
    NotFoundError: 404,
    ObjectNotFoundError: 404,
    AlreadyExistsError: 409,
    ConflictError: 409,
    InvalidTransitionError: 409,
    ValidationError: 422,
    UnauthorizedError: 401,
    ForbiddenError: 403,
    StorageError: 500,
    ExternalServiceError: 502,
}


def _camel_to_snake_upper(name: str) -> str:
    """Convert a CamelCase class name to a CONST_CASE code.

    e.g. ``NotFoundError`` -> ``NOT_FOUND``, ``InvalidTransitionError`` -> ``INVALID_TRANSITION``.
    """
    out: list[str] = []
    for i, ch in enumerate(name):
        if (
            i > 0
            and ch.isupper()
            and (name[i - 1].islower() or (i + 1 < len(name) and name[i + 1].islower()))
        ):
            out.append("_")
        out.append(ch)
    return "".join(out).upper()


def _vulis_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, VulisError)
    status = _STATUS_MAP.get(type(exc), 500)
    code = _camel_to_snake_upper(type(exc).__name__)
    if code.endswith("_ERROR"):
        code = code[: -len("_ERROR")]
    if not code:
        code = "ERROR"
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "details": getattr(exc, "details", None),
                "correlation_id": get_correlation_id(),
            }
        },
    )


# ─── Engine / session factory ───────────────────────────────────


def _build_engine(settings: ProjectSettings) -> Engine:
    dsn = settings.postgres_dsn
    if dsn is None:
        raise RuntimeError(
            "VULIS_POSTGRES_DSN must be set (or VULIS_PROJECT_POSTGRES_DSN as override)."
        )
    # SecretStr unwrap — SQLAlchemy wants a plain string.
    return create_engine(dsn.get_secret_value(), future=True, pool_pre_ping=True)


# ─── App factory ────────────────────────────────────────────────


def create_app(settings: ProjectSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_logging(service=settings.service_name, level=settings.log_level, fmt=settings.log_format)
    init_observability(
        service=settings.service_name,
        endpoint=settings.otel_endpoint,
        surface=settings.surface,
        environment=settings.environment,
    )

    app = FastAPI(
        title="Vulis Project API",
        version="0.1.0",
        description="M1.3 — Project / Line / Task / Campaign management with audit trail + RBAC.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # DB session factory — stashed on app.state so get_db can pick it up.
    engine = _build_engine(settings)
    app.state.db_engine = engine
    app.state.db_sessionmaker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Exception handler — VulisError → structured JSON.
    app.add_exception_handler(VulisError, _vulis_error_handler)

    # Routes
    app.include_router(api_router, prefix="/api/v1")

    return app


__all__ = ["create_app"]
