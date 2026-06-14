# Vulis Governance

This document describes how the Vulis project is governed: roles, decision
making, and how someone becomes a maintainer. It is intentionally lightweight;
we will refine it as the community grows.

---

## 1. Principles

- **Open and transparent.** All design discussions happen in public GitHub
  issues and pull requests. Decisions are recorded as
  [Architecture Decision Records (ADRs)](./ADR/).
- **Meritocratic.** Influence is earned through sustained, high-quality
  contributions.
- **Pragmatic.** We optimize for shipping a working, well-engineered product,
  not for process.
- **Respectful.** We follow the Code of Conduct (to be added) and assume good
  faith.

---

## 2. Roles

### Contributor

Anyone who submits a pull request. Contributors:

- Follow [CONTRIBUTING.md](./CONTRIBUTING.md).
- Sign the DCO on every commit.
- Respond to review feedback.

### Maintainer

A contributor with commit access to the repository. Maintainers:

- Review and merge pull requests.
- Tag and cut releases.
- Participate in ADR discussions and vote when consensus is unclear.
- Mentor new contributors.

Becoming a maintainer is based on sustained contribution quality, breadth,
and good judgment, demonstrated over time. There is no fixed number of PRs;
it is a judgment call by the existing maintainers.

A maintainer may step down to Contributor status at any time.

### Lead maintainer

Currently Basti (project founder). The lead maintainer:

- Has the final say when consensus cannot be reached.
- Is the primary contact for licensing and security matters.
- Owns the BSL 1.1 → AGPL-3.0 transition on 2030-06-14.

The role is transferable; succession is decided by maintainers.

---

## 3. Decision making

We use **lazy consensus** as the default.

| Decision type | Process |
|---|---|
| Bug fix, refactor, docs | A PR; merged once a maintainer approves and CI is green. |
| New feature in an existing package | PR + brief design note in the PR description. Larger designs get an ADR. |
| Cross-cutting feature, new dependency, breaking change, architectural change | **ADR** (`proposed` → `accepted`). At least one week for feedback; maintainers merge when consensus emerges. |
| Licensing or governance change | ADR + explicit maintainer vote (majority). |

Consensus means: no maintainer objects, and at least one maintainer other than
the author actively supports the change.

### When consensus fails

If maintainers cannot agree after a reasonable discussion, the lead maintainer
makes the call. The dissenting position is recorded in the ADR so the
rationale is preserved.

---

## 4. ADRs

[Architecture Decision Records](./ADR/) are the canonical record of design
choices. Each ADR has a status:

- `proposed` — open for discussion.
- `accepted` — adopted; supersedes any prior ADR it references.
- `deprecated` — no longer relevant, but not replaced.
- `superseded` — replaced by a newer ADR (which references it).

Anyone may propose an ADR by opening a PR copying
[`ADR/0000-template.md`](./ADR/0000-template.md).

---

## 5. Security

Security issues are **not** reported via public issues. Until a dedicated
contact is published, report them privately to the lead maintainer via a
GitHub security advisory
([`Security` tab → `Report a vulnerability`](https://github.com/vulis/vulis/security/advisories/new)).

---

## 6. Licensing

Vulis is licensed under the [BSL 1.1](./LICENSE), converting to AGPL-3.0
on 2030-06-14. All contributions are accepted under the same terms (see the
[DCO](./CONTRIBUTING.md#1-licensing--dco)).

Commercial licensing inquiries are handled by the lead maintainer.

---

## 7. Changes to this document

This governance document is itself versioned. Material changes require
maintainer consensus and a dedicated PR.
