# 0010. Air-gap git mirror on the server

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis is developed on **GitHub** (the canonical public repository). But the
server and edge surfaces are air-gap (see [ADR 0005](./0005-topology-3-surfaces.md)):
they cannot clone or pull from GitHub at runtime. We still need the ability
to:

- Inspect and rebuild any version of Vulis *on the server itself*, offline.
- Recover the source after a server reinstall without internet.
- Allow local branches / hotfixes to be made on the server if GitHub is
  unreachable.

## Decision drivers

- Air-gap on server and edges.
- Single source of truth remains GitHub (public).
- Reproducible offline builds from source.
- Low operational burden.

## Considered options

### Option A: Periodic `git clone --mirror` from the workstation

The workstation (which has internet) periodically mirrors GitHub → server.

- Pros: simple; uses git primitives; captures all refs/tags.
- Cons: someone (or a cron) must run it.

### Option B: Self-hosted Git server on the server, sync with GitHub

Gitea / Forgejo / GitLab running on the server, configured as a mirror of
the GitHub repo.

- Pros: web UI, issue mirroring, future local CI.
- Cons: another service to run/maintain on the already-busy server;
  overkill for a source mirror.

### Option C: Bundle files shipped via the relay

`git bundle` produced on the workstation, pushed via the artifact relay.

- Pros: ties into the existing `vulis relay sync` workflow (ADR 0007).
- Cons: less ergonomic than a bare clone for browsing; no incremental fetch
  UI without scripting.

### Option D: Bare mirror + relay push (chosen)

A bare `git clone --mirror` of the GitHub repo lives on the server. The
workstation runs a `vulis relay git` command that:

1. Fetches the latest from GitHub (workstation has internet).
2. Pushes (over SMB or SSH) into the server's bare mirror.
3. Optionally also writes release tarballs / wheels into the Artifact Depot
   (see ADR 0007), so the server can rebuild without pip/internet.

The server can then serve the mirror to edges (read-only) via git-daemon or
a lightweight HTTP smart-http, if needed; mostly the mirror is for the
server itself.

## Decision

**Adopt Option D.** A bare mirror on the server, kept up to date by the
`vulis relay git` command run from the workstation. Optional: Gitea/Forgejo
can be added later if a web UI or local CI is desired (deferred to a future
ADR).

## Rationale

A bare mirror is the smallest possible surface that gives us full offline
source access, including tags, release branches, and history. Coupling the
update to `vulis relay` keeps all air-gap-crossing operations in one tool,
consistent with ADR 0007.

## Consequences

- **Positive:** offline source recovery and audit; the server can rebuild any
  released version from source if the depot lacks a binary.
- **Negative:** workstation-driven sync means the mirror can lag GitHub by
  however long between relay runs — acceptable, since the server doesn't
  need live history.
- **Neutral:** the mirror is read-mostly; local hotfixes are made on a
  separate non-bare clone and pushed back through GitHub (then mirrored in)
  to keep GitHub canonical.

## Interface sketch

```bash
# On the workstation:
vulis relay git sync       # fetch GitHub → push to server bare mirror
vulis relay git verify     # check the server mirror ref set vs GitHub

# On the server:
git --git-dir=/srv/vulis.git log -1           # inspect
git clone /srv/vulis.git /tmp/vulis-src       # materialize for a build
```

## Risks & mitigations

- *Risk:* mirror diverges from GitHub unnoticed. *Mitigation:* `vulis relay
  git verify` compares refs and warns; the relay records each sync in the
  audit trail.
- *Risk:* secrets accidentally pushed to the mirror. *Mitigation:* the
  mirror is of the *public* GitHub repo only; secrets live elsewhere.
- *Risk:* Git LFS objects (none currently) would need separate handling.
  *Mitigation:* Vulis deliberately keeps large blobs out of git (see
  [.gitignore](../.gitignore)).

## Compliance

The mirror location and `vulis relay git` subcommands are documented in
`docs/` and registered in the audit trail on each sync.

## References

- [ADR 0007](./0007-air-gap-relay.md) — relay command family.
- [ADR 0005](./0005-topology-3-surfaces.md) — air-gap constraint.
- `git bundle`: <https://git-scm.com/docs/git-bundle>
