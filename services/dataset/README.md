# Vulis dataset service

> Manages versioned, content-addressed datasets with manifest publishing
> and async bulk import.

This is M1.4 of the Vulis roadmap. See `docs/handoff/04-roadmap.md` for the
full specification and `docs/handoff/03-conventions.md` for the conventions
this service follows.

## Quick start

```bash
# 1. From the monorepo root, install the service and its dev deps
uv sync --package vulis-dataset --extra dev

# 2. Make sure the platform stack is up (Postgres, Keycloak, ...)
task up:platform && task init:platform

# 3. Apply the migration (the platform's alembic one-shot already did it
#    if it was running — re-run is safe)
cd libs/schemas
uv run alembic -c alembic.ini upgrade head

# 4. Run the service
cd ../../
uv run uvicorn vulis_dataset.main:app --reload --port 8002
```

OpenAPI docs at <http://127.0.0.1:8002/docs>.

## Auth (dev)

Header-based stub, same convention as `project-api`:

| Header | Value |
|---|---|
| `X-Tenant-Id` | `tenant_<hex>` |
| `X-Actor`     | username (recorded in the audit trail) |
| `X-Roles`     | comma-separated Keycloak realm roles |

Missing or malformed → `401`. Wrong role → `403`.

## Endpoints

```
POST   /api/v1/datasets                              → 201 Dataset
GET    /api/v1/datasets?project_id=...               → 200 Dataset[]
GET    /api/v1/datasets/{id}                         → 200 Dataset

POST   /api/v1/datasets/{id}/versions                → 201 DatasetVersion (draft)
GET    /api/v1/datasets/{id}/versions                → 200 DatasetVersion[]
GET    /api/v1/datasets/{id}/versions/{vid}          → 200 DatasetVersion
GET    /api/v1/datasets/{id}/versions/{vid}/manifest → 200 Manifest

POST   /api/v1/datasets/{id}/versions/{vid}/import   → 202 {job_id}   (async)
GET    /api/v1/import-jobs/{job_id}                  → 200 ImportJob

POST   /api/v1/datasets/{id}/versions/{vid}:split    → 200 DatasetVersion
POST   /api/v1/datasets/{id}/versions/{vid}:publish  → 200 DatasetVersion (immutable)
```

## Versioning

Datasets are versioned using SemVer (`major.minor.patch`) and pinned to a
dataset with a unique constraint. A version is created in **draft** state
(samples can still be added); once **published** it becomes immutable and
its manifest is content-addressed (`sha256/<hex>`) and stored in
`vulis_storage` (SMB-protocol in prod, local-fs in dev).

Re-publishing a published version → `409`. Two versions with the same
`(dataset_id, major, minor, patch)` → `409`.

## Manifest

A published version has a `manifest.json` stored as a content-addressed
blob. The manifest is a JSON document that lists every sample by its
content-addressed key:

```json
{
  "version": "1.2.0",
  "dataset_id": "ds_abc",
  "task_kind": "DETECTION",
  "sample_count": 100,
  "size_bytes": 12345678,
  "samples": [
    {"key": "sha256/abcd...", "path": "train/img_001.png",
     "label": "ok", "split": "TRAIN", "size_bytes": 12345},
    ...
  ]
}
```

The `manifest_digest` stored on the `DatasetVersion` row is the sha256 of
this exact document. Verifying integrity = recomputing sha256 of the
stored manifest blob and comparing to `manifest_digest`.

## Tests

```bash
uv run pytest -q
```

Target coverage: ≥ 70%.
