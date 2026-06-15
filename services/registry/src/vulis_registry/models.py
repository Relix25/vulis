"""SQLAlchemy ORM models for the registry service.

Tables created by migration 0004_models.py. If you change a model, you
MUST change the migration in lockstep — the project doesn't rely on
Alembic autogenerate for this service.

Models
------
* ``Model``         — a named, tenant-scoped, soft-deletable model
                       belonging to a Project. Holds the metadata that
                       is stable across versions (task kind, name,
                       description).
* ``ModelVersion``  — a single SemVer release of a Model. Holds the
                       ONNX artifact reference (storage key + sha256
                       digest), the approval state, and the
                       ``trained_on_dataset_version_id`` link to the
                       dataset registry (M1.4).
* ``OnnxTensorSpec``— the per-tensor input/output shape and dtype,
                       captured at upload time from
                       ``onnx.shape_inference``.

Approval state machine — see ``state_machine.py``. Transitions are
role-gated (see routes).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from vulis_schemas import Base, SoftDelete, TenantScoped, Timestamped, UUIDPrimaryKey

# ─── Enums ─────────────────────────────────────────────────────


class ModelStatus(str, enum.Enum):
    """Lifecycle state of a ModelVersion.

    Workflow::

        DRAFT ──submit_for_review──► INTERNAL_REVIEW
                                        │      │
                                  approve      reject
                                        │      │
                                        ▼      ▼
                                     STAGING  REJECTED
                                        │      ▲
                                  approve      │
                                        │      │ (resubmit from DRAFT)
                                        ▼      │
                                     APPROVED ─┘ (reject goes back to INTERNAL_REVIEW? — no,
                                        │      see transition graph in state_machine.py)
                                        │      We allow reject from STAGING → DRAFT)
                                        │
                                        ├──deploy──► DEPLOYED
                                        │
                                        └──archive──► ARCHIVED
    """

    DRAFT = "DRAFT"
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    STAGING = "STAGING"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


# ─── Tables ────────────────────────────────────────────────────


class Model(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    """A Vulis model — a named, versioned collection of ONNX artifacts.

    The model itself is a thin container; all the artifact data lives
    on its ``ModelVersion`` rows. Soft-deletable — but published
    versions remain referencable from the fleet manager (M1.6) and
    the serving stack (M4).
    """

    __tablename__ = "models"

    # FK to Project (M1.3). Cross-service FK validated at the DB
    # layer; no Python import of vulis_project in this package.
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reusing TaskKind from the project-api domain — stored as the
    # same enum values (DETECTION, CLASSIFICATION, SEGMENTATION). We
    # do NOT import the enum class itself to keep services decoupled
    # at the Python level; the value set is the contract.
    task_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Free-form metadata (use case, business owner, ...).
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ModelVersion(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """A single SemVer release of a Model.

    Holds the ONNX artifact reference (storage key + sha256 digest),
    the approval state, and the ``trained_on_dataset_version_id`` link
    to the dataset registry (M1.4). Drafts are mutable; published
    versions (APPROVED, DEPLOYED) are effectively immutable — the
    artifact and ONNX specs are frozen.
    """

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "major",
            "minor",
            "patch",
            name="uq_model_versions_semver",
        ),
    )

    model_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    major: Mapped[int] = mapped_column(default=0, nullable=False)
    minor: Mapped[int] = mapped_column(default=0, nullable=False)
    patch: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[ModelStatus] = mapped_column(
        SAEnum(ModelStatus, name="modelstatus"),
        nullable=False,
        default=ModelStatus.DRAFT,
    )
    # Storage reference (content-addressed "sha256/<hex>").
    artifact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Link to the DatasetVersion this model was trained on (optional
    # but recommended). Cross-service FK validated at the DB layer.
    trained_on_dataset_version_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # MLflow integration (deferred to M2+; column reserved for
    # forward-compat with the run IDs we'll need for the model card).
    mlflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Default ONNX opset — captured at upload.
    onnx_opset: Mapped[int] = mapped_column(default=0, nullable=False)
    # Free-form model card text (markdown). Auto-generated at upload
    # from a Jinja2 template; can be edited later.
    model_card: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-form metadata (e.g. training hyperparams).
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    model: Mapped[Model] = relationship(back_populates="versions")
    onnx_specs: Mapped[list[OnnxTensorSpec]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OnnxTensorSpec(Base, UUIDPrimaryKey, Timestamped):
    """One input or output tensor spec of a ModelVersion's ONNX graph.

    Captured at upload time from ``onnx.shape_inference``. Used by the
    model card and by the serving layer to know what to feed in and
    what to expect out.
    """

    __tablename__ = "model_onnx_specs"

    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("model_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # "input" | "output"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dtype: Mapped[str] = mapped_column(String(64), nullable=False)
    # Shape as a list of ints; -1 is the dynamic dim (batch, etc.).
    shape: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)

    version: Mapped[ModelVersion] = relationship(back_populates="onnx_specs")


__all__ = [
    "Base",
    "Model",
    "ModelStatus",
    "ModelVersion",
    "OnnxTensorSpec",
]
