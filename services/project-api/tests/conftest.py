"""Test fixtures for the project-api.

Tests run against an in-memory SQLite database — fast and isolated. We
patch the ``app.state.db_sessionmaker`` so the real Postgres DSN is
never read. Alembic is bypassed; tables are created via
``Base.metadata.create_all`` which uses the same SQLAlchemy metadata
that the migrations apply.

Auth in tests: header-based stub. Provide ``auth_headers`` and pass it
to the ``TestClient`` as ``headers=...``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Ensure the env is sane BEFORE any imports that might read it.
# VULIS_ENVIRONMENT is a Literal[dev|staging|prod] so we use "dev" and
# set a sentinel env to flag the test runtime if needed.
os.environ.setdefault("VULIS_ENVIRONMENT", "dev")
os.environ.setdefault("VULIS_SURFACE", "server")
os.environ.setdefault("VULIS_TEST", "1")
# Tests never hit Postgres, but the app factory reads VULIS_POSTGRES_DSN
# at startup to build its (unused) engine. Provide a dummy value so the
# factory doesn't crash; the real sessionmaker is replaced right after.
os.environ.setdefault("VULIS_POSTGRES_DSN", "sqlite:///:memory:")

# Make sure the JSONB column type can be created on SQLite. We swap the
# JSONB type for JSON (a generic text-backed type) when running tests.
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.types import JSON as _GENERIC_JSON
from vulis_schemas import Base

# Import all the models so their tables register on Base.metadata.
from vulis_project import models  # noqa: F401
from vulis_project.app import create_app


@event.listens_for(Base.metadata, "before_create")
def _swap_jsonb_for_json(target, connection, **kw):  # pragma: no cover
    """Replace Postgres-only ``JSONB`` columns with portable ``JSON`` for SQLite tests.

    This mutates the table definitions in-place *before* SQLAlchemy emits
    the CREATE TABLE. It only runs when the dialect is SQLite.
    """
    if connection.dialect.name != "sqlite":
        return
    for table in target.tables.values():
        for col in table.columns:
            if isinstance(col.type, _PG_JSONB):
                col.type = _GENERIC_JSON()


@pytest.fixture
def engine():
    # In-memory SQLite needs StaticPool + a shared connection string,
    # otherwise each new connection sees a fresh empty database and the
    # tables created via create_all() are invisible to the sessionmaker
    # we hand to the app.
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    """Direct DB session for tests that don't go through HTTP."""
    Session_ = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session_()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def app(session_factory, monkeypatch):
    monkeypatch.setenv("VULIS_PROJECT_USE_HEADER_AUTH", "true")
    from vulis_project import config as _config

    _config._reset_settings_cache()

    # The app reads POSTGRES_DSN at startup to build its engine — for
    # tests we replace the session factory on app.state *after* the
    # app is created, so the real engine is built but never used.
    a = create_app()
    a.state.db_sessionmaker = session_factory
    yield a


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ─── Auth helpers ───────────────────────────────────────────────


def make_headers(
    roles: list[str] | None = None, tenant: str | None = None, actor: str | None = None
):
    """Build a header dict for the auth stub. Tenant + actor get random hex if not set."""
    return {
        "X-Tenant-Id": tenant or f"tenant_{uuid.uuid4().hex[:12]}",
        "X-Actor": actor or f"user_{uuid.uuid4().hex[:8]}",
        "X-Roles": ",".join(roles or []),
    }


@pytest.fixture
def admin_headers():
    return make_headers(roles=["admin"])


@pytest.fixture
def data_scientist_headers():
    return make_headers(roles=["data-scientist"])


@pytest.fixture
def annotator_headers():
    return make_headers(roles=["annotator"])


@pytest.fixture
def reviewer_headers():
    return make_headers(roles=["reviewer"])


@pytest.fixture
def operator_headers():
    return make_headers(roles=["operator"])
