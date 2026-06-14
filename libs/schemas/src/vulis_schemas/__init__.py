"""vulis-schemas — shared SQLAlchemy base + Alembic migrations for Vulis.

Re-exports the most common symbols.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_schemas.base import (
    Base,
    NamingConvention,
    SoftDelete,
    TenantScoped,
    Timestamped,
    UUIDPrimaryKey,
    VulisMetaData,
)

__version__ = "0.1.0"

__all__ = [
    "Base",
    "NamingConvention",
    "SoftDelete",
    "TenantScoped",
    "Timestamped",
    "UUIDPrimaryKey",
    "VulisMetaData",
    "__version__",
]
