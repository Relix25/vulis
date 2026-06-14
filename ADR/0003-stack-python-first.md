# 0003. Stack: Python-first, Rust for Tauri only

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis needs to implement many roles: ML training, ML inference, an HTTP/gRPC
gateway, acquisition drivers, observability, a CLI, and a desktop application.
The maintainer is most fluent in Python. A previous iteration considered
Python + Go for performance-critical parts.

## Decision drivers

- **Maintainer expertise:** Python is the strongest language; minimizing
  context switching matters more than raw throughput at this stage.
- **ML ecosystem:** PyTorch, ONNX Runtime, anomalib, smp, timm, OpenCV are
  Python-first.
- **Cross-platform parity:** must run identically on Linux (edge) and Windows
  (server / workstation).
- **Air-gap & deployment simplicity:** fewer runtimes = simpler packaging
  and fewer failure modes.
- **Performance-critical paths:** a few (capture zero-copy, batched serving)
  may need a faster language later.

## Considered options

### Option A: Python + Go (gateway/ingestion in Go)

- Pros: Go gives excellent concurrency and a single static binary for the
  gateway/ingestion; mature for high-throughput networking.
- Cons: two runtimes to package and learn; Go brings little to ML; the
  perf gains are not yet needed at M1.

### Option B: Pure Python everywhere

- Pros: one runtime, fastest iteration, broadest library coverage, trivial
  packaging (wheels).
- Cons: GIL limits CPU-bound parallelism; capture/serving hot paths may need
  optimization later.

### Option C: Python + Rust (only where required)

Python for all services, ML, gateway, acquisition, CLI. Rust **only** for the
Tauri desktop app backend (which mandates Rust anyway), and potentially later
for one or two hot-path modules (called via PyO3 if profiling justifies it).

- Pros: maximizes iteration speed; single backend runtime; Rust remains a
  surgical tool, not a pervasive dependency.
- Cons: some Python hot paths may eventually need a Rust rewrite (acceptable,
  and PyO3 makes it incremental).

### Option D: polyglot (Go + Rust + Python + ...)

- Cons: maximal operational and cognitive cost; rejected.

## Decision

**Option C — Python-first, Rust only where required.**

- All services, libraries, CLI, ML training/serving/acquisition: **Python**.
- Desktop application (`apps/tauri-app/`): **Rust backend + TypeScript
  frontend** (imposed by Tauri).
- If profiling later proves a Python hot path insufficient, rewrite that
  specific module in Rust and bind via PyO3. Do not adopt a second backend
  language speculatively.

## Rationale

At M1, throughput is not the bottleneck — correctness, audit trail, and
reproducibility are. Python's ecosystem, the maintainer's fluency, and the
simpler air-gap packaging (single runtime) outweigh Go's performance edge,
which we do not yet need. Tauri is the only Rust surface, and its scope is
strictly the desktop shell that launches Python sidecars.

## Consequences

- **Positive:** one backend runtime to package, install, and audit; easiest
  onboarding; full ML ecosystem natively.
- **Negative:** GIL may require multi-process patterns (e.g. ONNX Runtime
  data parallelism via separate processes, not threads) — this is well
  understood and acceptable.
- **Neutral:** a future Rust PyO3 module is possible but localized; it does
  not change the overall architecture.

## Risks & mitigations

- *Risk:* a Python hot path becomes a bottleneck. *Mitigation:* measure first
  (OTel profiling); rewrite locally with PyO3 if needed; no global rewrite.
- *Risk:* ONNX Runtime threading under the GIL. *Mitigation:* ONNX Runtime
  releases the GIL during inference; batching uses separate worker processes.

## Compliance

Tooling (`ruff`, `mypy` strict on `libs/`, `pytest`) is documented in
[CONTRIBUTING.md §4](../CONTRIBUTING.md). CI runs tests on Linux and Windows.

## References

- [ARCHITECTURE.md §3](../ARCHITECTURE.md) — per-brick language map.
