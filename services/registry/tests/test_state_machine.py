"""Tests for the model version approval state machine."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import pytest
from vulis_core import InvalidTransitionError

from vulis_registry.models import ModelStatus
from vulis_registry.state_machine import (
    ALL_VERBS,
    TRANSITIONS,
    allowed_verbs,
    apply_transition,
    is_verb_ambiguous,
)

# ─── apply_transition — happy path ──────────────────────────────


@pytest.mark.parametrize(
    ("current", "verb", "expected"),
    [
        # DRAFT → INTERNAL_REVIEW
        (ModelStatus.DRAFT, "submit_for_review", ModelStatus.INTERNAL_REVIEW),
        # REJECTED → INTERNAL_REVIEW (resubmit)
        (ModelStatus.REJECTED, "submit_for_review", ModelStatus.INTERNAL_REVIEW),
        # INTERNAL_REVIEW → STAGING
        (ModelStatus.INTERNAL_REVIEW, "approve", ModelStatus.STAGING),
        # INTERNAL_REVIEW → REJECTED
        (ModelStatus.INTERNAL_REVIEW, "reject", ModelStatus.REJECTED),
        # STAGING → APPROVED
        (ModelStatus.STAGING, "approve", ModelStatus.APPROVED),
        # STAGING → DRAFT (reject back to the bench)
        (ModelStatus.STAGING, "reject", ModelStatus.DRAFT),
        # APPROVED → DEPLOYED
        (ModelStatus.APPROVED, "deploy", ModelStatus.DEPLOYED),
        # archive from any non-archive state
        (ModelStatus.DRAFT, "archive", ModelStatus.ARCHIVED),
        (ModelStatus.INTERNAL_REVIEW, "archive", ModelStatus.ARCHIVED),
        (ModelStatus.STAGING, "archive", ModelStatus.ARCHIVED),
        (ModelStatus.APPROVED, "archive", ModelStatus.ARCHIVED),
        (ModelStatus.DEPLOYED, "archive", ModelStatus.ARCHIVED),
        (ModelStatus.REJECTED, "archive", ModelStatus.ARCHIVED),
    ],
)
def test_apply_transition_valid(current, verb, expected):
    assert apply_transition(current, verb) == expected


# ─── apply_transition — invalid ────────────────────────────────


def test_apply_transition_unknown_verb_raises():
    with pytest.raises(InvalidTransitionError) as exc_info:
        apply_transition(ModelStatus.DRAFT, "frobnicate")
    assert "Unknown transition verb" in str(exc_info.value)
    assert "frobnicate" in str(exc_info.value)


@pytest.mark.parametrize(
    ("current", "verb"),
    [
        # Cannot approve from DRAFT
        (ModelStatus.DRAFT, "approve"),
        # Cannot submit twice in a row (no back-to-back)
        (ModelStatus.INTERNAL_REVIEW, "submit_for_review"),
        # Cannot deploy without approval
        (ModelStatus.STAGING, "deploy"),
        (ModelStatus.INTERNAL_REVIEW, "deploy"),
        (ModelStatus.DRAFT, "deploy"),
        # Cannot deploy a deployed model again
        (ModelStatus.DEPLOYED, "deploy"),
        # Cannot reject from DRAFT
        (ModelStatus.DRAFT, "reject"),
    ],
)
def test_apply_transition_forbidden(current, verb):
    with pytest.raises(InvalidTransitionError) as exc_info:
        apply_transition(current, verb)
    assert "not allowed" in str(exc_info.value)


# ─── allowed_verbs ─────────────────────────────────────────────


def test_allowed_verbs_draft():
    assert set(allowed_verbs(ModelStatus.DRAFT)) == {"submit_for_review", "archive"}


def test_allowed_verbs_internal_review():
    assert set(allowed_verbs(ModelStatus.INTERNAL_REVIEW)) == {
        "approve",
        "reject",
        "archive",
    }


def test_allowed_verbs_staging():
    assert set(allowed_verbs(ModelStatus.STAGING)) == {"approve", "reject", "archive"}


def test_allowed_verbs_approved():
    assert set(allowed_verbs(ModelStatus.APPROVED)) == {"deploy", "archive"}


def test_allowed_verbs_deployed():
    assert set(allowed_verbs(ModelStatus.DEPLOYED)) == {"archive"}


def test_allowed_verbs_rejected():
    assert set(allowed_verbs(ModelStatus.REJECTED)) == {"submit_for_review", "archive"}


def test_allowed_verbs_archived_is_empty():
    assert allowed_verbs(ModelStatus.ARCHIVED) == ()


# ─── is_verb_ambiguous ─────────────────────────────────────────


def test_approve_is_ambiguous():
    assert is_verb_ambiguous("approve") is True


def test_reject_is_ambiguous():
    assert is_verb_ambiguous("reject") is True


def test_other_verbs_not_ambiguous():
    assert is_verb_ambiguous("submit_for_review") is False
    assert is_verb_ambiguous("deploy") is False
    assert is_verb_ambiguous("archive") is False


# ─── Graph completeness ────────────────────────────────────────


def test_every_state_has_at_least_one_outgoing_transition():
    """Sanity: no dead-end state (ARCHIVED is intentional — the escape
    hatch for terminal state)."""
    # The graph is complete for everything except ARCHIVED.
    states_with_out = {t.source for t in TRANSITIONS}
    assert states_with_out == set(ModelStatus) - {ModelStatus.ARCHIVED}


def test_every_verb_appears_in_transitions():
    verbs_in_use = {t.verb for t in TRANSITIONS}
    assert verbs_in_use == set(ALL_VERBS)
