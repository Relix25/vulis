"""vulis-core-py — shared core for Vulis.

Re-exports the most common symbols so callers can do::

    from vulis_core import ProjectId, VulisError, get_logger, init_logging

See the module docstrings for details.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_core.config import VulisSettings, get_settings
from vulis_core.exceptions import (
    AlreadyExistsError,
    ChecksumMismatchError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
    ObjectNotFoundError,
    RegistryError,
    StorageError,
    UnauthorizedError,
    ValidationError,
    VulisError,
)
from vulis_core.logging import (
    bind_context,
    get_correlation_id,
    get_logger,
    init_logging,
    set_correlation_id,
)
from vulis_core.types import (
    CampaignId,
    DatasetId,
    DatasetVersionId,
    EdgeId,
    EntityId,
    LineId,
    ModelId,
    ModelVersionId,
    ParseError,
    ProjectId,
    SemVer,
    TaskId,
    TenantId,
)

__version__ = "0.1.0"

__all__ = [
    "AlreadyExistsError",
    "CampaignId",
    "ChecksumMismatchError",
    "ConflictError",
    "DatasetId",
    "DatasetVersionId",
    "EdgeId",
    # types
    "EntityId",
    "ExternalServiceError",
    "ForbiddenError",
    "InvalidTransitionError",
    "LineId",
    "ModelId",
    "ModelVersionId",
    "NotFoundError",
    "ObjectNotFoundError",
    "ParseError",
    "ProjectId",
    "RegistryError",
    "SemVer",
    "StorageError",
    "TaskId",
    "TenantId",
    "UnauthorizedError",
    "ValidationError",
    # exceptions
    "VulisError",
    # config
    "VulisSettings",
    "__version__",
    "bind_context",
    "get_correlation_id",
    "get_logger",
    "get_settings",
    # logging
    "init_logging",
    "set_correlation_id",
]
