"""Tests for the Task state machine."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import pytest
from vulis_core import InvalidTransitionError

from vulis_project.models import TaskState
from vulis_project.state_machine import (
    ALL_VERBS,
    TRANSITIONS,
    allowed_verbs,
    apply_transition,
)

# ─── apply_transition — happy path ──────────────────────────────


@pytest.mark.parametrize(
    ("current", "verb", "expected"),
    [
        (TaskState.BACKLOG, "start", TaskState.IN_PROGRESS),
        (TaskState.RETRAINING, "start", TaskState.IN_PROGRESS),
        (TaskState.IN_PROGRESS, "submit", TaskState.IN_VALIDATION),
        (TaskState.IN_VALIDATION, "approve", TaskState.DEPLOYED),
        (TaskState.IN_VALIDATION, "reject", TaskState.IN_PROGRESS),
        (TaskState.DEPLOYED, "deploy", TaskState.MONITORING),
        (TaskState.MONITORING, "retrain", TaskState.RETRAINING),
    ],
)
def test_apply_transition_valid(current, verb, expected):
    assert apply_transition(current, verb) == expected


# ─── apply_transition — invalid ─────────────────────────────────


def test_apply_transition_unknown_verb_raises():
    with pytest.raises(InvalidTransitionError) as exc_info:
        apply_transition(TaskState.BACKLOG, "frobnicate")
    assert "Unknown transition verb" in str(exc_info.value)
    assert "frobnicate" in str(exc_info.value)


@pytest.mark.parametrize(
    ("current", "verb"),
    [
        (TaskState.BACKLOG, "submit"),  # must start first
        (TaskState.BACKLOG, "approve"),
        (TaskState.BACKLOG, "deploy"),
        (TaskState.IN_PROGRESS, "approve"),  # must submit first
        (TaskState.IN_PROGRESS, "deploy"),
        (TaskState.IN_VALIDATION, "start"),  # no direct restart
        (TaskState.IN_VALIDATION, "deploy"),
        (TaskState.DEPLOYED, "retrain"),  # must go to monitoring first
        (TaskState.DEPLOYED, "reject"),
        (TaskState.RETRAINING, "submit"),  # must start first
        (TaskState.RETRAINING, "retrain"),
    ],
)
def test_apply_transition_forbidden(current, verb):
    with pytest.raises(InvalidTransitionError) as exc_info:
        apply_transition(current, verb)
    assert "not allowed" in str(exc_info.value)


# ─── allowed_verbs ──────────────────────────────────────────────


def test_allowed_verbs_backlog():
    assert allowed_verbs(TaskState.BACKLOG) == ("start",)


def test_allowed_verbs_in_progress():
    assert set(allowed_verbs(TaskState.IN_PROGRESS)) == {"submit"}


def test_allowed_verbs_in_validation():
    assert set(allowed_verbs(TaskState.IN_VALIDATION)) == {"approve", "reject"}


def test_allowed_verbs_deployed():
    assert allowed_verbs(TaskState.DEPLOYED) == ("deploy",)


def test_allowed_verbs_monitoring():
    assert allowed_verbs(TaskState.MONITORING) == ("retrain",)


def test_allowed_verbs_retraining():
    assert allowed_verbs(TaskState.RETRAINING) == ("start",)


# ─── Graph completeness ─────────────────────────────────────────


def test_every_state_has_at_least_one_outgoing_transition():
    """Sanity: the graph covers every TaskState (no dead-end states)."""
    states_with_out = {t.source for t in TRANSITIONS}
    assert states_with_out == set(TaskState)


def test_every_verb_appears_in_transitions():
    verbs_in_use = {t.verb for t in TRANSITIONS}
    assert verbs_in_use == set(ALL_VERBS)
