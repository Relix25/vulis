"""Test fixtures for the dataset service.

Tests run against an in-memory SQLite database — fast and isolated. We
patch the ``app.state.db_sessionmaker`` and ``app.state.storage`` so
the real Postgres DSN and SMB share are never read. Alembic is bypassed;
tables are created via ``Base.metadata.create_all`` which uses the same
SQLAlchemy metadata that the migrations apply.

Auth in tests: header-based stub. Provide ``auth_headers`` and pass it
to the ``TestClient`` as ``headers=...``.

Important: we import the project-api models so the ``projects`` table
exists in the test DB (datasets FK to it). This is the only test-time
cross-service import — in production the migration handles it.
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
from sqlalchemy.pool import StaticPool
from vulis_schemas import Base
from vulis_storage import LocalFSBackend

# Ensure the env is sane BEFORE any imports that might read it.
os.environ.setdefault("VULIS_ENVIRONMENT", "dev")
os.environ.setdefault("VULIS_SURFACE", "server")
os.environ.setdefault("VULIS_TEST", "1")
os.environ.setdefault("VULIS_POSTGRES_DSN", "sqlite:///:memory:")
# Force the local-fs storage backend with a temp root.
os.environ.setdefault("VULIS_STORAGE_BACKEND", "local-fs")
os.environ.setdefault(
    "VULIS_STORAGE_LOCAL_ROOT", "/tmp/vulis-test-storage"
)  # overridden by tmp_path

# Make sure the JSONB column type can be created on SQLite. We swap the
# JSONB type for JSON (a generic text-backed type) when running tests.
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
from sqlalchemy.types import JSON as _GENERIC_JSON

# Import all the models so their tables register on Base.metadata.
# We import project-api models first so the projects table exists
# before dataset models declare their FKs.
from vulis_project import models as _project_models  # noqa: F401

from vulis_dataset import models  # noqa: F401
from vulis_dataset.app import create_app


@event.listens_for(Base.metadata, "before_create")
def _swap_jsonb_for_json(target, connection, **kw):  # pragma: no cover
    """Replace Postgres-only ``JSONB`` columns with portable ``JSON`` for SQLite tests."""
    if connection.dialect.name != "sqlite":
        return
    for table in target.tables.values():
        for col in table.columns:
            if isinstance(col.type, _PG_JSONB):
                col.type = _GENERIC_JSON()


@pytest.fixture
def engine():
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
def session_factory(engine) -> sessionmaker:
    """A session factory bound to the test engine.

    The factory also seeds a minimal ``Project`` row so the dataset
    route helper ``_check_project_exists`` finds it. Done via the
    ORM (not raw text INSERT) so the Python-side ``created_at``
    default fires.
    """
    from vulis_project.models import Phase, Project

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        s.add(
            Project(
                id="project_test",
                tenant_id="tenant_test",
                name="Test Project",
                phase=Phase.POC,
            )
        )
        s.commit()
    return factory


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    """Direct DB session for tests that don't go through HTTP."""
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def storage_root(tmp_path) -> str:
    """A unique temp directory for the storage backend."""
    p = tmp_path / "storage"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


@pytest.fixture
def app(session_factory, storage_root, monkeypatch):
    monkeypatch.setenv("VULIS_USE_HEADER_AUTH", "true")
    monkeypatch.setenv("VULIS_STORAGE_BACKEND", "local-fs")
    monkeypatch.setenv("VULIS_STORAGE_LOCAL_ROOT", storage_root)
    from vulis_dataset import config as _config

    _config._reset_settings_cache()

    a = create_app()
    # Replace both the session factory and the storage with test versions.
    a.state.db_sessionmaker = session_factory
    a.state.storage = LocalFSBackend(storage_root)
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
    return make_headers(roles=["admin"], tenant="tenant_test", actor="admin_user")


@pytest.fixture
def data_scientist_headers():
    return make_headers(roles=["data-scientist"], tenant="tenant_test", actor="ds_user")


@pytest.fixture
def annotator_headers():
    return make_headers(roles=["annotator"], tenant="tenant_test", actor="ann_user")


@pytest.fixture
def reviewer_headers():
    return make_headers(roles=["reviewer"], tenant="tenant_test", actor="rev_user")


@pytest.fixture
def operator_headers():
    return make_headers(roles=["operator"], tenant="tenant_test", actor="op_user")
