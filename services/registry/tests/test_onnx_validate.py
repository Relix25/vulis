"""Tests for the ONNX validator."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import onnx
import pytest
from vulis_core import ValidationError

from vulis_registry.onnx_validate import validate_onnx


def _make_minimal_onnx_bytes() -> bytes:
    """Build a minimal valid ONNX model in memory and return its bytes.

    A single ``Add`` op: input0 + input1 → output. All FLOAT, scalar
    shape. We round-trip through ``onnx.load`` to make sure the model
    is valid, then serialize to bytes.
    """
    a = onnx.helper.make_tensor_value_info("a", onnx.TensorProto.FLOAT, [1, 3])
    b = onnx.helper.make_tensor_value_info("b", onnx.TensorProto.FLOAT, [1, 3])
    y = onnx.helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, [1, 3])
    add_node = onnx.helper.make_node("Add", inputs=["a", "b"], outputs=["y"])
    graph = onnx.helper.make_graph(
        nodes=[add_node],
        name="add_graph",
        inputs=[a, b],
        outputs=[y],
    )
    opset = onnx.helper.make_opsetid("", 17)
    model = onnx.helper.make_model(graph, opset_imports=[opset], producer_name="vulis-test")
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _make_onnx_with_batch_dim() -> bytes:
    """Build an ONNX model with a dynamic (symbolic) batch dim."""
    a = onnx.helper.make_tensor_value_info("a", onnx.TensorProto.FLOAT, ["batch", 3, 224, 224])
    y = onnx.helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, ["batch", 3, 224, 224])
    relu_node = onnx.helper.make_node("Relu", inputs=["a"], outputs=["y"])
    graph = onnx.helper.make_graph(nodes=[relu_node], name="relu", inputs=[a], outputs=[y])
    opset = onnx.helper.make_opsetid("", 17)
    model = onnx.helper.make_model(graph, opset_imports=[opset])
    onnx.checker.check_model(model)
    return model.SerializeToString()


def test_validate_minimal_onnx():
    data = _make_minimal_onnx_bytes()
    meta = validate_onnx(data)
    assert meta.opset == 17
    assert meta.ir_version == 8
    assert meta.producer_name == "vulis-test"
    # Two inputs, one output.
    assert len(meta.inputs) == 2
    assert len(meta.outputs) == 1
    # Names match.
    names = {t.name for t in meta.inputs}
    assert names == {"a", "b"}
    assert meta.outputs[0].name == "y"
    # DType.
    assert all(t.dtype == "FLOAT" for t in meta.inputs)
    assert meta.outputs[0].dtype == "FLOAT"
    # Shape round-trips.
    assert meta.inputs[0].shape == [1, 3]


def test_validate_onnx_with_dynamic_dim():
    data = _make_onnx_with_batch_dim()
    meta = validate_onnx(data)
    # Symbolic dim becomes -1 in our mapping.
    assert meta.inputs[0].shape == [-1, 3, 224, 224]


def test_validate_invalid_bytes_raises():
    with pytest.raises(ValidationError) as exc_info:
        validate_onnx(b"this is definitely not an ONNX file")
    assert "Failed to parse" in str(exc_info.value)


def test_validate_empty_bytes_raises():
    # Empty bytes parses as an empty ModelProto (no error from onnx),
    # but the missing-opset check rejects it.
    with pytest.raises(ValidationError) as exc_info:
        validate_onnx(b"")
    assert "opset" in str(exc_info.value).lower()


def test_to_dict_round_trip():
    data = _make_minimal_onnx_bytes()
    meta = validate_onnx(data)
    d = meta.to_dict()
    assert d["opset"] == 17
    assert isinstance(d["inputs"], list)
    assert len(d["inputs"]) == 2
    # Each input has the expected keys.
    for t in d["inputs"]:
        assert set(t.keys()) == {"name", "dtype", "shape"}
