# 0001. License: BSL 1.1 with 4-year Change Date → AGPL-3.0

- **Status:** Accepted
- **Date:** 2026-06-14
- **Deciders:** Basti (founder)
- **Supersedes:** —
- **Superseded by:** —

## Context

Vulis is intended to be open source and freely usable internally — including
in production on industrial lines — but **must not be resellable** or offered
as a competing hosted service without authorization.

These two requirements ("permanently usable" and "no resale") are
**juridically incompatible** under an OSI-approved license: the Open Source
Definition (clause 1, no discrimination; clause 5, no discrimination against
fields of endeavor) explicitly forbids prohibiting resale. We therefore need
a *source-available* license that grants the desired freedoms while reserving
commercial exploitation rights.

## Decision drivers

- The founder wants the project usable internally by anyone, free of charge.
- The founder wants to forbid resale and competing SaaS, to preserve a
  future commercial option.
- The project should still become truly open source after a reasonable time.
- Contributor CLA/DCO management must remain light.

## Considered options

### Option A: AGPL-3.0

Copyleft, OSI-approved. SaaS competitors must release their modifications.

- Pros: recognized as open source, strong copyleft, network clause.
- Cons: **does not forbid resale** (the explicit requirement). Competitors
  can still sell the software as long as they release source.

### Option B: PolyForm-Shield 1.0.0

Source-available, forbids competing use, allows internal use.

- Pros: matches the requirement exactly.
- Cons: less standardized than BSL, smaller adoption in the ecosystem.

### Option C: BSL 1.1 with a Change Date and Change License

Source-available now, becomes OSI-open at a fixed date. Permits configuring
the exact grant via the "Additional Use Grant" field.

- Pros: industry-standard (Sentry, CockroachDB, HashiCorp, MariaDB),
  well-understood, configurable grant, clean conversion to open source.
- Cons: not OSI-open until the Change Date.

### Option D: Custom license

- Pros: maximum control.
- Cons: legal cost, distrust from community, low recognition.

## Decision

**Adopt Option C: Business Source License 1.1**, with:

- **Licensed Work Date:** 2026-06-14.
- **Change Date:** 2030-06-14 (4 years).
- **Change License:** GNU AGPL-3.0-only.
- **Additional Use Grant:** None (default grant: internal use allowed,
  competing/resale use requires a commercial license).

## Rationale

BSL 1.1 is the most widely recognized source-available license that converts
to open source, and the 4-year window is the market standard. It satisfies
both requirements:

- **Until 2030-06-14:** free for any internal use (factories, research,
  evaluation, modification, forking for own use), but resale/competing SaaS
  requires a commercial license.
- **On 2030-06-14:** automatically becomes AGPL-3.0, truly and permanently
  open source for everyone.

PolyForm-Shield was considered but BSL is more recognizable and gives the
same practical outcome with a clearer conversion path.

## Consequences

- **Positive:** preserves a future commercial licensing option; clearly
  communicates permitted use; converts to AGPL-3.0 automatically.
- **Negative:** not OSI "open source" until 2030; some contributors or users
  may be unfamiliar with BSL — we must document the grant clearly.
- **Neutral:** the Change Date is far enough to allow a commercial pivot but
  short enough to commit to openness.
- **Risks & mitigations:**
  - *Risk:* dual-licensing requires clean copyright. *Mitigation:* DCO on
    every commit; CLA for substantial external contributions if dual-license
    becomes necessary.

## Compliance

Every source file carries an SPDX header (`LicenseRef-Vulis-BSL-1.1`). The
`reuse` tool (configured via `REUSE.toml`) enforces this in CI.

## References

- [LICENSE](../LICENSE) — full BSL 1.1 text with project parameters.
- [NOTICE](../NOTICE) — third-party attributions.
- MariaDB BSL 1.1 reference: <https://mariadb.com/bsl11/>
- Sentry BSL explainer: <https://fossa.com/blog/business-source-license-qa-implications-commercial-open-source/>
