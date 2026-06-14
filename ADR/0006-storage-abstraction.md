# 0006. Storage: backend abstraction, SMB default via smbprotocol

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis stores two categories of data:

- **Metadata** (datasets, models, projects, audit events): structured, lives
  in Postgres.
- **Blobs** (raw images, model artifacts, training outputs): large, binary,
  content-addressed.

The deployment uses **Windows SMB shares** as the central blob store, accessed
from Linux (edge) and Windows (server, workstation) alike. We want zero
dependency on OS-level mounts in the default case (to keep install simple and
privilege-free), while preserving an option for higher performance when the
operator is willing to mount the share at the OS level.

## Decision drivers

- Default path must work on Linux + Windows without OS-level configuration.
- Performance: traversing thousands of small files (training data) is much
  faster via an OS mount than via a userspace SMB library.
- Future-proofing: we may want S3-compatible storage later (MinIO or cloud).
- Avoiding lock-in: service code must not call `open()` on absolute paths.

## Considered options

### Option A: MinIO only

- Pros: S3-compatible, mature, great API.
- Cons: would require running MinIO on the (GPU-less, already-busy) server,
  duplicating storage already present on the SMB shares; not what the
  deployment context provides.

### Option B: Direct `open()` calls + SMB mount everywhere

- Pros: simplest code.
- Cons: requires OS-level SMB mounts on every host, with admin privileges
  and per-OS setup; fragile.

### Option C: Custom `StorageBackend` abstraction with multiple backends (chosen)

A small Python package (`libs/storage`) defines a `StorageBackend` protocol
with implementations:

- `SmbProtocolBackend` — **default**, pure Python via `smbprotocol`, no OS
  mount needed.
- `SmbMountBackend` — relies on an OS-level mount; used for performance when
  the operator chooses to mount.
- `LocalFSBackend` — local filesystem, used in dev/tests.
- `S3Backend` — future, when MinIO/S3 is available.

All Vulis code interacts with blobs through this abstraction only.

## Decision

**Adopt Option C.** `libs/storage` is the sole entry point for blob access.
The default backend is `SmbProtocolBackend`. Configuration selects the
backend per environment via environment variables / config file.

## Rationale

The abstraction gives us:

1. **Zero-privilege default install** (pure Python SMB).
2. **Opt-in performance** (mount the share, switch backend by config).
3. **Future S3 path** without rewriting services.
4. **Testability** (`LocalFSBackend` in CI, no SMB server needed).

## Interface sketch

```python
class StorageBackend(Protocol):
    def put(self, key: str, data: bytes | BinaryIO) -> str: ...
    def get(self, key: str) -> BinaryIO: ...
    def stat(self, key: str) -> ObjectInfo: ...
    def list(self, prefix: str) -> Iterator[str]: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
```

Keys are content-hash based for blobs (dedup), explicit for manifests.

## Consequences

- **Positive:** OS-agnostic default; testable; swappable.
- **Negative:** a thin layer to maintain; the `SmbMountBackend` and
  `SmbProtocolBackend` semantics must match closely (documented).
- **Neutral:** services declare a `StorageBackend` dependency (DI), not a
  path.

## Risks & mitigations

- *Risk:* `smbprotocol` performance on bulk reads. *Mitigation:* the
  `SmbMountBackend` is a one-line config switch for training workloads.
- *Risk:* backend divergence (one backend lacks an operation). *Mitigation:*
  the `Protocol` defines the common surface; capabilities are declared per
  backend and asserted in tests.

## Compliance

Documented in [ARCHITECTURE.md §5](../ARCHITECTURE.md). `libs/storage` ships
unit tests for every backend.

## References

- `smbprotocol` docs: <https://github.com/jborean93/smbprotocol>
- [ADR 0005](./0005-topology-3-surfaces.md) — server holds the central share.
