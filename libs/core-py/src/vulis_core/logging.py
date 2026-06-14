"""Structured logging for Vulis.

Thin wrapper around ``structlog`` that:

- picks JSON output in production / staging and pretty console output in dev,
- stamps every log entry with the service name and a correlation id,
- exposes a thread-local "context" for adding business fields
  (``project_id``, ``line_id``, ``model_version``, ...) without threading
  them through every function signature,
- falls back gracefully if structlog is not configured (e.g. in a one-off
  script) so ``get_logger`` always returns a usable logger.

Usage
-----
::

    from vulis_core.logging import init_logging, get_logger, bind_context

    init_logging(service="dataset", level="INFO")
    log = get_logger(__name__)

    with bind_context(project_id="proj_abc", line_id="line_3"):
        log.info("dataset.imported", dataset_id="ds_xyz", samples=1234)
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

import structlog

__all__ = [
    "bind_context",
    "get_correlation_id",
    "get_logger",
    "init_logging",
    "set_correlation_id",
]

# ContextVar so async-safe correlation/context propagation works.
# We use ``None`` as the default and lazily initialize on first access,
# because mutable defaults on ContextVar are flagged by ruff B039.
_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("vulis_log_context", default=None)
_CORRELATION_ID: ContextVar[str | None] = ContextVar("vulis_correlation_id", default=None)

_INITIALIZED = False


def _get_context() -> dict[str, Any]:
    """Return the current context dict, initializing it lazily."""
    ctx = _CONTEXT.get()
    if ctx is None:
        ctx = {}
        _CONTEXT.set(ctx)
    return ctx


def _compute_processors(*, dev: bool) -> list[Any]:
    """Build the structlog processor chain."""
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_vulis_context,
        _inject_correlation_id,
    ]
    if dev:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.extend(
            [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ]
        )
    return processors


def _inject_vulis_context(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Merge the thread-local Vulis context into the event dict."""
    ctx = _get_context()
    for k, v in ctx.items():
        event_dict.setdefault(k, v)
    return event_dict


def _inject_correlation_id(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    cid = _CORRELATION_ID.get()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def init_logging(
    *,
    service: str = "vulis",
    level: str | int = "INFO",
    fmt: Literal["json", "console"] | None = None,
    force: bool = False,
) -> None:
    """Configure structlog and the stdlib logging bridge.

    Calling this more than once is a no-op unless ``force=True``.

    Parameters
    ----------
    service:
        Service/component name stamped on every log entry.
    level:
        Log level (string or int).
    fmt:
        ``"json"`` (default outside dev) or ``"console"`` (pretty, colored).
        If ``None``, defaults to ``console`` when ``sys.stderr.isatty()``,
        else ``json``.
    force:
        Re-initialize even if already initialized.
    """
    global _INITIALIZED
    if _INITIALIZED and not force:
        return

    level_no = (
        logging.getLevelName(level.upper()) if isinstance(level, str) else int(level)
    )

    if fmt is None:
        fmt = "console" if (sys.stderr.isatty() and "pytest" not in sys.modules) else "json"
    dev = fmt == "console"

    # Configure stdlib logging so non-structlog loggers (uvicorn, sqlalchemy)
    # also flow through the same formatter.
    logging.basicConfig(
        level=level_no,
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=_compute_processors(dev=dev),
        wrapper_class=structlog.make_filtering_bound_logger(level_no),
        # Defer file resolution: PrintLoggerFactory() resolves sys.stdout
        # lazily on first use, which is what we want — especially under
        # pytest where sys.stdout is replaced after import time.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Stamp every entry with the service name.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service)

    # If no correlation id yet, generate one for this process.
    if _CORRELATION_ID.get() is None:
        _CORRELATION_ID.set(_new_correlation_id())

    _INITIALIZED = True


def get_logger(
    name: str | None = None, **initial_values: Any
) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    If ``init_logging`` has not been called, a sensible default config is
    applied lazily (JSON to stdout) so importing a Vulis library and
    logging right away still works.
    """
    if not _INITIALIZED:
        # Lazy minimal init — JSON, INFO, no service tag.
        init_logging(service="vulis", level="INFO", fmt="json")
    logger = structlog.get_logger(name or "vulis")
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger


# ─── Context binding (business fields) ───────────────────────


@contextmanager
def bind_context(**values: Any) -> Iterator[None]:
    """Bind business fields (``project_id``, ``line_id``, ...) to logs
    emitted within the ``with`` block.

    Async-safe (uses ``ContextVar``). Safe to nest; nested scopes see their
    parent's values and override them locally.
    """
    current = dict(_get_context())
    current.update(values)
    token = _CONTEXT.set(current)
    try:
        yield
    finally:
        _CONTEXT.reset(token)


# ─── Correlation id ──────────────────────────────────────────


def _new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    """Return the current correlation id, generating one if absent."""
    cid = _CORRELATION_ID.get()
    if cid is None:
        cid = _new_correlation_id()
        _CORRELATION_ID.set(cid)
    return cid


def set_correlation_id(cid: str | None) -> None:
    """Override the correlation id (e.g. from an incoming request header).

    Pass ``None`` to clear it; the next read will generate a fresh one.
    """
    _CORRELATION_ID.set(cid)
