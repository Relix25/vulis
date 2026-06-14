# Architecture Decision Records (ADR)

An [ADR](https://adr.github.io/) is a short text document that captures a
single architectural decision: its context, the considered options, the
chosen solution, and its consequences.

- **Why?** So future maintainers (including future-you) understand *why* the
  code is shaped the way it is.
- **When?** Whenever a decision is non-trivial or hard to reverse: picking a
  dependency, choosing a protocol, defining a public API, splitting a service.
- **Where?** Here, numbered sequentially.

## Index

| # | Title | Status |
|---|---|---|
| [0000](./0000-template.md) | ADR template | — |
| [0001](./0001-license.md) | License: BSL 1.1 with 4-year Change Date → AGPL-3.0 | Accepted |
| [0002](./0002-monorepo.md) | Repository layout: modular monorepo | Accepted |
| [0003](./0003-stack-python-first.md) | Stack: Python-first, Rust for Tauri only | Accepted |
| [0004](./0004-mqtt-sparkplug.md) | Edge ↔ server bus: MQTT 5 + Sparkplug B | Accepted |
| [0005](./0005-topology-3-surfaces.md) | Deployment topology: three surfaces | Accepted |
| [0006](./0006-storage-abstraction.md) | Storage: backend abstraction, SMB default | Accepted |
| [0007](./0007-air-gap-relay.md) | Air-gap relay via the workstation | Accepted |
| [0008](./0008-edge-fleet.md) | Edge fleet manager with OTA updates | Accepted |
| [0009](./0009-code-management.md) | Code management: trunk-based + independent SemVer | Accepted |
| [0010](./0010-air-gap-git-mirror.md) | Air-gap git mirror on the server | Accepted |

## Process

1. Copy [`0000-template.md`](./0000-template.md), pick the next free number.
2. Fill it in. Status starts at `Proposed`.
3. Open a PR. Allow at least one week for feedback (see [GOVERNANCE.md](../GOVERNANCE.md)).
4. On merge, flip status to `Accepted`.
5. To supersede an ADR, write a new one referencing the old, then mark the old
   as `Superseded by 00NN`.

## Statuses

- **Proposed** — open for discussion.
- **Accepted** — adopted.
- **Deprecated** — no longer relevant.
- **Superseded** — replaced by a newer ADR.
