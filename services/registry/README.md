# Vulis model registry service

> Manages `Model`, `ModelVersion`, and `OnnxTensorSpec` — with the
> industrial approval workflow (DRAFT → INTERNAL_REVIEW → STAGING →
> APPROVED → DEPLOYED), ONNX validation, and auto-generated model cards.

This is M1.5 of the Vulis roadmap. See `docs/handoff/04-roadmap.md` for
the full specification and `docs/handoff/03-conventions.md` for the
conventions this service follows.

## Quick start

```bash
# 1. From the monorepo root, install the service and its dev deps
uv sync --package vulis-registry --extra dev

# 2. Make sure the platform stack is up (Postgres, Keycloak, ...)
task up:platform && task init:platform

# 3. Apply the migration
cd libs/schemas
uv run alembic -c alembic.ini upgrade head

# 4. Run the service
cd ../../
uv run uvicorn vulis_registry.main:app --reload --port 8003
```

OpenAPI docs at <http://127.0.0.1:8003/docs>.

## Auth (dev)

Header-based stub, same convention as the other services:

| Header | Value |
|---|---|
| `X-Tenant-Id` | `tenant_<hex>` |
| `X-Actor`     | username (recorded in the audit trail) |
| `X-Roles`     | comma-separated Keycloak realm roles |

## Endpoints

```
POST   /api/v1/models                            → 201 Model
GET    /api/v1/models?project_id=...             → 200 Model[]
GET    /api/v1/models/{id}                       → 200 Model

POST   /api/v1/models/{id}/versions:upload       → 201 ModelVersion  (multipart ONNX)
GET    /api/v1/models/{id}/versions              → 200 ModelVersion[]
GET    /api/v1/models/{id}/versions/{vid}        → 200 ModelVersion
GET    /api/v1/models/{id}/versions/{vid}/card   → 200 text/markdown
GET    /api/v1/models/{id}/versions/{vid}/artifact → 200 application/octet-stream

POST   /api/v1/models/{id}/versions/{vid}:promote → 200 ModelVersion  (transition)
```

## Approval workflow

```
DRAFT ──submit_for_review──► INTERNAL_REVIEW ──approve──► STAGING
                                  │                            │
                                  ├──reject──► REJECTED        ├──approve──► APPROVED
                                  ▲                            │                │
                                  └─────── (resubmit)          └──reject───────┘
                                                                       │
                                                                       ▼
                                                                   DEPLOYED
                                                                       │
                                                                       ▼
                                                                   ARCHIVED
```

Transitions are role-gated (per-verb):

| Verb                  | Required role(s)           |
|-----------------------|----------------------------|
| `submit_for_review`   | `data-scientist`, `admin`  |
| `approve` (review)    | `reviewer`, `admin`        |
| `reject` (review)     | `reviewer`, `admin`        |
| `approve` (staging)   | `reviewer`, `admin`        |
| `reject` (staging)    | `reviewer`, `admin`        |
| `deploy`              | `operator`, `admin`        |
| `archive`             | `admin`                    |

Forbidden transitions → `InvalidTransitionError` → HTTP 409.
Wrong role → 403.

## Model card

A `GET .../versions/{vid}/card` returns a Markdown document auto-built
from:

- Model + version metadata
- ONNX specs (opset, input/output tensors, shapes)
- Trained-on dataset version (if linked)
- Approval transition history
- BSL-1.1 disclaimer footer

Templated with Jinja2 (`vulis_registry/card_template.md.j2`).

## ONNX validation

`POST ...:upload` streams the file, computes the sha256 on the fly,
validates the bytes with `onnx.load_from_string`, then runs
`onnx.shape_inference.infer_shapes` to extract input/output specs.
Upload of a non-ONNX file → 422.

The artifact is stored as `"sha256/<hex>"` in `vulis_storage` (content-
addressed; re-upload of the same bytes is a no-op).

## Tests

```bash
uv run pytest -q
```

Target coverage: ≥ 70%.
