# Security Policy

## Reporting a vulnerability

We take security issues seriously. **Do not open a public GitHub issue** for
security problems.

Please report vulnerabilities privately using GitHub's security advisory
feature:

> **<https://github.com/vulis/vulis/security/advisories/new>**

Alternatively, until a dedicated security email is published, contact the
maintainers privately through the same advisory flow.

Include in your report:

- A description of the issue and its potential impact.
- Steps to reproduce, or a proof-of-concept.
- Affected versions (commit SHA or tag if possible).
- Any suggested remediation.

You should receive an acknowledgement within **5 business days**. We will keep
you informed of progress and coordinate a public disclosure timeline with you.

## Scope

Vulnerabilities in the **Vulis source code** in this repository are in scope.
This includes the libraries in `libs/`, services in `services/`, applications
in `apps/`, the CLI in `tools/`, and the bundled Docker compose configurations.

The following are **out of scope**:

- Vulnerabilities in third-party dependencies (report them upstream). We still
  appreciate being notified so we can track and patch.
- Issues that require already-compromised credentials or physical access.
- Theoretical DoS without a concrete attack vector.
- Default configurations intended for development (`docker-compose.dev.yml`),
  provided the documentation marks them as not for production.

## Supported versions

Vulis is pre-1.0 and under active development. Only the latest `main` and the
most recent release tag receive security fixes.

| Version | Supported |
|---|---|
| `main` (development) | ✅ |
| Latest release tag | ✅ |
| Older tags | ❌ |

## Hardening notes (production deployments)

Vulis is designed for **on-premise, air-gap** deployments, but it ships with
development defaults. Before any production use, at minimum:

- Replace all default secrets (Postgres, Redis, Keycloak admin, Mosquitto).
- Enable TLS on every listener (server ↔ workstation, server ↔ edge).
- Restrict network exposure: edge nodes should not be reachable from outside
  the line network; the server should sit behind the plant firewall.
- Configure Keycloak with strong password policies and multi-factor auth for
  privileged roles.
- Mount the SMB share with the minimum necessary permissions.
- Run container images with least privilege (read-only root filesystem where
  possible, non-root users, resource limits).

A production hardening guide will be published in `docs/` during M9.
