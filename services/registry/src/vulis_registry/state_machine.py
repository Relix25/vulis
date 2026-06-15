"""ModelVersion approval state machine.

The graph (see ``docs/handoff/04-roadmap.md`` § M1.5)::

    DRAFT ──submit_for_review──► INTERNAL_REVIEW ──approve──► STAGING
                                       │                     │
                                       ├──reject──► REJECTED │
                                       ▲                     ├──approve──► APPROVED
                                       └──── (resubmit)      │                │
                                                             │                ├──deploy──► DEPLOYED
                                                             │                │
                                                             └──reject────────┘
                                                                              ▼
                                                                              ARCHIVED

The graph allows:

* ``submit_for_review`` from ``DRAFT`` (resubmit) or ``REJECTED``
  (re-submit after a rejection — common in practice).
* ``approve`` from ``INTERNAL_REVIEW`` → ``STAGING``.
* ``reject`` from ``INTERNAL_REVIEW`` → ``REJECTED``.
* ``approve`` from ``STAGING`` → ``APPROVED``.
* ``reject`` from ``STAGING`` → ``DRAFT`` (back to the bench).
* ``deploy`` from ``APPROVED`` → ``DEPLOYED``.
* ``archive`` from any non-archive state (admin escape hatch).

Role gating per verb is enforced in the route layer, not here. The
state machine is purely about *what* transition is allowed, not *who*
can do it.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vulis_core import InvalidTransitionError

from vulis_registry.models import ModelStatus

# ─── Verbs ──────────────────────────────────────────────────────

Verb = Literal[
    "submit_for_review",
    "approve",
    "reject",
    "deploy",
    "archive",
]

ALL_VERBS: tuple[Verb, ...] = (
    "submit_for_review",
    "approve",
    "reject",
    "deploy",
    "archive",
)


# ─── Transition graph ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Transition:
    verb: Verb
    source: ModelStatus
    target: ModelStatus


TRANSITIONS: tuple[Transition, ...] = (
    # DRAFT can be submitted for review, or archived.
    Transition(
        verb="submit_for_review", source=ModelStatus.DRAFT, target=ModelStatus.INTERNAL_REVIEW
    ),
    # A rejected version can be resubmitted (sends it back to review).
    Transition(
        verb="submit_for_review", source=ModelStatus.REJECTED, target=ModelStatus.INTERNAL_REVIEW
    ),
    # Reviewer passes it to staging.
    Transition(verb="approve", source=ModelStatus.INTERNAL_REVIEW, target=ModelStatus.STAGING),
    # Reviewer rejects outright.
    Transition(verb="reject", source=ModelStatus.INTERNAL_REVIEW, target=ModelStatus.REJECTED),
    # Reviewer approves staging → approved.
    Transition(verb="approve", source=ModelStatus.STAGING, target=ModelStatus.APPROVED),
    # Reviewer rejects staging → back to DRAFT for another iteration.
    Transition(verb="reject", source=ModelStatus.STAGING, target=ModelStatus.DRAFT),
    # Operator (or admin) deploys an approved version.
    Transition(verb="deploy", source=ModelStatus.APPROVED, target=ModelStatus.DEPLOYED),
    # Admin can archive from any non-archive state.
    Transition(verb="archive", source=ModelStatus.DRAFT, target=ModelStatus.ARCHIVED),
    Transition(verb="archive", source=ModelStatus.INTERNAL_REVIEW, target=ModelStatus.ARCHIVED),
    Transition(verb="archive", source=ModelStatus.STAGING, target=ModelStatus.ARCHIVED),
    Transition(verb="archive", source=ModelStatus.APPROVED, target=ModelStatus.ARCHIVED),
    Transition(verb="archive", source=ModelStatus.DEPLOYED, target=ModelStatus.ARCHIVED),
    Transition(verb="archive", source=ModelStatus.REJECTED, target=ModelStatus.ARCHIVED),
)


_BY_KEY: dict[tuple[ModelStatus, str], ModelStatus] = {
    (t.source, t.verb): t.target for t in TRANSITIONS
}

# `approve` is overloaded (reviewer passes both INTERNAL_REVIEW and
# STAGING). `reject` is overloaded too. The role layer (routes) is
# responsible for asking "which approve / which reject" — the state
# machine is symmetric and the verb + source state are enough to
# disambiguate. See ``is_verb_ambiguous`` for the helper.

_AMBIGUOUS_VERBS: frozenset[str] = frozenset({"approve", "reject"})


# ─── Public API ────────────────────────────────────────────────


def apply_transition(current: ModelStatus, verb: str) -> ModelStatus:
    """Return the new state after applying ``verb`` from ``current``.

    Raises ``InvalidTransitionError`` (vulis_core) if the verb is
    unknown or the transition isn't allowed from the current state.
    """
    if verb not in ALL_VERBS:
        raise InvalidTransitionError(
            f"Unknown transition verb: {verb!r}. Allowed: {', '.join(ALL_VERBS)}"
        )
    target = _BY_KEY.get((current, verb))
    if target is None:
        raise InvalidTransitionError(f"Transition {current.value} --[{verb}]--> ? is not allowed")
    return target


def allowed_verbs(current: ModelStatus) -> tuple[Verb, ...]:
    """Return the verbs that can be applied from ``current`` (for the UI)."""
    return tuple(t.verb for t in TRANSITIONS if t.source == current)


def is_verb_ambiguous(verb: str) -> bool:
    """Return True for verbs that map to multiple transitions.

    ``approve`` and ``reject`` are ambiguous — they can mean different
    things depending on the current state. Routes use this to know
    whether the verb alone is enough or if a state disambiguator is
    needed (in our current design, the state is enough).
    """
    return verb in _AMBIGUOUS_VERBS


__all__ = [
    "ALL_VERBS",
    "TRANSITIONS",
    "Transition",
    "Verb",
    "allowed_verbs",
    "apply_transition",
    "is_verb_ambiguous",
]
