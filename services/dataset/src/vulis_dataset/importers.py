"""In-process async import worker.

When a client posts to ``.../import``, we:

1. Create an ``ImportJob`` row in PENDING state and return 202 + job_id.
2. Schedule an ``asyncio.create_task`` that picks up the job and:
   - transitions it to RUNNING + stamps ``started_at``,
   - walks the source (LOCAL directory or ZIP archive),
   - uploads each file to ``vulis_storage`` via ``put_blob`` (content-
     addressed; the digest becomes the key),
   - inserts a ``Sample`` row per file (committing in batches to keep
     the transaction window small),
   - updates progress counters on the job,
   - transitions the job to DONE (or FAILED on error).

The worker is intentionally simple: an in-process asyncio task. M2+
will replace it with a real queue (NATS / Celery) when the import
volume justifies it. For M1.4, ``asyncio.create_task`` is enough.

The worker uses its own session per commit — the API's request session
is already closed by the time the task runs. The session factory is
captured at task creation time.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import asyncio
import io
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePath, PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session, sessionmaker
from vulis_core import get_logger
from vulis_obs import counter as otel_counter
from vulis_obs import histogram as otel_histogram
from vulis_storage import StorageBackend

from vulis_dataset.audit import log_audit
from vulis_dataset.models import (
    Dataset,
    DatasetVersion,
    ImportJob,
    ImportSourceKind,
    ImportStatus,
    Sample,
    Split,
)

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# Module-level events for tests that want to wait until the worker is done.
# A ``threading.Event`` is used (not ``asyncio.Event``) because the
# worker runs in a thread executor on a different event loop than the
# test's loop — cross-loop ``asyncio.Event`` access is broken in
# Python 3.10+.
import_done_event: dict[str, threading.Event] = {}


# ─── Helpers ────────────────────────────────────────────────────


def _is_probably_binary(path: PurePath) -> bool:
    """Quick extension-based guess; we only ingest images + a few common types."""
    ext = path.suffix.lower().lstrip(".")
    return ext in {
        "png",
        "jpg",
        "jpeg",
        "tif",
        "tiff",
        "bmp",
        "webp",
        "gif",
        "npy",
        "npz",
        "pt",
        "pth",
    }


def _derive_label(path: PurePosixPath) -> str | None:
    """Convention: if the path is ``<split>/<label>/<file>``, return ``<label>``.

    Returns ``None`` if the path is too shallow.
    """
    parts = path.parts
    if len(parts) >= 3:
        return parts[-2]
    return None


def _derive_split(path: PurePosixPath, default: str = "TRAIN") -> str:
    """Convention: first path segment is the split (``train``/``val``/``test``)."""
    parts = path.parts
    if not parts:
        return default
    head = parts[0].lower()
    if head in ("train", "val", "validation", "test"):
        # Map "validation" → "VAL" to match the enum.
        if head in ("val", "validation"):
            return "VAL"
        if head == "train":
            return "TRAIN"
        if head == "test":
            return "TEST"
    return default


# ─── Source walkers ─────────────────────────────────────────────


def _walk_local(
    source_descriptor: dict[str, Any],
) -> list[tuple[str, bytes]]:
    """Walk a local directory and return ``(relative_path, bytes)`` pairs.

    Skips non-files, hidden files, and our own dotfiles. Filters by
    extension (image / tensor formats only).
    """
    root = Path(source_descriptor["path"])
    if not root.exists():
        raise FileNotFoundError(f"Local import source does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Local import source is not a directory: {root}")

    out: list[tuple[str, bytes]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if not _is_probably_binary(rel):
            continue
        out.append((rel.as_posix(), p.read_bytes()))
    return out


def _walk_zip(
    source_descriptor: dict[str, Any],
) -> list[tuple[str, bytes]]:
    """Read a ZIP archive and return ``(relative_path, bytes)`` pairs.

    The archive itself is in the storage backend under the key passed
    in ``source_descriptor["blob_key"]``. We stream its members.
    """
    blob_key: str = source_descriptor["blob_key"]
    storage: StorageBackend = source_descriptor["_storage"]
    data = storage.get_bytes(blob_key)
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/"):  # directory entry
                continue
            rel = PurePosixPath(name)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if not _is_probably_binary(rel):
                continue
            out.append((rel.as_posix(), zf.read(name)))
    return out


# ─── Worker core ────────────────────────────────────────────────


def _ingest_into_version(
    session: Session,
    *,
    version: DatasetVersion,
    storage: StorageBackend,
    files: list[tuple[str, bytes]],
) -> tuple[int, int]:
    """Upload + record each file. Returns ``(sample_count, total_bytes)``.

    Commits in batches of 50 to keep transactions short. Updates the
    DatasetVersion's running sample_count / size_bytes on each commit.
    """
    sample_count = 0
    total_bytes = 0
    BATCH = 50
    pending_samples: list[Sample] = []

    for rel_path, data in files:
        # Content-addressed put — idempotent; the digest becomes the key.
        key = storage.put_blob(data)
        digest = key.split("/", 1)[1]  # "sha256/<hex>" → "<hex>"
        path = PurePosixPath(rel_path)
        sample = Sample(
            tenant_id=version.tenant_id,
            version_id=version.id,
            blob_key=key,
            relative_path=rel_path,
            label=_derive_label(path),
            size_bytes=len(data),
            split=Split(_derive_split(path)),
            blob_digest=digest,
        )
        pending_samples.append(sample)
        session.add(sample)
        sample_count += 1
        total_bytes += len(data)
        if len(pending_samples) >= BATCH:
            session.flush()
            session.commit()
            pending_samples = []

    if pending_samples:
        session.flush()
        session.commit()

    # Update version counters.
    version.sample_count = (version.sample_count or 0) + sample_count
    version.size_bytes = (version.size_bytes or 0) + total_bytes
    session.add(version)
    session.commit()
    return sample_count, total_bytes


def _run_job_sync(
    *,
    job_id: str,
    session_factory: sessionmaker[Session],
    storage: StorageBackend,
) -> None:
    """Synchronous core of the import worker. Called from the asyncio task."""
    started = datetime.now(UTC)
    # OTel metrics
    _samples_metric = otel_counter("vulis.dataset.samples_imported")
    _import_seconds_metric = otel_histogram("vulis.dataset.import_seconds")
    _size_bytes_metric = otel_histogram("vulis.dataset.size_bytes")
    _write_bytes_metric = otel_counter("vulis.storage.write_bytes")

    with session_factory() as session:
        job = session.get(ImportJob, job_id)
        if job is None:  # pragma: no cover — defensive
            log.error("import.job.missing", job_id=job_id)
            return
        version = session.get(DatasetVersion, job.version_id)
        if version is None:  # pragma: no cover — defensive
            job.status = ImportStatus.FAILED
            job.error_message = f"Version {job.version_id} not found"
            job.completed_at = datetime.now(UTC)
            session.add(job)
            session.commit()
            return
        if version.is_published:
            # Refuse to add samples to a published version.
            job.status = ImportStatus.FAILED
            job.error_message = f"Version {version.id} is already published"
            job.completed_at = datetime.now(UTC)
            session.add(job)
            session.commit()
            return

        job.status = ImportStatus.RUNNING
        job.started_at = started
        session.add(job)
        session.commit()

        try:
            if job.source_kind == ImportSourceKind.LOCAL:
                files = _walk_local(job.source_descriptor)
            elif job.source_kind == ImportSourceKind.ZIP:
                files = _walk_zip({**job.source_descriptor, "_storage": storage})
            else:  # pragma: no cover — M1.4 only implements LOCAL + ZIP
                raise NotImplementedError(
                    f"Import source {job.source_kind!r} not implemented in M1.4"
                )

            job.total_samples = len(files)
            session.add(job)
            session.commit()

            n, total = _ingest_into_version(session, version=version, storage=storage, files=files)

            elapsed = (datetime.now(UTC) - started).total_seconds()
            job.processed_samples = n
            job.total_bytes = total
            job.status = ImportStatus.DONE
            job.completed_at = datetime.now(UTC)
            session.add(job)
            session.commit()

            # OTel — fire-and-forget; the no-op fallback handles missing SDK.
            try:
                _samples_metric.add(n, attributes={"dataset_id": version.dataset_id})
                _import_seconds_metric.record(
                    elapsed, attributes={"dataset_id": version.dataset_id}
                )
                _size_bytes_metric.record(total, attributes={"dataset_id": version.dataset_id})
                _write_bytes_metric.add(total, attributes={"service": "dataset-api"})
            except Exception:  # pragma: no cover — never let metrics fail the job
                pass

            # Audit: import job completed.
            dataset = session.get(Dataset, version.dataset_id)
            if dataset is not None:  # pragma: no cover — defensive
                log_audit(
                    session,
                    tenant_id=version.tenant_id,
                    actor=job.source_descriptor.get("actor") or "system",
                    action="dataset.import.done",
                    target_type="dataset_version",
                    target_id=version.id,
                    diff={
                        "job_id": job.id,
                        "imported_samples": n,
                        "size_bytes": total,
                        "elapsed_seconds": elapsed,
                    },
                )
                session.commit()
            log.info(
                "import.job.done",
                job_id=job.id,
                version_id=version.id,
                samples=n,
                bytes=total,
                elapsed_s=round(elapsed, 3),
            )
        except Exception as e:
            log.warning("import.job.failed", job_id=job.id, error=str(e))
            job.status = ImportStatus.FAILED
            job.error_message = f"{type(e).__name__}: {e}"
            job.completed_at = datetime.now(UTC)
            session.add(job)
            session.commit()


async def run_import_job(
    *,
    job_id: str,
    session_factory: sessionmaker[Session],
    storage: StorageBackend,
) -> None:
    """Async entry point — schedules the sync core on a thread.

    Synchronous file IO + ORM work is moved off the event loop so we
    don't block the API. In M1.4, the thread is implicit (asyncio
    default executor); M2+ may use a real thread pool.
    """
    from functools import partial

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(_run_job_sync, job_id=job_id, session_factory=session_factory, storage=storage),
        )
    except Exception as e:  # pragma: no cover — final safety net
        log.error("import.job.crashed", job_id=job_id, error=str(e))
        with session_factory() as session:
            job = session.get(ImportJob, job_id)
            if job is not None and job.status not in (
                ImportStatus.DONE,
                ImportStatus.FAILED,
            ):
                job.status = ImportStatus.FAILED
                job.error_message = f"worker crashed: {e}"
                job.completed_at = datetime.now(UTC)
                session.add(job)
                session.commit()
    finally:
        # Notify any test that registered an event for this job.
        ev = import_done_event.pop(job_id, None)
        if ev is not None:
            ev.set()


def schedule_import_job(
    *,
    job_id: str,
    session_factory: sessionmaker[Session],
    storage: StorageBackend,
) -> asyncio.Task[None]:
    """Create the asyncio task. Returns the Task (tests can await it)."""
    return asyncio.create_task(
        run_import_job(job_id=job_id, session_factory=session_factory, storage=storage)
    )


__all__ = [
    "import_done_event",
    "run_import_job",
    "schedule_import_job",
]
