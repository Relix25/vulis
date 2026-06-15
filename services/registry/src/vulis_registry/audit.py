"""Audit trail helper for the registry service.

Writes a row to the shared ``audit_events`` table on every state-changing
operation. The table is append-only — a Postgres trigger rejects UPDATE
and DELETE (see ``libs/schemas/alembic/versions/0001_initial.py``).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session
from vulis_core import get_correlation_id
from vulis_schemas import Base

_AUDIT_TABLE = Base.metadata.tables.get("audit_events")
if _AUDIT_TABLE is None:  # pragma: no cover — defensive
    raise RuntimeError(
        "audit_events table not found in shared metadata. "
        "Did you forget to import vulis_schemas before calling log_audit()?"
    )


def log_audit(
    session: Session,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    diff: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    """Append a single audit row to ``audit_events``."""
    session.execute(
        _AUDIT_TABLE.insert().values(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            diff=json.dumps(diff, default=str) if diff else None,
            correlation_id=correlation_id or get_correlation_id(),
            occurred_at=datetime.now(UTC),
        )
    )


__all__ = ["log_audit"]
