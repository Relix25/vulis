## Summary

Brief description of what this PR changes and why.

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (would require existing users to change something)
- [ ] Refactor / chore
- [ ] Documentation

## Scope

Which package(s) / brick(s) are affected:
- [ ] `libs/` (which: core-py / storage / obs-py / proto / schemas)
- [ ] `services/` (which)
- [ ] `apps/` (web / tauri-app)
- [ ] `tools/` (cli / release)
- [ ] CI / infra / docs

## Checklist

- [ ] Commits follow **Conventional Commits** with the right scope.
- [ ] Every commit is **signed off** (`-s`, DCO).
- [ ] `ruff check` and `ruff format --check` pass.
- [ ] `mypy` passes on touched `libs/` packages.
- [ ] Tests added/updated; `pytest` passes on Linux + Windows.
- [ ] License headers present on new files (`reuse lint` passes).
- [ ] A changeset was added in `changes/` if a releasable package changed.
- [ ] An ADR was added/updated if this is a non-trivial architectural change.
- [ ] Public API or behavior change documented.

## Related issues

Closes #NNN (or: Refs #NNN).

## Notes for reviewers

Anything specific reviewers should pay attention to.
