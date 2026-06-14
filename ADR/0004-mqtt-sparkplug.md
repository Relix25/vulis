# 0004. Edge ↔ server bus: MQTT 5 + Sparkplug B

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

The server must communicate with N edge nodes (PCs with cameras, behind the
server on the plant LAN). Two topologies must both be supported, since the
maintainer is not yet sure which will be available on every site:

- **Pull:** edge nodes can open a connection to the server (edge = client).
- **Push:** the server can also initiate requests toward edges.

The bus carries heartbeats, telemetry, commands, model-update notifications,
and (signaling for) large binary transfers.

## Decision drivers

- Industrial ecosystem alignment (future OPC-UA / SCADA integration).
- Robustness to intermittent connectivity (edge reboots, network hiccups).
- Automatic edge discovery and liveness detection.
- Both pull and push modes.
- Lightweight enough for a Windows server without GPU.

## Considered options

### Option A: NATS JetStream

Lightweight, persistent streams, good ergonomics.

- Pros: simple to operate, fast, built-in persistence and replay.
- Cons: not the industrial standard; future IIoT integrations would still
  need MQTT/OPC-UA on top.

### Option B: Kafka

- Pros: industry standard for high-volume streaming.
- Cons: operationally heavy (Zookeeper/KRaft, JVM, tuning); overkill for
  edge heartbeat/command volumes; poor fit for a single Windows server.

### Option C: gRPC bidirectional streaming

- Pros: typed, performant, no extra broker.
- Cons: requires the server to reach each edge directly (push topology),
  which we cannot always guarantee; no built-in liveness/discovery; no
  retained messages.

### Option D: MQTT 5 + Sparkplug B (chosen)

MQTT 5 with the Sparkplug B specification on top.

- Pros:
  - **De-facto IIoT standard** — future PLC / SCADA / OPC-UA bridges speak
    MQTT natively.
  - **QoS + persistent sessions** — guaranteed delivery of commands even if
    an edge was offline when sent.
  - **Retained messages** — the desired state ("edge X should run model Y
    v3") is always available to a reconnecting edge.
  - **Last Will & Testament + Sparkplug B death certificates** — automatic,
    reliable edge offline detection.
  - **Sparkplug B birth certificates** — auto-discovery of edge nodes and
    their capabilities.
  - **Mosquitto** is a tiny single-binary broker that runs fine on Windows.
- Cons:
  - Sparkplug B adds some complexity (payload encoding, state management).
  - Not designed for large payloads — we use HTTP for big binaries.

## Decision

**Adopt MQTT 5 + Sparkplug B, brokered by Eclipse Mosquitto.**

- Mosquitto runs on the server.
- Each edge is an MQTT client with a persistent session.
- Edge telemetry and heartbeats follow Sparkplug B (so the fleet manager
  gets birth/death certificates and auto-discovery for free).
- High-level Vulis commands use a `vulis/...` topic namespace (still over
  MQTT 5), QoS 1, with persistent sessions.
- **Large binaries (model bundles, software updates) are never sent over
  MQTT.** The server publishes a small metadata message (size, hash, URL);
  the edge pulls the binary from the server over HTTP.

### Topic namespace (preliminary)

```
spBv1.0/Vulis/...                          Sparkplug B spec topics
vulis/edge/{id}/heartbeat                  QoS 1
vulis/edge/{id}/telemetry/...              QoS 0/1
vulis/edge/{id}/status                     QoS 1, retained
vulis/edge/{id}/cmd/+                      QoS 1, persistent session
vulis/edge/{id}/update/notify              QoS 1
vulis/registry/model/notify                QoS 1, retained
vulis/fleet/discovery                      QoS 1, retained
```

## Rationale

MQTT is the right default for industrial contexts: it matches the future
integration needs, handles intermittent connectivity gracefully, and
Mosquitto's footprint is negligible. Sparkplug B is adopted **from the
start** (per maintainer request) so birth/death certificates and discovery
are first-class, even at the cost of a slightly steeper initial setup.

## Consequences

- **Positive:** native IIoT vocabulary, robust liveness, retained desired
  state, future-proof for OPC-UA/SCADA.
- **Negative:** Sparkplug B payload encoding (Protocol Buffers) is required;
  we vendor a Python Sparkplug B client.
- **Neutral:** HTTP remains the channel for large binaries; the broker only
  signals.

## Risks & mitigations

- *Risk:* Mosquitto + Sparkplug B on Windows server. *Mitigation:* Mosquitto
  ships a Windows binary; we test persistent sessions and LWT in CI.
- *Risk:* broker is a SPOF. *Mitigation:* Mosquitto bridges can be added
  later for HA; for M1, a single broker is acceptable on the server.

## Compliance

Sparkplug B spec: <https://sparkplug.apache.org/specification/latest>
Mosquitto: <https://mosquitto.org/>

## References

- [ARCHITECTURE.md §2](../ARCHITECTURE.md) — communication summary.
- [ADR 0008](./0008-edge-fleet.md) — fleet manager uses Sparkplug B for
  health and OTA signaling.
