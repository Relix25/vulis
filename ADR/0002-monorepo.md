# 0002. Repository layout: modular monorepo

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis is composed of ~10 functional bricks plus shared libraries, in two
languages (Python mostly, Rust/TS for the Tauri/web apps). We must decide
between one repository (monorepo) or many (multi-repo), and if monorepo,
how to keep the bricks independently buildable and releasable.

## Decision drivers

- Cross-brick consistency (shared types, protocols, migrations).
- Atomic refactors across bricks (e.g. rename a shared type).
- Simple contributor onboarding (one clone, one tooling).
- Independent releases per brick (SemVer per package).
- Long-term option to extract a brick into its own repo if useful.

## Considered options

### Option A: Multi-repo (one repo per brick)

- Pros: strict isolation; independent CI naturally; easy per-brick ACLs.
- Cons: cross-repo refactors are painful; version skew; many repos to
  bootstrap; harder for a single contributor to keep everything coherent.

### Option B: Single monorepo, single version for everything

- Pros: simplest mental model; one release.
- Cons: tight coupling — a docs tweak bumps every brick; no independent
  SemVer; doesn't fit a system where libs/services evolve at different speeds.

### Option C: Modular monorepo (chosen)

One repo, but each package under `libs/`, `services/`, `apps/`, `tools/`
has its own manifest (`pyproject.toml`, `Cargo.toml`, `package.json`), its
own SemVer, and its own CI job. Cross-package dependencies are declared
explicitly.

- Pros: shared history + atomic refactors, while preserving independent
  versioning and releases. Each package is usable in isolation.
- Cons: tooling must be aware of the layout (CI matrix, changeset tooling,
  a release script).

### Option D: Monorepo with a build system (Nx / Turbo / Bazel)

- Pros: top-tier incremental builds, caching, dependency graphs.
- Cons: heavy tooling overhead; premature at this stage.

## Decision

**Option C — modular monorepo**, without a heavy build system. Cross-package
dependency tracking is handled by:

- Python: per-package `pyproject.toml` with local path dependencies (uv
  workspace). The top-level `uv.lock` pins everything.
- TypeScript: pnpm workspaces.
- Rust: a Cargo workspace under `apps/tauri-app/`.

A platform **baseline tag** (`vulis-YYYY.MM`) marks a coherent, tested
snapshot of all packages, even though each package can also be tagged and
released independently.

## Rationale

For a single-maintainer project with many tightly related components, the
modular monorepo maximizes coherence while keeping the door open to later
extraction. The "no heavy build system" choice avoids premature complexity;
we can adopt Nx/Turbo if/when CI times justify it.

## Consequences

- **Positive:** atomic cross-brick changes; consistent tooling; one place for
  issues/PRs/ADRs; one `uv.lock`/`pnpm-lock.yaml` for reproducibility.
- **Negative:** CI must be matrix-aware; release tooling (`tools/release/`)
  must read a `changes/` folder to bump per-package versions.
- **Neutral:** each package retains its own version and changelog.

## Compliance

The layout is documented in [ARCHITECTURE.md §3](../ARCHITECTURE.md) and the
[README](../README.md). Per-package READMEs describe scope and API.

## References

- [tools/release/](../tools/release/) — per-package SemVer bump + changelog.
- [ADR 0009](./0009-code-management.md) — versioning & branching strategy.
