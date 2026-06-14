# 0008. Edge fleet manager with OTA updates

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Multiple edge nodes (PCs with cameras + GPU) run acquisition and serving.
They are air-gap, reachable only via the server, and must be kept in sync:
software versions, model versions, configuration. The maintainer needs to
roll out updates from the server without physically visiting each line.

## Decision drivers

- Centralized control from the server.
- Robust to intermittent edge connectivity.
- Atomic, reversible updates (roll back if a model misbehaves).
- Support both **bare-metal** and **Docker** edge runtimes.
- No internet on edges — updates must come from the server's depot.

## Considered options

### Option A: Ansible / configuration management

- Pros: mature, declarative.
- Cons: requires the server to SSH into edges (push topology only); heavy
  dependency; not designed for the MQTT/Sparkplug B vocabulary we already
  have.

### Option B: Kubernetes (k8s) on edge

- Pros: industry-grade orchestration.
- Cons: rejected at this stage — too heavy per edge node, k8s-on-Windows-edge
  is awkward, and the maintainer chose bare-metal-or-Docker runtimes.

### Option C: Custom fleet manager over MQTT + HTTP (chosen)

A server-side service (`services/fleet/`) that:

- Maintains the **edge catalog** (id, capabilities, current versions,
  last-seen).
- Subscribes to Sparkplug B birth/death certificates → live health and
  discovery (see [ADR 0004](./0004-mqtt-sparkplug.md)).
- Publishes **update intents** ("edge X should run model Y v3") as retained
  MQTT messages → desired state.
- When an edge notifies it needs an artifact, signals availability over MQTT
  and the edge **pulls** the binary over HTTP from the server's Artifact
  Depot (see [ADR 0007](./0007-air-gap-relay.md)).
- Verifies signature and hash on the edge before applying.
- Supports blue-green / canary rollouts per line.

## Decision

**Adopt Option C.** `services/fleet/` is the single owner of edge state.
Edges are autonomous clients that:

1. On boot, publish a Sparkplug B birth certificate + current versions.
2. Subscribe to their command and update topics.
3. Pull advertised binaries from the depot over HTTP, verify, apply.
4. Report new versions + heartbeat via Sparkplug B.

The runtime (bare-metal process vs. Docker container) is abstracted behind
a small **edge agent** interface: the fleet manager emits intents; the agent
implements them for its runtime. Both runtimes are supported from day one.

## Rationale

Building on the MQTT/Sparkplug B infrastructure already chosen, the fleet
manager is a natural server-side component. The "intent + edge pull" pattern
works whether the server can push to edges or not, and gives us free
retry/resume (an edge that was offline catches up on reconnect via retained
messages and the depot).

## Consequences

- **Positive:** centralized version control for edges; rollback via prior
  intent; works in pull-only topology; runtime-agnostic via the edge agent.
- **Negative:** we own the fleet manager (vs. adopting k8s/Ansible); we must
  be disciplined about the desired-state vs. reported-state model.
- **Neutral:** the edge agent is a small per-host daemon; bare-metal and
  Docker variants ship together.

## Interface sketch

```bash
# Server-side:
vulis fleet list                       # show edges + reported state
vulis fleet deploy --line 3 --model mydet:v3 --strategy canary
# Edge-side (agent):
vulis edge agent run                   # boots, subscribes, pulls, applies
```

## Risks & mitigations

- *Risk:* a bad update bricks an edge. *Mitigation:* every apply keeps the
  previous version; the agent auto-rolls back if the new version fails its
  readiness check (heartbeat + a sanity inference).
- *Risk:* divergent runtime behavior (Docker vs bare-metal). *Mitigation:*
  the agent interface is minimal and fully tested for both runtimes.
- *Risk:* large model bundle transfer stalls. *Mitigation:* HTTP range
  requests + resume; MQTT only signals.

## Compliance

Fleet operations are recorded in the audit trail (who deployed what, when,
to which line, with which strategy).

## References

- [ADR 0004](./0004-mqtt-sparkplug.md) — transport for health + intents.
- [ADR 0007](./0007-air-gap-relay.md) — Artifact Depot source.
- [ARCHITECTURE.md §3 B5](../ARCHITECTURE.md).
