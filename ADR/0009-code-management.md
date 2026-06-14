# 0009. Code management: trunk-based + independent SemVer

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

The modular monorepo (see [ADR 0002](./0002-monorepo.md)) hosts many
packages that evolve at different speeds. We need a branching strategy, a
versioning scheme, and a release cadence that:

- Keep `main` always green and deployable.
- Allow packages to be released independently.
- Stay lightweight for a small team / solo maintainer.
- Produce clear changelogs.

## Decision drivers

- Simplicity for a solo / small team workflow.
- No long-lived diverging branches.
- Each package has its own SemVer and changelog.
- A tested, coherent snapshot of the whole platform is sometimes useful.

## Considered options

### Branching

| Option | Verdict |
|---|---|
| Git-flow (develop/release/hotfix/feature) | Too heavy for the team size; long-lived `develop` diverges. |
| GitHub flow (feature branches → main, continuous deploy) | Close, but we still want occasional release branches. |
| **Trunk-based** (short feature branches, squash-merge to main, optional release branches) | **Chosen.** Light, modern, fits the team. |

### Versioning

| Option | Verdict |
|---|---|
| Single version for the whole monorepo | Couples all packages; a docs tweak bumps everything. |
| Independent Git tags per package, no baseline | Loses the notion of a coherent platform snapshot. |
| **Independent SemVer per package + optional platform baseline tag `vulis-YYYY.MM`** | **Chosen.** Best of both. |

### Release cadence

| Option | Verdict |
|---|---|
| Calendar-based monthly release | Artificial pressure; forces half-baked features to wait or ship early. |
| Strict semantic per-commit release (every merge = release) | Noisy while pre-1.0. |
| **"Au fil de l'eau" (on demand, when a package is ready)** | **Chosen.** |

## Decision

**Branching:** trunk-based.

- `main` is always deployable and protected.
- Work happens on short-lived branches: `feat(scope): ...`,
  `fix(scope): ...`, `chore(scope): ...`, `docs(scope): ...`.
- PRs are required, even for the maintainer; squash-merge on approval +
  green CI.
- Optional `release/vulis-YYYY.MM` branches to stabilize a baseline, with
  cherry-picks from `main`.

**Commits:** [Conventional Commits](https://www.conventionalcommits.org/),
scope = package or area (`dataset`, `storage`, `core-py`, `ci`, `adr`, ...).

**Versioning:** each package under `libs/`, `services/`, `apps/`, `tools/`
carries its own SemVer in its manifest (`pyproject.toml` `version` field,
etc.). A `changes/` folder holds one changeset per PR describing the bump
type (`patch`/`minor`/`major`) and the user-facing note. The
`tools/release/` script consumes the changesets, bumps versions, generates
per-package `CHANGELOG.md`, tags the package (`<pkg>-vX.Y.Z`), and optionally
creates a platform baseline tag (`vulis-YYYY.MM`).

**Releases:** on demand. Anytime a package is ready, the maintainer runs the
release script for that package. A baseline tag is cut periodically when the
whole platform has been tested together.

## Rationale

Trunk-based minimizes merge pain and keeps history linear (squash-merge).
Independent SemVer matches the modular monorepo's premise — packages evolve
independently — while the baseline tag preserves the ability to say "this
exact combination is known-good". "Au fil de l'eau" avoids calendar pressure
and is the natural fit for a pre-1.0, solo-maintained project.

## Consequences

- **Positive:** linear history; per-package changelogs; no version skew
  ambiguity (lockfiles pin everything); clear release notes.
- **Negative:** the `changes/` folder discipline must be enforced (a CI check
  verifies a changeset exists for non-trivial PRs touching releasable
  packages).
- **Neutral:** tooling (`tools/release/`) is bespoke but small; can be
  replaced by [`changesets`](https://github.com/changesets/changesets) if
  the JS world converges.

## Risks & mitigations

- *Risk:* forgotten changeset → missing changelog entry. *Mitigation:* CI
  check on PRs that touch `libs/`/`services/`/`apps/`/`tools/` and lack a
  `changes/*.md` file (with an `area:` allowlist for docs-only changes).
- *Risk:* baseline tag drifts from per-package tags. *Mitigation:* the
  release script records the exact package versions in the baseline release
  notes.

## Compliance

- Branch protection rules enforced on GitHub.
- DCO enforced by the `dco` Action (see [CONTRIBUTING.md](../CONTRIBUTING.md)).
- Conventional Commit scopes listed in CONTRIBUTING.md §3.

## References

- [ADR 0002](./0002-monorepo.md) — repository layout.
- [ADR 0010](./0010-air-gap-git-mirror.md) — git mirror for air-gap.
- [Trunk-based development](https://trunkbaseddevelopment.com/)
