# Vulis documentation

Welcome to the Vulis documentation. Vulis is an end-to-end, air-gap-ready,
source-available platform for deploying and operating computer-vision
inspection on industrial production lines.

## Where to start

- **New here?** Read [Getting started → Concepts](./getting-started/concepts.md).
- **Want to run it?** Follow the [Quick start](./getting-started/quick-start.md).
- **Want the big picture?** Read the [Architecture](./architecture.md).
- **Wondering why a decision was made?** Browse the
  [Architecture Decision Records](./adr/index.md).
- **Want to contribute?** See the [Contributing guide](./contributing.md).

## At a glance

| | |
|---|---|
| **License** | BSL 1.1 → AGPL-3.0 on 2030-06-14 — see [Licensing](./licensing.md). |
| **Stack** | Python-first, Rust for the Tauri desktop app only. |
| **Topology** | Three surfaces: workstation · server · edge. |
| **Transport** | MQTT 5 + Sparkplug B (edge ↔ server), HTTPS + SMB (workstation ↔ server). |
| **Status** | Pre-1.0, M1 (foundations) in progress. |

## Project status

Vulis is under active development and not yet production-ready. The current
focus is **M1 — foundations**: storage abstraction, dataset versioning, model
registry, project/workflow API, and the edge fleet skeleton.
