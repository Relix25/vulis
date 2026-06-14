"""Vulis exception hierarchy.

Every Vulis service and library should raise exceptions derived from
``VulisError``. This makes it trivial to distinguish Vulis errors from
unrelated ones (e.g. stdlib or third-party) in a single ``except`` clause.

Hierarchy::

    VulisError                       (base)
    ├── NotFoundError                (404-ish)
    ├── AlreadyExistsError           (409-ish)
    ├── ValidationError              (422-ish, input shape)
    ├── ConflictError                (409-ish, semantic conflict)
    ├── UnauthorizedError            (401)
    ├── ForbiddenError               (403)
    ├── StorageError                 (backend-agnostic storage failure)
    │   ├── ObjectNotFoundError
    │   └── ChecksumMismatchError
    ├── RegistryError                (model/dataset registry)
    └── ExternalServiceError         (talking to Mosquitto, Postgres, etc.)

Conventions
-----------

- Each exception carries a human-readable ``message`` and an optional
  ``details`` dict for structured context (logged + serialized to clients).
- Exception classes are **not** used for control flow inside libraries;
  prefer returning ``None`` / ``Result``-like values when appropriate.
- HTTP services map these to status codes via a central exception handler
  (implemented in each service's app layer).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class VulisError(Exception):
    """Base class for all Vulis errors.

    Parameters
    ----------
    message:
        Short human-readable description.
    details:
        Optional structured context. Should be JSON-serializable.
    """

    def __init__(
        self,
        message: str = "",
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}

    def __str__(self) -> str:
        return self.message or self.__class__.__name__

    def __repr__(self) -> str:
        if self.details:
            return f"{self.__class__.__name__}({self.message!r}, details={self.details!r})"
        return f"{self.__class__.__name__}({self.message!r})"


# ─── Generic semantic errors ─────────────────────────────────


class NotFoundError(VulisError):
    """Raised when a referenced entity does not exist."""


class AlreadyExistsError(VulisError):
    """Raised when attempting to create an entity that already exists."""


class ConflictError(VulisError):
    """Raised when an operation conflicts with the current state.

    Use this for semantic conflicts that are not simply "already exists"
    (e.g. promoting a model that is not in the expected state).
    """


class ValidationError(VulisError):
    """Raised when input fails structural validation.

    Prefer pydantic ``ValidationError`` for schema-driven validation; this
    class is for higher-level semantic validation in service code.
    """


class UnauthorizedError(VulisError):
    """Raised when authentication is missing or invalid."""


class ForbiddenError(VulisError):
    """Raised when the authenticated subject lacks permission."""


# ─── Storage-related errors ──────────────────────────────────


class StorageError(VulisError):
    """Base class for storage backend failures."""


class ObjectNotFoundError(StorageError, NotFoundError):
    """Raised by a storage backend when a key does not exist.

    Multiple inheritance so callers can catch it either as a generic
    ``NotFoundError`` (semantic) or as a ``StorageError`` (transport).
    """


class ChecksumMismatchError(StorageError):
    """Raised when a retrieved blob does not match its expected hash."""


# ─── Registry errors ─────────────────────────────────────────


class RegistryError(VulisError):
    """Base class for model/dataset registry failures."""


class InvalidTransitionError(RegistryError, ConflictError):
    """Raised when a state-machine transition is not allowed."""


# ─── External service errors ─────────────────────────────────


class ExternalServiceError(VulisError):
    """Raised when a call to an external service (Mosquitto, Postgres, ...)
    fails. Carry the upstream status/error in ``details``."""

    def __init__(
        self,
        message: str,
        *,
        service: str,
        upstream_error: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"service": service}
        if upstream_error is not None:
            merged["upstream_error"] = upstream_error
        if details:
            merged.update(details)
        super().__init__(message, details=merged)
        self.service = service
        self.upstream_error = upstream_error


__all__ = [
    "AlreadyExistsError",
    "ChecksumMismatchError",
    "ConflictError",
    # External
    "ExternalServiceError",
    "ForbiddenError",
    "InvalidTransitionError",
    # Generic
    "NotFoundError",
    "ObjectNotFoundError",
    # Registry
    "RegistryError",
    # Storage
    "StorageError",
    "UnauthorizedError",
    "ValidationError",
    # Base
    "VulisError",
]
