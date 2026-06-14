"""Initialization of OpenTelemetry providers for Vulis services.

A Vulis service calls ``init_observability`` once at startup. The function
is idempotent and safe to call with no OTLP endpoint (in which case a
no-op provider is installed — useful for tests and CLI tools).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import logging

log = logging.getLogger("vulis.obs")

_INITIALIZED = False
_GLOBAL_ATTRS: dict[str, str] = {}

__all__ = [
    "global_attributes",
    "init_observability",
    "is_initialized",
    "set_global_attribute",
]


def init_observability(
    *,
    service: str,
    endpoint: str | None = None,
    surface: str = "server",
    environment: str = "dev",
    resource_attrs: dict[str, str] | None = None,
    force: bool = False,
) -> None:
    """Configure the global tracer + meter providers.

    Parameters
    ----------
    service:
        Component name, e.g. ``"dataset"`` or ``"serving"``.
    endpoint:
        OTLP/gRPC endpoint (e.g. ``"http://otel:4317"``). If ``None``, a
        no-op provider is installed (safe default for CLI/tests).
    surface:
        One of ``"workstation"``, ``"server"``, ``"edge"``.
    environment:
        ``dev`` / ``staging`` / ``prod``.
    resource_attrs:
        Extra resource attributes merged into the default set.
    force:
        Re-initialize even if already initialized.
    """
    global _INITIALIZED
    if _INITIALIZED and not force:
        return

    base_attrs: dict[str, str] = {
        "service.name": service,
        "service.namespace": "vulis",
        "vulis.surface": surface,
        "vulis.environment": environment,
    }
    if resource_attrs:
        base_attrs.update(resource_attrs)

    # Stash the base attributes for use as default span attributes.
    _GLOBAL_ATTRS.clear()
    _GLOBAL_ATTRS.update(base_attrs)

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning(
            "opentelemetry-sdk not installed; observability is a no-op. "
            "Install vulis-obs-py to enable it."
        )
        _INITIALIZED = True
        return

    resource = Resource.create(base_attrs)

    # ─── Tracer ───────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    if endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
    trace.set_tracer_provider(tracer_provider)

    # ─── Meter ────────────────────────────────────────────────
    if endpoint:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=True),
            export_interval_millis=15000,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    else:
        meter_provider = MeterProvider(resource=resource, metric_readers=[])
    metrics.set_meter_provider(meter_provider)

    _INITIALIZED = True
    log.debug("observability initialized", extra={"service": service, "endpoint": endpoint})


def is_initialized() -> bool:
    return _INITIALIZED


def set_global_attribute(key: str, value: str) -> None:
    """Set a default attribute applied to every subsequently created span/metric.

    Useful for binding the current request's ``vulis.project_id`` once and
    having every span in the request inherit it.
    """
    _GLOBAL_ATTRS[key] = value


def global_attributes() -> dict[str, str]:
    """Return a copy of the global default attributes."""
    return dict(_GLOBAL_ATTRS)
