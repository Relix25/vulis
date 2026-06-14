# Core concepts

> Stub — to be expanded during M1.

## Surfaces

Vulis distinguishes three deployment surfaces (see
[ADR 0005](../../ADR/0005-topology-3-surfaces.md)):

| Surface | Where | Role |
|---|---|---|
| **Workstation** | Engineer's PC | Training, dataset prep, air-gap relay, desktop UI (Tauri). |
| **Server** | Central Windows host | Control plane (metadata, registry, fleet, webapp), storage, MQTT broker. |
| **Edge** | Per-line IPC | Acquisition, inference, telemetry. |

## Core entities

| Entity | Meaning |
|---|---|
| **Project** | A vision-inspection initiative (e.g. "defect detection on part X line 3"). |
| **Line** | A physical production line → maps to one or more edge nodes. |
| **Task** | A vision task on a project: detection, classification, or segmentation. |
| **Dataset / DatasetVersion** | A versioned collection of labeled images. Immutable once published. |
| **Model / ModelVersion** | A versioned model artifact (ONNX). Linked to a DatasetVersion and Task. |
| **Deployment** | A specific ModelVersion live on a Line at a given time. |
| **Campaign** | A data-collection, validation, pilot, or A/B operation. |
| **Audit event** | An immutable record of a state-changing action. |

## Storage model

All binary blobs (images, model artifacts, training outputs) are
content-addressed and accessed through the `libs/storage` abstraction — never
via direct filesystem paths in service code. See
[ADR 0006](../../ADR/0006-storage-abstraction.md).

## Communication

- **Edge ↔ Server**: MQTT 5 + Sparkplug B (heartbeats, telemetry, commands,
  update notifications). Large binaries are pulled over HTTP from the server.
- **Workstation ↔ Server**: HTTPS (REST/gRPC) + SMB shares.
