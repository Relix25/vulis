# 0007. Air-gap relay via the workstation

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

In the deployment (see [ADR 0005](./0005-topology-3-surfaces.md)), only the
**workstation** has internet access (via a proxy). The server and edges are
air-gap. Anything coming from the outside — Python wheels, Docker images,
pretrained model backbones (timm, anomalib), CVAT containers — must cross
the air-gap somehow.

## Decision drivers

- Server and edges must stay air-gap.
- The workstation is the only internet-connected machine.
- Reproducibility: the relayed artifacts must be exactly what was downloaded
  (no silent mutation).
- Forward distribution: once on the server, artifacts must reach edges too.

## Considered options

### Option A: Manual copy

Operator downloads wheels on the workstation, copies them via SMB to the
server, then to edges manually.

- Pros: zero tooling.
- Cons: error-prone, non-reproducible, no integrity check, scales badly.

### Option B: Reverse proxy / mirror on the server with outbound access

Rejected: violates the air-gap constraint on the server.

### Option C: Automated relay command (`vulis relay sync`) (chosen)

A dedicated CLI subcommand, run **on the workstation**, that:

1. Resolves all declared dependencies (Python wheels for Linux *and*
   Windows, Docker images as tarballs, model backbone weights, vendored
   datasets) — using the workstation's internet + proxy.
2. Downloads them into a local staging directory.
3. Computes hashes (SHA-256) and signs the bundle (cosign or a project key).
4. Pushes the signed bundle to the server's **Artifact Depot** (a versioned
   directory on the SMB share, tracked in Postgres).
5. The server then redistributes to edges via the fleet manager (see
   [ADR 0008](./0008-edge-fleet.md)): MQTT signals an update, edges pull the
   binary over HTTP.

### Option D: Sneakernet with offline media

Operator carries a USB drive between internet-connected PC and server.

- Pros: maximum isolation.
- Cons: not needed here (workstation has LAN access to the server).

## Decision

**Adopt Option C** — `vulis relay sync` is the canonical way to bring
external artifacts into the air-gap. The server exposes an Artifact Depot
that the relay populates and the fleet manager consumes.

## Rationale

A dedicated command makes the air-gap workflow reproducible, signed, and
auditable. It removes a whole class of operational mistakes ("which wheel
did I copy? was it the Linux or Windows one?"). The Linux/Windows matrix is
handled in one pass because edges run Linux while server/workstation run
Windows.

## Consequences

- **Positive:** reproducible artifact sets; integrity via hashes + signatures;
  single command to cross the air-gap.
- **Negative:** the workstation must be online and have proxy access for
  `relay sync` to work.
- **Neutral:** the Artifact Depot is a first-class object (versioned, listed
  in the webapp, with retention policy).

## Interface sketch

```bash
# On the workstation (has internet via proxy):
vulis relay sync                       # resolve + download + sign
vulis relay push                       # upload to server depot
# On the server:
vulis fleet update --depot-version 42  # redistribute to edges
```

## Risks & mitigations

- *Risk:* a needed artifact is missing from the bundle. *Mitigation:* `relay
  sync` resolves from a manifest declared per package; missing items fail
  fast with a clear error.
- *Risk:* tampered artifact. *Mitigation:* signature verification on both
  the server depot and on the edge before installation.
- *Risk:* proxy blocks large downloads (Docker images, backbones).
  *Mitigation:* chunked download + resume; documented proxy configuration.

## Compliance

The Artifact Depot and relay commands are part of `tools/vulis-cli/`. The
fingerprint of every relayed artifact is recorded in the audit trail.

## References

- [ADR 0008](./0008-edge-fleet.md) — fleet manager consumes the depot.
- [ADR 0010](./0010-air-gap-git-mirror.md) — git mirror uses the same relay.
