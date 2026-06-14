# Vulis — Architecture

> **Living document.** This is the canonical description of Vulis' architecture.
> Material changes require an [ADR](./ADR/). Last updated: 2026-06-14 (M1).

---

## 1. Goals & non-goals

### Goals

- End-to-end industrial **computer-vision inspection**: defect detection,
  classification, segmentation.
- **Air-gap** operation: no internet required at runtime on the server or
  edge.
- **Heterogeneous compute placement**: control plane (server) separated from
  compute (workstation for training, edge for inference).
- **Reproducibility & governance**: versioned datasets and models, append-only
  audit trail, structured approval workflow.
- **Linux + Windows** parity (server is Windows).
- **Open source**: BSL 1.1 → AGPL-3.0 on 2030-06-14.

### Non-goals (for now)

- Cloud-only deployment (no first-class cloud provider SDKs).
- General-purpose ML platform (Vulis is vision-industry focused).
- Real-time control of industrial equipment (no PLC logic; we observe and
  advise).

---

## 2. Three-surface topology

Vulis is deployed across three surfaces, each with distinct capabilities:

```
┌────────────────────────────┐
│   SURFACE 1: WORKSTATION   │   The engineer's PC.
│   - GPU (training)         │   - Has internet (via proxy).
│   - App Tauri + CLI        │   - No direct access to edge nodes.
│   - Air-gap relay          │   - Pulls datasets, pushes models.
└─────────────┬──────────────┘
              │
              │  LAN (proxy-aware), API + SMB
              ▼
┌────────────────────────────┐
│   SURFACE 2: SERVER (Win)  │   Control plane. No GPU.
│   - Postgres, Mosquitto    │   - Air-gap (no internet).
│   - Redis, Keycloak        │   - Central SMB shares.
│   - Webapp + REST/gRPC API │   - Sole bridge to edge nodes.
│   - Fleet manager          │
└─────────────┬──────────────┘
              │
              │  LAN, MQTT 5 + Sparkplug B (pull + push)
              ▼
┌────────────────────────────┐
│   SURFACE 3: EDGE ×N       │   One per production line.
│   - GPU (inference)        │   - Air-gap total.
│   - Cameras (acquisition)  │   - Self-contained.
│   - Serving (ONNX Runtime) │   - Pulls updates from server.
└────────────────────────────┘
```

**Why three surfaces?** The deployment context dictates it:

- The server is a Windows machine without GPU — it cannot train or infer.
- Edge nodes have the GPUs but are network-isolated (only reachable via the
  server).
- Only the workstation has internet — it must relay external artifacts.

### Communication summary

| Path | Transport | Purpose |
|---|---|---|
| Workstation ↔ Server | HTTPS (REST/gRPC) + SMB | Datasets, models, run results, management. |
| Server ↔ Edge | **MQTT 5 + Sparkplug B** | Heartbeats, telemetry, commands, model-update notifications. |
| Server ↔ Edge (bulk) | HTTP (pull) | Large binaries (model bundles, software updates) — MQTT only signals availability. |
| Edge ↔ Edge | None (via server) | Edges do not talk to each other. |

---

## 3. Bricks (modules)

| # | Brick | Surface | Language | Responsibility |
|---|---|---|---|---|
| B1 | **Acquisition** | Edge | Python | Camera capture (GenICam via Harvester, RTSP, file), buffering, line sync. |
| B2 | **Dataset & Model Registry** | Server | Python | Versioned datasets + model registry with approval workflow. |
| B3 | **Training** | Workstation | Python + Tauri | PyTorch training recipes, MLflow tracking, ONNX export to registry. |
| B4 | **Serving** | Edge | Python | ONNX Runtime inference (stream + batch), version manager. |
| B5 | **Edge Fleet Manager** | Server | Python | Edge catalog, health (Sparkplug B), OTA updates, configs. |
| B6 | **Observability** | All | Python + Grafana | Metrics, logs, traces, drift detection, KPIs. |
| B7 | **Project / Workflow** | Server | Python | Projects, lines, tasks, campaigns, RBAC, audit trail. |
| B8 | **API Gateway** | Server | Python | REST/gRPC entrypoint, auth, routing. |
| B9 | **UI** | Server + Workstation | React/TS | Webapp (server) + Tauri app (workstation), shared components. |
| B10 | **Platform** | Server | Infra | Postgres, Mosquitto, Redis, Keycloak, Traefik, SMB shares. |

### Shared libraries (`libs/`)

These are pip-installable packages consumed by the services:

| Library | Purpose |
|---|---|
| `libs/core-py` | Exceptions, common types, configuration, structured logging. |
| `libs/storage` | Storage backend abstraction: `SmbProtocol` (default), `SmbMount`, `LocalFS`, `S3`. |
| `libs/obs-py` | OpenTelemetry wrapper + Vulis-specific metrics (`vulis.*`). |
| `libs/proto` | Protobuf schemas + generated code for gRPC. |
| `libs/schemas` | SQLAlchemy base models + Alembic migrations shared across services. |

---

## 4. Key technical decisions

The full rationale for each lives in the [ADRs](./ADR/). Quick reference:

| Topic | Decision | ADR |
|---|---|---|
| License | BSL 1.1 → AGPL-3.0 on 2030-06-14 | [0001](./ADR/0001-license.md) |
| Repository layout | Modular monorepo | [0002](./ADR/0002-monorepo.md) |
| Stack | Python-first, Rust for Tauri only | [0003](./ADR/0003-stack-python-first.md) |
| Edge ↔ server bus | MQTT 5 + Sparkplug B (Mosquitto) | [0004](./ADR/0004-mqtt-sparkplug.md) |
| Topology | Three surfaces (workstation/server/edge) | [0005](./ADR/0005-topology-3-surfaces.md) |
| Storage | Backend abstraction, SMB default via `smbprotocol` | [0006](./ADR/0006-storage-abstraction.md) |
| Air-gap relay | Workstation relays external artifacts to server | [0007](./ADR/0007-air-gap-relay.md) |
| Edge fleet | Centralized manager, OTA via MQTT signal + HTTP pull | [0008](./ADR/0008-edge-fleet.md) |
| Code management | Trunk-based + independent SemVer + changesets | [0009](./ADR/0009-code-management.md) |
| Air-gap git mirror | Local mirror on server for offline rebuild | [0010](./ADR/0010-air-gap-git-mirror.md) |

---

## 5. Storage model

All file access in Vulis goes through `libs/storage`'s `StorageBackend`
interface. Never call `open()` directly on a path that should live in shared
storage.

```
StorageBackend (abstract)
├── SmbProtocolBackend   ← default: pure-Python smbprotocol, no OS mount
├── SmbMountBackend      ← optional perf: relies on OS-level SMB mount
├── LocalFSBackend       ← dev, tests
└── S3Backend            ← future scalability (MinIO or cloud S3)
```

Conceptually, storage holds two kinds of objects:

- **Blobs**: opaque binary content-addressed files (images, model artifacts,
  experiment outputs). Addressed by hash. Deduplicated.
- **Manifests**: JSON documents (dataset versions, model cards) stored in
  Postgres, referencing blobs by hash. The source of truth for versioning.

This mirrors a DVC-like model and makes datasets/models reproducible and
diffable across versions.

---

## 6. Data model (high level)

Detailed schemas live with each service and in `libs/schemas`. Conceptually:

```
Tenant (Keycloak realm)
└── Project
    ├── Line(s)         # physical production line, maps to edge node(s)
    ├── Task(s)         # one vision task = one model slot
    │     (detection | classification | segmentation)
    ├── Campaign(s)     # data collection | validation | pilot | A/B
    ├── DatasetVersions # from B2
    ├── ModelVersions   # from B2 registry
    ├── Runs            # from B3 training (MLflow link)
    └── Deployments     # model version live on a line at time T
```

Every state-changing operation is recorded in an **append-only audit trail**
(actor, action, target, diff, timestamp). The trail is the foundation for
industrial compliance (ISO / GxP / FDA) without forcing a heavy process.

---

## 7. Security

- **Identity:** Keycloak (OIDC), multi-tenant via realms.
- **Authorization:** RBAC. Roles per project: admin, data-scientist,
  annotator, operator, reviewer.
- **Transport:** TLS everywhere (server has internal CA for edge nodes).
- **Secrets:** stored outside git, injected via environment or a vault.
- **Air-gap:** no outbound network from server or edge. Software/model
  updates are explicitly relayed by the workstation (see ADR 0007).

---

## 8. Observability

| Signal | Tool |
|---|---|
| Metrics | Prometheus + custom `vulis.*` metrics |
| Logs | Loki (structured, via OpenTelemetry/logs driver) |
| Traces | OpenTelemetry → Tempo (or local OTLP collector) |
| Dashboards | Grafana (infra) + custom Vulis dashboards (ML KPIs) |
| Drift (tabular) | Evidently |
| Drift (visual) | custom — see B6 roadmap (M6) |

Every service emits OTel traces with consistent attributes
(`vulis.project_id`, `vulis.line_id`, `vulis.model_version`).

---

## 9. Development lifecycle

See [CONTRIBUTING.md](./CONTRIBUTING.md). Summary:

- Trunk-based, Conventional Commits, DCO.
- PRs required; CI runs ruff, mypy, pytest, reuse, on Linux + Windows.
- Independent SemVer per package; platform baseline tags `vulis-YYYY.MM`.
- Releases on demand.
- ADRs for non-trivial decisions.

---

## 10. Roadmap

See the README [roadmap table](./README.md#roadmap). Current focus: **M1 —
foundations + dataset/registry**.

---

## 11. References

- [ADR index](./ADR/README.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [GOVERNANCE.md](./GOVERNANCE.md)
- [LICENSE](./LICENSE)
- [NOTICE](./NOTICE)
