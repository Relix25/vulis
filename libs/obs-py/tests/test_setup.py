# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

import pytest

from vulis_obs import (
    PREDEFINED,
    counter,
    global_attributes,
    histogram,
    init_observability,
    is_initialized,
    set_global_attribute,
    span,
    up_down_counter,
)


@pytest.fixture(autouse=True)
def fresh_state():
    # Reset module-level state between tests.
    from vulis_obs import setup as s

    s._INITIALIZED = False
    s._GLOBAL_ATTRS.clear()
    yield
    s._INITIALIZED = False
    s._GLOBAL_ATTRS.clear()


def test_init_without_endpoint_is_noop() -> None:
    # Must not raise even with no OTLP collector.
    init_observability(service="dataset", endpoint=None)
    assert is_initialized()


def test_init_is_idempotent() -> None:
    init_observability(service="a")
    init_observability(service="b")  # ignored
    attrs = global_attributes()
    assert attrs.get("service.name") == "a"


def test_init_force_reconfigures() -> None:
    init_observability(service="a")
    init_observability(service="b", force=True)
    assert global_attributes().get("service.name") == "b"


def test_global_attributes_include_surface_and_env() -> None:
    init_observability(service="dataset", surface="edge", environment="prod")
    a = global_attributes()
    assert a["vulis.surface"] == "edge"
    assert a["vulis.environment"] == "prod"
    assert a["service.namespace"] == "vulis"


def test_set_global_attribute_persists() -> None:
    init_observability(service="dataset")
    set_global_attribute("vulis.project_id", "proj_x")
    assert global_attributes()["vulis.project_id"] == "proj_x"


def test_global_attributes_returns_copy() -> None:
    init_observability(service="dataset")
    a = global_attributes()
    a["mutated"] = "yes"
    assert "mutated" not in global_attributes()


# ─── Predefined metrics ──────────────────────────────────────


def test_predefined_contains_key_vulis_metrics() -> None:
    for name in [
        "vulis.dataset.samples_imported",
        "vulis.serving.inferences",
        "vulis.serving.inference_seconds",
        "vulis.fleet.edge_heartbeat",
        "vulis.storage.read_bytes",
    ]:
        assert name in PREDEFINED


def test_predefined_entries_have_kind_unit_desc() -> None:
    for name, (kind, unit, desc) in PREDEFINED.items():
        assert kind in ("counter", "histogram", "up_down_counter"), name
        assert isinstance(unit, str) and unit, name
        assert isinstance(desc, str) and desc, name


# ─── instruments (no-op fallbacks) ───────────────────────────


def test_counter_returns_instrument() -> None:
    c = counter("vulis.dataset.samples_imported")
    # add must not raise.
    c.add(5)
    c.add(3, attributes={"project_id": "proj_x"})


def test_histogram_returns_instrument() -> None:
    h = histogram("vulis.serving.inference_seconds")
    h.record(0.012)
    h.record(2.5, attributes={"model_version": "mdlv_y"})


def test_up_down_counter_returns_instrument() -> None:
    u = up_down_counter("vulis.fleet.edge_online")
    u.add(1)
    u.add(-1)


def test_custom_metric_names_not_in_predefined() -> None:
    # Names outside PREDEFINED are accepted too.
    c = counter("vulis.custom.thing")
    c.add(1)


# ─── spans ───────────────────────────────────────────────────


def test_span_is_context_manager() -> None:
    with span("test.op", k="v"):
        pass


def test_span_merges_global_attrs() -> None:
    init_observability(service="dataset")
    set_global_attribute("vulis.project_id", "proj_x")
    # Just ensure no exception; span attrs are merged internally.
    with span("test.op", extra="y"):
        pass


def test_span_usable_without_init() -> None:
    # No init_observability called yet — must not crash.
    with span("test.op"):
        pass
