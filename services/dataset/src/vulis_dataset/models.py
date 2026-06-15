"""SQLAlchemy ORM models for the dataset service.

Tables created by migration 0003_datasets.py. If you change a model, you
MUST change the migration in lockstep — the project doesn't rely on
Alembic autogenerate for this service.

Models
------
* ``Dataset``        — a named, tenant-scoped collection of versioned samples
                       for a given task kind. Belongs to a Project (M1.3).
* ``DatasetVersion`` — a single SemVer release of a Dataset. Drafts are
                       mutable; published versions are immutable. The
                       manifest is content-addressed and stored via
                       ``vulis_storage``.
* ``Sample``         — a single sample belonging to a ``DatasetVersion``.
                       Content-addressed blob key + relative path + split
                       + optional label.
* ``ImportJob``      — async import job record. Tracks progress of a bulk
                       ingest (local-fs, zip, etc.) so the API can return
                       202 + job_id immediately.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
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


class Split(str, enum.Enum):
    """Train/Val/Test split a sample is assigned to."""

    TRAIN = "TRAIN"
    VAL = "VAL"
    TEST = "TEST"


class ImportSourceKind(str, enum.Enum):
    """What an import job is pulling from.

    M1.4 implements ``LOCAL`` and ``ZIP``. ``CVAT`` and ``S3`` are
    reserved for later milestones.
    """

    LOCAL = "LOCAL"
    ZIP = "ZIP"
    CVAT = "CVAT"
    S3 = "S3"


class ImportStatus(str, enum.Enum):
    """Lifecycle of an import job.

    State machine::

        PENDING ──► RUNNING ──► DONE
                          └──► FAILED
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


# ─── Tables ────────────────────────────────────────────────────


class Dataset(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    """A Vulis dataset — a named, versioned collection of samples for a task kind.

    The dataset itself is a thin container; all sample data lives on its
    ``DatasetVersion`` rows. Soft-deletable — but published versions
    remain referencable from the model registry (M1.5) even after the
    dataset is marked deleted.
    """

    __tablename__ = "datasets"

    # FK to Project (M1.3). The reference is intentional across services
    # (a Dataset is always owned by a Project) but we only validate the
    # foreign key at the DB layer — there is no Python import of
    # vulis_project in this package.
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reusing TaskKind from the project-api domain — stored as the same
    # enum values (DETECTION, CLASSIFICATION, SEGMENTATION). We do NOT
    # import the enum class itself to keep services decoupled at the
    # Python level; the value set is the contract.
    task_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Free-form metadata (e.g. domain tags, source). Column name has the
    # trailing underscore to avoid colliding with SQLAlchemy ``Base.metadata``.
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DatasetVersion(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """A single SemVer release of a Dataset.

    Drafts (``is_published=False``) can accumulate Samples. Publishing
    freezes the version: it writes the manifest blob, sets
    ``is_published=True`` and ``manifest_digest``, and the version is
    considered immutable thereafter. ``manifest_key`` is the
    content-addressed storage key (``"sha256/<hex>"``).
    """

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "major",
            "minor",
            "patch",
            name="uq_dataset_versions_semver",
        ),
    )

    dataset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    major: Mapped[int] = mapped_column(default=0, nullable=False)
    minor: Mapped[int] = mapped_column(default=0, nullable=False)
    patch: Mapped[int] = mapped_column(default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Content-addressed storage key for the manifest JSON. Null until publish.
    manifest_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # sha256 of the manifest JSON; null until publish. Used to verify the
    # stored blob is byte-identical to the one we computed at publish.
    manifest_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sample_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-form: source URL, license, notes, ... (trailing underscore
    # to avoid clashing with SQLAlchemy ``Base.metadata``).
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    samples: Mapped[list[Sample]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Sample(Base, UUIDPrimaryKey, Timestamped):
    """A single sample belonging to a ``DatasetVersion``.

    The blob itself lives in ``vulis_storage``; this row is metadata
    plus the storage key. ``blob_digest`` is the sha256 of the blob's
    bytes and is used for dedup + integrity.
    """

    __tablename__ = "dataset_samples"
    __table_args__ = (
        # Common read path is "give me the train samples of this version".
        Index("ix_dataset_samples_version_split", "version_id", "split"),
    )

    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # POSIX-style content-addressed key ("sha256/<hex>").
    blob_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # Path relative to the version root (e.g. "train/img_001.png").
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Optional annotation key — separate blob (CVAT export, JSON, ...).
    annotation_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    split: Mapped[Split] = mapped_column(
        SAEnum(Split, name="datasplit"), nullable=False, default=Split.TRAIN
    )
    # sha256 of the blob content.
    blob_digest: Mapped[str] = mapped_column(String(128), nullable=False)

    version: Mapped[DatasetVersion] = relationship(back_populates="samples")


class ImportJob(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    """A single async import job.

    Created when a client posts to ``.../import``. The status moves
    ``PENDING → RUNNING → DONE|FAILED`` driven by an in-process worker
    (asyncio task). Polled via ``GET /api/v1/import-jobs/{job_id}``.
    """

    __tablename__ = "dataset_import_jobs"
    __table_args__ = (Index("ix_dataset_import_jobs_status", "status"),)

    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_kind: Mapped[ImportSourceKind] = mapped_column(
        SAEnum(ImportSourceKind, name="importsourcekind"), nullable=False
    )
    # Free-form, source-specific descriptor (e.g. {"path": "/data/raw/x"}
    # for LOCAL, {"filename": "x.zip"} for ZIP). Kept opaque here.
    source_descriptor: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ImportStatus] = mapped_column(
        SAEnum(ImportStatus, name="importstatus"),
        nullable=False,
        default=ImportStatus.PENDING,
    )
    total_samples: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    processed_samples: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "Base",
    "Dataset",
    "DatasetVersion",
    "ImportJob",
    "ImportSourceKind",
    "ImportStatus",
    "Sample",
    "Split",
]
