# 0005. Deployment topology: three surfaces

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis is deployed in a constrained industrial environment:

- A **Windows server** acts as the central node. It has **no GPU** and serves
  as the bridge to edge nodes. It holds the central SMB file shares.
- **Edge nodes** (one or more per production line) have GPUs and cameras.
  They are **air-gap** (no internet) and only reachable via the server.
- A **workstation** (the engineer's PC) has a GPU and internet access via a
  proxy. It is the only machine that can reach the outside world.

The maintainer trains models locally and pushes results to the server; the
server redistributes to edges.

## Decision drivers

- Compute must happen where the GPUs are: workstation for training, edge for
  inference.
- The server cannot host compute (no GPU).
- Edge nodes are network-isolated; only the server can reach them.
- Only the workstation has internet (air-gap for server and edge).
- Storage is centralized on Windows SMB shares.

## Considered options

### Option A: Single-surface (everything on the server)

Rejected: the server has no GPU; cannot train or infer.

### Option B: Two-surface (workstation + edge)

The workstation would push directly to edges. Rejected: the workstation
cannot reach edge nodes on this network; only the server can.

### Option C: Three-surface (chosen)

Workstation, server, edge. Each has a clear responsibility:

- **Workstation** → training, dataset preparation, air-gap relay, desktop UI.
- **Server** → control plane (metadata, registry, fleet manager, webapp),
  central storage, MQTT broker.
- **Edge** → acquisition, inference (serving), telemetry source.

### Option D: Cloud-hosted control plane

Rejected by the air-gap requirement.

## Decision

**Adopt the three-surface topology** described in
[ARCHITECTURE.md §2](../ARCHITECTURE.md).

- **The server never computes.** It is a pure control plane + storage hub.
- **The workstation relays external artifacts** (wheels, Docker images,
  model backbones) into the air-gap (see [ADR 0007](./0007-air-gap-relay.md)).
- **Edges are clients** of the server (MQTT + HTTP pull), so the design works
  whether or not the server can initiate connections to them.

## Rationale

This is not really a *choice* — it is dictated by the deployment constraints.
The architecture's job is to make the separation explicit and keep each
surface's responsibilities tight, so each can be replaced or scaled
independently (e.g. add more edges, add a second workstation, later host the
control plane on a beefier Linux box).

## Consequences

- **Positive:** clear ownership of compute vs control vs storage; the server
  stays lightweight and stable; edges remain swappable.
- **Negative:** more moving parts (three deploy targets); the workstation
  must be online for training and for relaying external updates.
- **Neutral:** MLOps tooling must be aware of "where does this run?"
  (training always on a workstation-class GPU, never on the server).

## Risks & mitigations

- *Risk:* workstation is a bottleneck for training and updates. *Mitigation:*
  multiple workstations can be registered; the relay and training sidecars
  are stateless w.r.t. the server.
- *Risk:* server single point of failure for the fleet. *Mitigation:*
  documented; HA Mosquitto and Postgres replicas are possible later.

## Compliance

Brick-to-surface mapping in [ARCHITECTURE.md §3](../ARCHITECTURE.md).

## References

- [ADR 0007](./0007-air-gap-relay.md) — air-gap relay via workstation.
- [ADR 0008](./0008-edge-fleet.md) — edge fleet management.
- [ADR 0010](./0010-air-gap-git-mirror.md) — git mirror for offline rebuild.
