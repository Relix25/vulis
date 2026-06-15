"""ONNX validation helper.

Loads the raw bytes of a ``.onnx`` file, verifies it's a valid ONNX
model, extracts the default opset version, and runs shape inference
to pull the per-tensor input/output specifications.

Wrapped in this module so:

* Routes can call ``validate_onnx(blob)`` and get a structured
  ``OnnxMetadata`` they can persist as ``OnnxTensorSpec`` rows.
* Errors are caught and re-raised as ``VulisError`` subclasses
  (e.g. ``ValidationError``) for the exception handler.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# onnx is a hard dep (pyproject.toml) so importing it is safe at
# service startup.
import onnx
from onnx import shape_inference
from vulis_core import ValidationError


@dataclass(frozen=True)
class TensorSpec:
    """One input or output tensor."""

    name: str
    dtype: str
    shape: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "dtype": self.dtype, "shape": list(self.shape)}


@dataclass(frozen=True)
class OnnxMetadata:
    """All the metadata we extract from an uploaded ONNX file."""

    opset: int
    producer_name: str | None
    producer_version: str | None
    ir_version: int
    inputs: list[TensorSpec] = field(default_factory=list)
    outputs: list[TensorSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opset": self.opset,
            "producer_name": self.producer_name,
            "producer_version": self.producer_version,
            "ir_version": self.ir_version,
            "inputs": [t.to_dict() for t in self.inputs],
            "outputs": [t.to_dict() for t in self.outputs],
        }


def _shape_from_type(onnx_type: Any) -> list[int]:
    """Extract a concrete shape from an ONNX TypeProto, or ``[]`` if symbolic.

    Dynamic dims (parametrised by a name in the graph) are returned as
    ``-1`` — a common convention in deep learning frameworks.
    """
    shape: list[int] = []
    if not onnx_type.HasField("tensor_type"):
        return shape
    ttype = onnx_type.tensor_type
    if not ttype.HasField("shape"):
        return shape
    for dim in ttype.shape.dim:
        if dim.HasField("dim_value") and dim.dim_value > 0:
            shape.append(int(dim.dim_value))
        elif dim.HasField("dim_param") and dim.dim_param:
            # Symbolic dim — return -1 as a generic "dynamic" marker.
            shape.append(-1)
        else:
            # Unknown — keep as -1.
            shape.append(-1)
    return shape


def _dtype_name(elem_type: int) -> str:
    """Map an ONNX TensorProto element type to its name (e.g. ``FLOAT``, ``INT64``).

    Falls back to ``"UNDEFINED_<n>"`` for unknown codes.
    """
    try:
        return onnx.TensorProto.DataType.Name(elem_type)  # type: ignore[attr-defined]
    except ValueError:
        return f"UNDEFINED_{elem_type}"


def _tensor_spec(name: str, value_info: Any) -> TensorSpec:
    dtype = ""
    if value_info.type.HasField("tensor_type"):
        dtype = _dtype_name(value_info.type.tensor_type.elem_type)
    return TensorSpec(name=name, dtype=dtype, shape=_shape_from_type(value_info.type))


def validate_onnx(data: bytes) -> OnnxMetadata:
    """Parse ``data`` as an ONNX model and extract its metadata.

    Raises ``ValidationError`` if the bytes are not a valid ONNX
    model. Shape inference failures are also surfaced as
    ``ValidationError`` (we'd rather reject than store broken specs).
    """
    try:
        model = onnx.load_from_string(data)
    except Exception as e:
        raise ValidationError(
            f"Failed to parse ONNX model: {e}",
            details={"error": str(e)},
        ) from e

    # Default opset (the empty-domain one is what matters for ONNX
    # runtime; other domains are framework-specific).
    opset = 0
    for o in model.opset_import:
        if o.domain in ("", "ai.onnx"):
            opset = max(opset, o.version)
    if opset == 0:
        raise ValidationError(
            "ONNX model is missing the default ('ai.onnx') opset import",
            details={"opset_imports": [(o.domain, o.version) for o in model.opset_import]},
        )

    # Producer info (best-effort).
    producer_name = None
    producer_version = None
    if model.producer_name:
        producer_name = model.producer_name
    if model.producer_version:
        producer_version = model.producer_version

    # Shape inference — fills in unknown dims if the model supports
    # it. We wrap in try/except because some legacy ONNX exporters
    # produce models that shape_inference can't handle.
    try:
        inferred = shape_inference.infer_shapes(model)
    except Exception as e:
        raise ValidationError(
            f"ONNX shape inference failed: {e}",
            details={"error": str(e)},
        ) from e

    inputs = [_tensor_spec(i.name, i) for i in inferred.graph.input]
    outputs = [_tensor_spec(o.name, o) for o in inferred.graph.output]

    return OnnxMetadata(
        opset=opset,
        producer_name=producer_name,
        producer_version=producer_version,
        ir_version=int(model.ir_version),
        inputs=inputs,
        outputs=outputs,
    )


__all__ = [
    "OnnxMetadata",
    "TensorSpec",
    "validate_onnx",
]
