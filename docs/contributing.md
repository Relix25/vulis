# Contributing

The canonical contributing guide lives at the repository root:
[../CONTRIBUTING.md](../CONTRIBUTING.md).

Highlights:

- Trunk-based development, Conventional Commits, DCO sign-off on every commit.
- PRs required; CI runs on Linux + Windows.
- `task check` runs the full local gate (ruff, mypy, pytest, reuse).
- ADRs required for non-trivial decisions; copy `ADR/0000-template.md`.
- Changesets in `changes/` for any change touching a releasable package.
