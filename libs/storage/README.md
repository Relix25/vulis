# vulis-storage

Backend-agnostic blob storage abstraction for Vulis.

> See [ADR 0006](../../ADR/0006-storage-abstraction.md) for the rationale.

All binary blobs in Vulis (raw images, model artifacts, training outputs)
go through `StorageBackend`. **Never call `open()` directly on a path that
should live in shared storage** — go through this library.

## Available backends

| Backend | Class | When to use |
|---|---|---|
| **SMB (smbprotocol)** | `SmbProtocolBackend` | **Default.** Pure Python, no OS-level mount needed. Works on Linux + Windows. |
| SMB (OS mount) | `SmbMountBackend` | Opt-in performance: relies on an OS-level mount (`/mnt/...` or `Z:\`). Best for training data traversal. |
| Local FS | `LocalFSBackend` | Dev, tests, single-node setups. |
| S3-compatible | `S3Backend` | Future, when MinIO or cloud S3 is available. (Stub in M1.) |

## Install

```bash
uv pip install -e libs/storage
```

## Quick usage

```python
from vulis_storage import build_backend, BackendConfig

cfg = BackendConfig(
    backend="smb-protocol",
    smb_host="nas.plant.local",
    smb_share="vulis",
    smb_username="vulis",
    smb_password="...",
)
backend = build_backend(cfg)

key = backend.put_bytes("models/mydet.onnx", b"...")
data = backend.get_bytes(key)
info = backend.stat(key)
assert info.size == len(data)
```

## Content addressing

`put_bytes` / `put_stream` accept an explicit key. For content-addressed
blobs (dedup), use `put_blob` which hashes the content and returns the
hash-based key:

```python
key = backend.put_blob(b"image-bytes")  # → "sha256/abc123..."
```

## Testing the SMB backend

Live SMB tests are skipped by default. Run them against a real share:

```bash
pytest --smb-host nas.local --smb-share vulis --smb-user me --smb-pass secret
```

## License

BSL 1.1 → AGPL-3.0 on 2030-06-14. See [../../LICENSE](../../LICENSE).
