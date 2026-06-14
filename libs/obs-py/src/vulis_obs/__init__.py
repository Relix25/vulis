"""vulis-obs-py — observability helpers for Vulis services.

Wraps OpenTelemetry to provide:
- a single ``init_observability`` entry point,
- a catalog of predefined ``vulis.*`` metrics,
- a ``span`` context manager that auto-injects global attributes.

See the README for the full metric reference and ADR 0004 / ARCHITECTURE
section 8 for the observability design.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

# Re-export ``meter`` as an alias of ``span`` for the README examples
# that use ``with meter("name", ...)`` — kept for ergonomics.
from vulis_obs.metrics import (
    PREDEFINED,
    counter,
    histogram,
    up_down_counter,
)
from vulis_obs.setup import (
    global_attributes,
    init_observability,
    is_initialized,
    set_global_attribute,
)
from vulis_obs.tracing import current_span, set_span_attribute, span

# Convenience alias.
meter = span

__version__ = "0.1.0"

__all__ = [
    "PREDEFINED",
    "__version__",
    # metrics
    "counter",
    "current_span",
    "global_attributes",
    "histogram",
    # setup
    "init_observability",
    "is_initialized",
    "meter",
    "set_global_attribute",
    "set_span_attribute",
    # tracing
    "span",
    "up_down_counter",
]
