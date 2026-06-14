"""Vulis typed identifiers and value objects.

Strong typing for IDs prevents mixing a ``ProjectId`` with a ``DatasetId``
at call sites that accept both. Each ID is a ``UUID`` under the hood, with
a short prefix tag (``proj_``, ``ds_``, ``mdl_``, ...) when serialized to
strings — useful in logs and URLs.

This module is dependency-free.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

__all__ = [
    "CampaignId",
    "DatasetId",
    "DatasetVersionId",
    "EdgeId",
    "EntityId",
    "LineId",
    "ModelId",
    "ModelVersionId",
    "ParseError",
    "ProjectId",
    "SemVer",
    "TaskId",
    "TenantId",
]


class ParseError(ValueError):
    """Raised when a string cannot be parsed into a typed ID or version."""


@dataclass(frozen=True, order=True)
class EntityId:
    """Base class for Vulis typed identifiers.

    Subclasses set the ``prefix`` class variable (e.g. ``"proj"``).
    The string form is ``"<prefix>_<uuid>"``.
    """

    prefix: ClassVar[str] = ""
    value: uuid.UUID

    # ── constructors ──────────────────────────────────────────
    @classmethod
    def new(cls) -> EntityId:
        """Generate a new random ID."""
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, s: str) -> EntityId:
        """Parse a ``prefix_uuid`` string into an ID.

        Raises ``ParseError`` if the prefix does not match this class.
        """
        if not cls.prefix:
            raise NotImplementedError(f"{cls.__name__} must define a prefix")
        expected = cls.prefix + "_"
        if not s.startswith(expected):
            raise ParseError(
                f"Expected id with prefix '{expected}', got {s!r}"
            )
        raw = s[len(expected) :]
        try:
            return cls(uuid.UUID(raw))
        except ValueError as e:  # invalid UUID
            raise ParseError(f"Invalid UUID in {s!r}: {e}") from e

    @classmethod
    def from_uuid(cls, u: uuid.UUID) -> EntityId:
        """Wrap an existing ``uuid.UUID`` value."""
        return cls(u)

    @classmethod
    def try_parse(cls, s: str) -> EntityId | None:
        """Like ``from_string`` but returns ``None`` on failure."""
        try:
            return cls.from_string(s)
        except ParseError:
            return None

    # ── dunders ───────────────────────────────────────────────
    def __str__(self) -> str:
        return f"{self.prefix}_{self.value.hex}" if self.prefix else self.value.hex

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self}')"


# ─── Concrete entity IDs ─────────────────────────────────────


class TenantId(EntityId):
    prefix = "tenant"


class ProjectId(EntityId):
    prefix = "proj"


class LineId(EntityId):
    prefix = "line"


class TaskId(EntityId):
    prefix = "task"


class DatasetId(EntityId):
    prefix = "ds"


class DatasetVersionId(EntityId):
    prefix = "dsv"


class ModelId(EntityId):
    prefix = "mdl"


class ModelVersionId(EntityId):
    prefix = "mdlv"


class CampaignId(EntityId):
    prefix = "camp"


class EdgeId(EntityId):
    """Edge node identifier. Often the host name; must be unique per tenant."""

    prefix = "edge"


# ─── Semantic version ────────────────────────────────────────


_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class SemVer:
    """A minimal SemVer 2.0.0 implementation.

    Ordering follows the SemVer 2.0.0 spec for the numeric core and the
    pre-release precedence rules. Build metadata is ignored for ordering.

    The default dataclass-generated ordering does NOT respect the SemVer
    precedence rules (a pre-release must be *lower* than the corresponding
    release, and build metadata must be ignored), so we disable the default
    ``order=True`` and implement ``__eq__`` / ``__lt__`` manually.
    """

    major: int
    minor: int
    patch: int
    pre_release: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(n < 0 for n in (self.major, self.minor, self.patch)):
            raise ValueError("Version numbers must be non-negative")

    # ─── comparison (SemVer precedence) ──────────────────────
    def _sort_key(self) -> tuple[int, int, int, int, tuple[Any, ...]]:
        """Return a key that orders versions per SemVer 2.0.0 §11.

        - Numeric core compared numerically.
        - A version WITHOUT a pre-release has higher precedence than one
          WITH a pre-release. We encode this with a leading ``1`` (no
          pre-release) vs ``0`` (pre-release) in the fourth slot.
        - Pre-release identifiers are compared element-wise: numeric ones as
          ints (lower than any string), string ones lexicographically; a
          shorter set is lower when all common identifiers are equal.
        - Build metadata is intentionally excluded.
        """
        # Pre-release precedence tuple. Numeric identifiers sort before
        # string ones, so we tag each as (0, int) or (1, str) so that
        # tuples of mixed types compare cleanly.
        pre_key: tuple[Any, ...] = tuple(
            (0, int(p)) if p.isdigit() else (1, p) for p in self.pre_release
        )
        # "has no pre-release" sorts AFTER "has pre-release".
        has_pre = 0 if self.pre_release else 1
        return (self.major, self.minor, self.patch, has_pre, pre_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() == other._sort_key()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() <= other._sort_key()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() > other._sort_key()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._sort_key() >= other._sort_key()

    def __hash__(self) -> int:
        # Hash on the precedence key (ignoring build metadata).
        return hash(self._sort_key())

    # ── constructors ──────────────────────────────────────────
    @classmethod
    def parse(cls, s: str) -> SemVer:
        m = _SEMVER_RE.match(s.strip())
        if not m:
            raise ParseError(f"Invalid SemVer: {s!r}")
        pre = tuple(m["pre"].split(".")) if m["pre"] else ()
        build = tuple(m["build"].split(".")) if m["build"] else ()
        return cls(int(m["major"]), int(m["minor"]), int(m["patch"]), pre, build)

    @classmethod
    def try_parse(cls, s: str) -> SemVer | None:
        try:
            return cls.parse(s)
        except ParseError:
            return None

    # ── dunders ───────────────────────────────────────────────
    def __str__(self) -> str:
        out = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            out += "-" + ".".join(self.pre_release)
        if self.build:
            out += "+" + ".".join(self.build)
        return out

    def __repr__(self) -> str:
        return f"SemVer('{self}')"

    # ── helpers ───────────────────────────────────────────────
    def bump_major(self) -> SemVer:
        return SemVer(self.major + 1, 0, 0)

    def bump_minor(self) -> SemVer:
        return SemVer(self.major, self.minor + 1, 0)

    def bump_patch(self) -> SemVer:
        return SemVer(self.major, self.minor, self.patch + 1)

    @property
    def is_pre_release(self) -> bool:
        return bool(self.pre_release)

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def _coerce_semver(v: SemVer | str | Mapping[str, Any]) -> SemVer:
    if isinstance(v, SemVer):
        return v
    if isinstance(v, str):
        return SemVer.parse(v)
    if isinstance(v, Mapping):
        return SemVer(
            int(v["major"]),
            int(v["minor"]),
            int(v["patch"]),
            tuple(v.get("pre_release") or ()),
            tuple(v.get("build") or ()),
        )
    raise TypeError(f"Cannot coerce {type(v).__name__} into SemVer")
