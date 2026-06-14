# Vulis

**Industrial computer-vision platform — modular, air-gap-ready, open source.**

Vulis is an end-to-end platform for deploying and operating computer-vision
inspection on industrial production lines: defect detection, classification,
and segmentation. It is designed for **on-premise** deployment, with an
explicit three-surface topology (workstation / server / edge), strict
**air-gap** support, and SMB-based shared storage.

> **Status:** early development (M1 — foundations). Not production-ready.
> See [ARCHITECTURE.md](./ARCHITECTURE.md) and the [ADR index](./ADR/README.md)
> for the current design.

---

## Why Vulis?

| Concern | Vulis' answer |
|---|---|
| **Air-gap** | Runs entirely offline. A workstation relays external artifacts (Python wheels, Docker images, model backbones) to a central server, which redistributes them to edge nodes. |
| **Industrial network** | Edge nodes live behind a central Windows server; they communicate with it via **MQTT 5 + Sparkplug B**, supporting both pull and push topologies. |
| **Compute placement** | The server never computes — it is the control plane. Training runs on the workstation GPU, inference on the edge GPU. |
| **Storage** | Central Windows SMB shares, accessed via `smbprotocol` (pure Python, no OS-level mount required) — Linux and Windows alike. |
| **Multi-task vision** | Detection, classification, and segmentation are first-class citizens, each with its own training recipe and model-card template. |
| **Governance** | Append-only audit trail, role-based access control, model approval workflow (`draft → review → staging → approved → deployed → archived`). |
| **Open source** | Source-available under **BSL 1.1**, converting to **AGPL-3.0** on 2030-06-14. Free for internal use; resale/competing-SaaS requires a commercial license. |

---

## Architecture in one picture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Workstation    │     │   Server (Win)   │     │   Edge ×N (GPU)  │
│  (train, GPU,    │     │  control plane,  │     │  inference,      │
│   internet)      │     │  air-gap, SMB    │     │  cameras,        │
│   App Tauri      │     │  Webapp + APIs   │     │  air-gap         │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │       LAN (proxy-aware)        MQTT 5 + Sparkplug B
         └────────────────────────────────┴─────────────────────┘
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full picture.

---

## Repository layout

```
vulis/
├── libs/        # Shared, pip-installable Python libraries
│   ├── core-py/   # exceptions, types, config, logging
│   ├── storage/   # storage backend abstraction (SMB / LocalFS / S3)
│   ├── obs-py/    # OpenTelemetry wrapper + Vulis metrics
│   ├── proto/     # gRPC/protobuf schemas + codegen
│   └── schemas/   # Alembic migrations shared across services
├── services/    # One folder per brick (acquisition, dataset, registry, ...)
├── apps/        # web/ (server webapp) + tauri-app/ (workstation)
├── tools/       # vulis-cli + release tooling
├── docker/      # Dockerfiles + compose files (dev, platform, edge)
├── ADR/         # Architecture Decision Records
└── docs/        # MkDocs Material site
```

---

## Quick start (development)

> Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/),
> [Task](https://taskfile.dev), Docker (or a `docker`-compatible runtime).

```bash
# 1. Clone
git clone https://github.com/vulis/vulis.git
cd vulis

# 2. Install dev dependencies (all libs)
task install

# 3. Bring up the local dev stack (Postgres, Mosquitto, Redis, Keycloak)
task up

# 4. Run the test suite
task test
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full development workflow.

---

## Licensing

Vulis is licensed under the **Business Source License 1.1** (BSL 1.1). In
plain terms, until **2030-06-14**:

- ✅ You may use Vulis internally, including in production on your own lines.
- ✅ You may modify it, fork it, run it for evaluation, research, and testing.
- ❌ You may not resell it or offer it as a hosted service that competes with
  Vulis, without a commercial license.

On 2030-06-14, Vulis automatically becomes available under the
**GNU AGPL-3.0** license.

See [LICENSE](./LICENSE) for the full text and [NOTICE](./NOTICE) for
third-party attributions.

---

## Contributing

Contributions are welcome. Please read:

- [CONTRIBUTING.md](./CONTRIBUTING.md) — development setup, conventions, DCO.
- [GOVERNANCE.md](./GOVERNANCE.md) — project governance and roles.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — system architecture.
- [ADR/](./ADR/) — architecture decision records.

All contributions require a **Developer Certificate of Origin** sign-off
(`Signed-off-by:`), see CONTRIBUTING.md.

---

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| **M1** | Foundations: storage, dataset, model registry, project API, fleet skeleton | 🚧 in progress |
| M2 | Training (PyTorch recipes, MLflow tracking, ONNX export) | planned |
| M3 | Acquisition (camera drivers, GenICam/RTSP) | planned |
| M4 | Serving (ONNX Runtime, stream + batch, version manager) | planned |
| M5 | Deploy & Fleet OTA (signed bundles, blue-green) | planned |
| M6 | Observability & drift (Grafana, visual + tabular drift) | planned |
| M7 | Active learning loop | planned |
| M8 | CVAT integration | planned |
| M9 | Industrialization (multi-tenant, OPC-UA/MQTT adapters) | planned |

---

## Contact

- **Issues:** <https://github.com/vulis/vulis/issues>
- **Commercial licensing:** open an issue labeled `licensing`.
