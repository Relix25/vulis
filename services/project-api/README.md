# Vulis project-api service

> Manages `Project`, `Line`, `Task`, `Campaign` — with append-only audit
> trail, RBAC, and a state machine for `Task` transitions.

This is M1.3 of the Vulis roadmap. See `docs/handoff/04-roadmap.md` for the
full specification and `docs/handoff/03-conventions.md` for the conventions
this service follows.

## Quick start

```bash
# 1. From the monorepo root, install the service and its dev deps
uv sync --package vulis-project --extra dev

# 2. Make sure the platform stack is up (Postgres, Keycloak, ...)
task up:platform && task init:platform

# 3. Apply the migration (the platform's alembic one-shot already did it
#    if it was running — re-run is safe)
cd libs/schemas
uv run alembic -c alembic.ini upgrade head

# 4. Run the service
cd ../../   # back to monorepo root
uv run uvicorn vulis_project.main:app --reload --port 8001
```

OpenAPI docs at <http://127.0.0.1:8001/docs>.

## Auth (dev)

For M1.3 the service uses a **header-based auth stub** instead of a real
OIDC token validation. This is intentional — the gateway (M1.6) will
validate Keycloak JWTs and forward pre-validated claims via headers.

Set on every request:

| Header | Value |
|---|---|
| `X-Tenant-Id` | `tenant_<hex>` (e.g. `tenant_default`) |
| `X-Actor`     | username (recorded in the audit trail) |
| `X-Roles`     | comma-separated Keycloak realm roles, e.g. `admin,data-scientist` |

Missing or malformed → `401`. Wrong role → `403`.

## Endpoints

```
POST   /api/v1/projects                       → 201 Project
GET    /api/v1/projects?project_id=...        → 200 Project[]
GET    /api/v1/projects/{id}                  → 200 Project
PATCH  /api/v1/projects/{id}                  → 200 Project
DELETE /api/v1/projects/{id}                  → 204    (soft delete)

POST   /api/v1/projects/{pid}/lines           → 201 Line
GET    /api/v1/projects/{pid}/lines           → 200 Line[]

POST   /api/v1/projects/{pid}/tasks           → 201 Task
GET    /api/v1/projects/{pid}/tasks           → 200 Task[]
POST   /api/v1/tasks/{tid}:transition         → 200 Task

POST   /api/v1/projects/{pid}/campaigns       → 201 Campaign
GET    /api/v1/projects/{pid}/campaigns       → 200 Campaign[]
```

## State machine (Task)

```
BACKLOG ──start──► IN_PROGRESS ──submit──► IN_VALIDATION
                       ▲                        │
                       │                        ├──approve──► DEPLOYED
                       │                        │                │
                       └──reject────────────────┘                │
                                                                  ▼
                                                              MONITORING
                                                                  │
                                                                  ▼
                                                              RETRAINING
                                                                  │
                                                                  └─► IN_PROGRESS
```

Forbidden transitions → `InvalidTransitionError` → HTTP 409.

## Tests

```bash
uv run pytest -q
```

Target coverage: ≥ 70%.
