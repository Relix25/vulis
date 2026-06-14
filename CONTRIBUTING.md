# Contributing to Vulis

First of all, thank you for considering a contribution to Vulis. This document
describes how to set up your environment, the conventions we follow, and the
process for getting changes merged.

> **TL;DR:** trunk-based development, conventional commits, DCO sign-off,
> PRs required, tests must pass on Linux + Windows.

---

## 1. Licensing & DCO

Vulis is licensed under the [Business Source License 1.1](./LICENSE),
converting to AGPL-3.0 on 2030-06-14. By contributing, you agree that your
contributions are licensed under the same terms.

Every commit must be signed off with a **Developer Certificate of Origin**
(DCO), which certifies that you wrote the code or otherwise have the right to
submit it. Add a `Signed-off-by:` line to each commit:

```bash
# One-time: configure git to sign off automatically
git config format.signOff true

# Or manually on each commit
git commit -s -m "feat(dataset): add stratified split"
```

The DCO text is the standard
[Developer Certificate of Origin v1.1](https://developercertificate.org/):

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
1 Letterman Drive, Suite D4700, San Francisco, CA, 94129

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

A GitHub Action enforces DCO on every PR; unsigned commits block the merge.

---

## 2. Development environment

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.11 and 3.12 tested in CI |
| [uv](https://docs.astral.sh/uv/) | latest | Python dependency & venv manager |
| [Task](https://taskfile.dev) | 3.x | Build runner (`winget install Task.Task` on Windows) |
| Docker | 24+ | Or any `docker compose` compatible runtime |
| Node.js | 20 LTS | For the web/tauri apps |
| Rust | stable | For the Tauri app only |

### Setup

```bash
git clone https://github.com/vulis/vulis.git
cd vulis

# Install Python dependencies for all libs and services
task install

# Bring up the local dev stack
task up

# Run all checks
task check
```

See [`Taskfile.yml`](./Taskfile.yml) for the full list of available commands.

### Per-package development

Each library and service has its own `pyproject.toml` and can be developed
in isolation:

```bash
cd libs/storage
uv sync
uv run pytest
```

---

## 3. Git workflow

We use **trunk-based development**:

1. Branch from `main`:
   ```bash
   git checkout -b feat/dataset-stratified-split
   ```
2. Keep branches short-lived (ideally < 1 week).
3. Write [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat(dataset): add stratified split endpoint
   fix(serving): handle empty batch gracefully
   chore(ci): bump ruff to 0.6
   docs(adr): add 0004-mqtt-sparkplug
   ```
   The scope matches the affected package (`dataset`, `registry`, `storage`,
   `core-py`, `fleet`, `web`, `tauri-app`, `ci`, ...).
4. Open a **pull request** against `main`. PRs are required even for
   maintainers — this keeps history reviewable and CI enforced.
5. CI must be green and at least one reviewer must approve (the CODEOWNERS
   rule requests the right reviewers automatically).
6. **Squash-merge** to `main`. The squashed commit message follows the
   Conventional Commits format.

### Conventional commit scopes

| Scope | Used for |
|---|---|
| `core-py`, `storage`, `obs-py`, `proto`, `schemas` | shared libraries |
| `dataset`, `registry`, `training`, `serving`, `acquisition`, `fleet`, `observability`, `gateway`, `project-api` | services |
| `web`, `tauri-app` | applications |
| `cli` | `tools/vulis-cli` |
| `ci`, `chore`, `docs`, `adr`, `release` | cross-cutting |

---

## 4. Code conventions

### Python

- **Formatter & linter:** [`ruff`](https://docs.astral.sh/ruff/) (format + lint).
- **Type checker:** [`mypy`](https://mypy-lang.org/), strict on `libs/`.
- **Tests:** `pytest`, coverage ≥ 80% on `libs/`.
- **Imports:** absolute, sorted by ruff (`isort` profile).
- **Typing:** all public APIs are typed.

Run locally:
```bash
uv run ruff check .
uv run ruff format .
uv run mypy libs/
uv run pytest
```

### Rust (Tauri app only)

- `cargo fmt`, `cargo clippy -- -D warnings`.

### TypeScript (web app)

- `biome` (lint + format) or `eslint` + `prettier` (decided in M1.7).
- `vitest` for unit tests.

### License headers

Every source file must carry an SPDX header. The [`reuse`](https://reuse.software)
tool validates this:

```bash
pip install reuse
reuse lint
```

Pre-commit hooks (see below) automate all of the above.

---

## 5. Pre-commit hooks

We use [`pre-commit`](https://pre-commit.com/) for local checks. Install once:

```bash
pip install pre-commit
pre-commit install
```

Hooks run `ruff`, `mypy` (on staged files), format checks, license header
checks, and the DCO presence check on commit messages.

---

## 6. Testing

- **Unit tests** live next to the code (`tests/` folder per package).
- **Integration tests** live in the top-level [`tests/`](./tests/) folder
  and exercise multiple services against the dev docker stack.
- CI runs tests on both **Linux** and **Windows** (matrix).

### When adding a feature

- Add or update tests covering the new behavior.
- Do not lower existing coverage in `libs/`.
- If a change is hard to test, describe why in the PR description and propose
  a follow-up.

---

## 7. Adding a new package (lib or service)

1. Create the folder under `libs/` or `services/`.
2. Add a `pyproject.toml` (copy an existing one as a template).
3. Add the package to [`CODEOWNERS`](./CODEOWNERS).
4. Add the package to the CI matrix in `.github/workflows/ci.yml`.
5. Add a Task target in `Taskfile.yml` if relevant.
6. Write a short README in the package folder.

---

## 8. Architecture Decision Records (ADRs)

For any non-trivial decision (new dependency, architectural pattern, public
API change), write an ADR in [`ADR/`](./ADR/). Copy
[`ADR/0000-template.md`](./ADR/0000-template.md) and number it sequentially.

ADRs are immutable once `accepted`; superseding an ADR creates a new one that
references the old one and flips the old one to `superseded`.

---

## 9. Releases

Vulis uses **independent SemVer** per package plus a periodic
**platform baseline** tag (`vulis-YYYY.MM`). Releases are made
on demand ("au fil de l'eau") whenever a package is ready.

See the release runbook (to be added in `docs/`) and
[`tools/release/`](./tools/release/).

---

## 10. Getting help

- Open an issue with the `question` label.
- For security issues, see [SECURITY.md](./SECURITY.md) (to be added).

Welcome aboard, and happy hacking.
