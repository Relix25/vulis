"""Vulis metric instruments.

Predefined OpenTelemetry counters and histograms under the ``vulis.*``
namespace. They are created lazily on first access and cached per process.

Why predefined names? So dashboards (Grafana) and alerting rules can rely on
a stable set of instrument names rather than ad-hoc strings scattered across
services.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from typing import Any

__all__ = [
    "PREDEFINED",
    "counter",
    "histogram",
    "up_down_counter",
]


# Predefined metric registry: name → (kind, unit, description)
PREDEFINED: dict[str, tuple[str, str, str]] = {
    # ─── datasets ─────────────────────────────────────────────
    "vulis.dataset.samples_imported": (
        "counter",
        "1",
        "Number of samples added to a dataset version",
    ),
    "vulis.dataset.import_seconds": (
        "histogram",
        "s",
        "Wall-clock duration of a dataset import",
    ),
    "vulis.dataset.size_bytes": ("histogram", "By", "Dataset version size in bytes"),
    # ─── models / registry ────────────────────────────────────
    "vulis.model.approval_transitions": (
        "counter",
        "1",
        "Number of model approval state transitions",
    ),
    "vulis.model.uploaded": (
        "counter",
        "1",
        "Number of model versions uploaded to the registry",
    ),
    # ─── serving / inference ──────────────────────────────────
    "vulis.serving.inferences": ("counter", "1", "Number of inferences performed"),
    "vulis.serving.inference_seconds": ("histogram", "s", "Inference latency"),
    "vulis.serving.batch_size": ("histogram", "1", "Inference batch size"),
    "vulis.serving.confidence": ("histogram", "1", "Per-prediction confidence"),
    # ─── fleet ────────────────────────────────────────────────
    "vulis.fleet.edge_heartbeat": ("counter", "1", "Edge heartbeats received"),
    "vulis.fleet.edge_online": ("up_down_counter", "1", "Currently online edges (gauge)"),
    "vulis.fleet.update_applied": ("counter", "1", "Number of edge updates applied"),
    # ─── storage ──────────────────────────────────────────────
    "vulis.storage.read_bytes": ("counter", "By", "Bytes read from a storage backend"),
    "vulis.storage.write_bytes": ("counter", "By", "Bytes written to a storage backend"),
    "vulis.storage.operations": (
        "counter",
        "1",
        "Storage operations (put/get/stat/list/delete)",
    ),
    "vulis.storage.operation_seconds": ("histogram", "s", "Storage operation latency"),
}


def _meter() -> Any:
    """Return the OTel meter, or a no-op fallback."""
    try:
        from opentelemetry import metrics
        return metrics.get_meter("vulis", schema_url="https://vulis.io/metrics/v1")
    except ImportError:
        return _NoopMeter()


def counter(name: str, *, unit: str = "1", description: str = "") -> Any:
    """Get or create a counter instrument.

    If ``name`` is one of the PREDEFINED metrics, unit/description are taken
    from the registry and the provided values ignored.
    """
    _kind, u, desc = PREDEFINED.get(name, ("counter", unit, description or name))
    m = _meter()
    return m.create_counter(name, unit=u, description=desc)


def histogram(name: str, *, unit: str = "1", description: str = "") -> Any:
    _kind, u, desc = PREDEFINED.get(name, ("histogram", unit, description or name))
    m = _meter()
    return m.create_histogram(name, unit=u, description=desc)


def up_down_counter(name: str, *, unit: str = "1", description: str = "") -> Any:
    _kind, u, desc = PREDEFINED.get(name, ("up_down_counter", unit, description or name))
    m = _meter()
    return m.create_up_down_counter(name, unit=u, description=desc)


# ─── No-op fallback when OTel is not configured ──────────────


class _NoopMeter:
    """Minimal meter that returns no-op instruments.

    Ensures services can call ``counter(...).add(...)`` even when the OTel
    SDK is absent (CLI tools, tests).
    """

    def create_counter(self, name: str, **kw: Any) -> _NoopInstrument:
        return _NoopInstrument()

    def create_histogram(self, name: str, **kw: Any) -> _NoopInstrument:
        return _NoopInstrument()

    def create_up_down_counter(self, name: str, **kw: Any) -> _NoopInstrument:
        return _NoopInstrument()


class _NoopInstrument:
    def add(self, amount: float, **kw: Any) -> None:
        pass

    def record(self, amount: float, **kw: Any) -> None:
        pass

    def inc(self, amount: float = 1.0, **kw: Any) -> None:
        pass
