"""Task lifecycle state machine.

The graph:

    BACKLOG ──start──► IN_PROGRESS ──submit──► IN_VALIDATION
                          ▲                          │
                          │                          ├──approve──► DEPLOYED
                          │                          │                │
                          └──reject──────────────────┘                │
                                                                    ▼
                                                                MONITORING
                                                                    │
                                                                    ▼
                                                                RETRAINING
                                                                    │
                                                                    └──start──► IN_PROGRESS
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vulis_core import InvalidTransitionError

from vulis_project.models import TaskState

# ─── Verbs ──────────────────────────────────────────────────────

Verb = Literal["start", "submit", "approve", "reject", "deploy", "retrain"]

ALL_VERBS: tuple[Verb, ...] = ("start", "submit", "approve", "reject", "deploy", "retrain")


# ─── Transition graph ──────────────────────────────────────────
#
# Static description of "from X via verb Y → Z". The runtime check is just
# a dict lookup; tests can iterate TRANSITIONS for coverage.


@dataclass(frozen=True, slots=True)
class Transition:
    verb: Verb
    source: TaskState
    target: TaskState


TRANSITIONS: tuple[Transition, ...] = (
    Transition(verb="start", source=TaskState.BACKLOG, target=TaskState.IN_PROGRESS),
    Transition(verb="start", source=TaskState.RETRAINING, target=TaskState.IN_PROGRESS),
    Transition(verb="submit", source=TaskState.IN_PROGRESS, target=TaskState.IN_VALIDATION),
    Transition(verb="approve", source=TaskState.IN_VALIDATION, target=TaskState.DEPLOYED),
    Transition(verb="reject", source=TaskState.IN_VALIDATION, target=TaskState.IN_PROGRESS),
    Transition(verb="deploy", source=TaskState.DEPLOYED, target=TaskState.MONITORING),
    Transition(verb="retrain", source=TaskState.MONITORING, target=TaskState.RETRAINING),
)


_BY_KEY: dict[tuple[TaskState, str], TaskState] = {
    (t.source, t.verb): t.target for t in TRANSITIONS
}


# ─── Public API ────────────────────────────────────────────────


def apply_transition(current: TaskState, verb: str) -> TaskState:
    """Return the new state after applying ``verb`` from ``current``.

    Raises ``InvalidTransitionError`` (vulis_core) if the verb is unknown
    or the transition isn't allowed from the current state.
    """
    if verb not in ALL_VERBS:
        raise InvalidTransitionError(
            f"Unknown transition verb: {verb!r}. Allowed: {', '.join(ALL_VERBS)}"
        )
    target = _BY_KEY.get((current, verb))
    if target is None:
        raise InvalidTransitionError(f"Transition {current.value} --[{verb}]--> ? is not allowed")
    return target


def allowed_verbs(current: TaskState) -> tuple[Verb, ...]:
    """Return the verbs that can be applied from ``current`` (for the UI)."""
    return tuple(t.verb for t in TRANSITIONS if t.source == current)


__all__ = [
    "ALL_VERBS",
    "TRANSITIONS",
    "Transition",
    "Verb",
    "allowed_verbs",
    "apply_transition",
]
