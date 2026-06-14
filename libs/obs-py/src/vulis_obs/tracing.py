"""Tracing helpers: span creation + Vulis attribute binding.

Usage::

    from vulis_obs import span, meter  # meter here = "context manager span"

    with span("dataset.import", dataset_id=str(did)):
        ...

Span attributes are automatically merged with the global defaults set via
``set_global_attribute`` (e.g. ``vulis.project_id`` bound for the duration
of a request).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from vulis_obs.setup import global_attributes

__all__ = ["current_span", "set_span_attribute", "span"]


def _tracer() -> Any:
    try:
        from opentelemetry import trace
        return trace.get_tracer("vulis", schema_url="https://vulis.io/traces/v1")
    except ImportError:
        return _NoopTracer()


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """Open a tracing span named ``name``.

    Extra attributes are merged with the global defaults. Safe to use when
    OTel is not configured (no-op).
    """
    merged = global_attributes()
    merged.update(attrs)
    tracer = _tracer()
    with tracer.start_as_current_span(name, attributes=merged) as s:
        yield s


def current_span() -> Any:
    """Return the currently active span, or a no-op span if none."""
    try:
        from opentelemetry import trace
        s = trace.get_current_span()
        return s
    except ImportError:
        return _NoopSpan()


def set_span_attribute(key: str, value: Any) -> None:
    """Set an attribute on the current span (no-op if no active span)."""
    import contextlib

    s = current_span()
    # No-op spans or non-recordable spans just swallow the attribute.
    with contextlib.suppress(Exception):
        s.set_attribute(key, value)


# ─── No-op fallbacks ─────────────────────────────────────────


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None: pass
    def set_attributes(self, attrs: dict[str, Any]) -> None: pass
    def add_event(self, name: str, **kw: Any) -> None: pass
    def record_exception(self, exc: BaseException) -> None: pass
    def set_status(self, *args: Any, **kw: Any) -> None: pass
    def end(self) -> None: pass


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kw: Any) -> Iterator[_NoopSpan]:
        yield _NoopSpan()

    def start_span(self, name: str, **kw: Any) -> _NoopSpan:
        return _NoopSpan()
