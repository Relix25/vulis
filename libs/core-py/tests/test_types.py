# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

import uuid

import pytest

from vulis_core import (
    DatasetId,
    DatasetVersionId,
    EdgeId,
    EntityId,
    LineId,
    ModelId,
    ModelVersionId,
    ParseError,
    ProjectId,
    SemVer,
    TaskId,
)

# ─── EntityId ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cls,prefix",
    [
        (ProjectId, "proj"),
        (LineId, "line"),
        (TaskId, "task"),
        (DatasetId, "ds"),
        (DatasetVersionId, "dsv"),
        (ModelId, "mdl"),
        (ModelVersionId, "mdlv"),
        (EdgeId, "edge"),
    ],
)
def test_entity_id_prefix(cls: type[EntityId], prefix: str) -> None:
    assert cls.prefix == prefix
    eid = cls.new()
    assert str(eid).startswith(prefix + "_")


def test_new_generates_unique_ids() -> None:
    a, b = ProjectId.new(), ProjectId.new()
    assert a != b
    assert a.value != b.value


def test_roundtrip_string_and_parse() -> None:
    pid = ProjectId.new()
    s = str(pid)
    parsed = ProjectId.from_string(s)
    assert parsed == pid


def test_from_string_wrong_prefix_raises() -> None:
    with pytest.raises(ParseError):
        ProjectId.from_string("ds_" + uuid.uuid4().hex)


def test_from_string_invalid_uuid_raises() -> None:
    with pytest.raises(ParseError):
        ProjectId.from_string("proj_not-a-uuid")


def test_try_parse_returns_none_on_failure() -> None:
    assert ProjectId.try_parse("garbage") is None
    assert ProjectId.try_parse("proj_garbage") is None
    pid = ProjectId.new()
    assert ProjectId.try_parse(str(pid)) == pid


def test_different_id_types_dont_mix() -> None:
    u = uuid.uuid4()
    # Same underlying UUID, different types — they must NOT be equal,
    # even though both are EntityId subclasses with the same value.
    a = ProjectId(u)
    b = DatasetId(u)
    assert a != b
    assert str(a).startswith("proj_")
    assert str(b).startswith("ds_")


def test_ids_are_hashable_and_frozen() -> None:
    pid = ProjectId.new()
    s = {pid, ProjectId.from_uuid(pid.value)}
    assert len(s) == 1
    with pytest.raises(Exception):  # FrozenInstanceError
        pid.value = uuid.uuid4()  # type: ignore[misc]


def test_from_uuid_wraps_existing() -> None:
    u = uuid.uuid4()
    assert ProjectId.from_uuid(u).value == u


def test_repr_includes_prefix_form() -> None:
    pid = ProjectId.new()
    assert repr(pid) == f"ProjectId('{pid}')"


# ─── SemVer ──────────────────────────────────────────────────


def test_semver_parse_basic() -> None:
    v = SemVer.parse("1.2.3")
    assert v.core == (1, 2, 3)
    assert str(v) == "1.2.3"
    assert not v.is_pre_release


def test_semver_parse_with_pre_release_and_build() -> None:
    v = SemVer.parse("0.10.0-rc.1+build.5")
    assert v.core == (0, 10, 0)
    assert v.pre_release == ("rc", "1")
    assert v.build == ("build", "5")
    assert v.is_pre_release


def test_semver_parse_invalid() -> None:
    for bad in ["", "1", "1.2", "1.2.3.4", "01.2.3", "v1.2.3", "1.2.x"]:
        with pytest.raises(ParseError):
            SemVer.parse(bad)


def test_semver_try_parse_returns_none() -> None:
    assert SemVer.try_parse("nope") is None
    assert SemVer.try_parse("1.2.3") is not None


def test_semver_ordering_core() -> None:
    assert SemVer.parse("1.0.0") < SemVer.parse("2.0.0")
    assert SemVer.parse("2.0.0") < SemVer.parse("2.1.0")
    assert SemVer.parse("2.1.0") < SemVer.parse("2.1.1")


def test_semver_release_higher_than_prerelease() -> None:
    # 1.0.0-alpha < 1.0.0 (SemVer rule 11).
    assert SemVer.parse("1.0.0-alpha") < SemVer.parse("1.0.0")


def test_semver_pre_release_precedence() -> None:
    # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta
    # Per spec example.
    a = SemVer.parse("1.0.0-alpha")
    a1 = SemVer.parse("1.0.0-alpha.1")
    ab = SemVer.parse("1.0.0-alpha.beta")
    b = SemVer.parse("1.0.0-beta")
    assert a < a1 < ab < b


def test_semver_build_metadata_ignored_in_ordering() -> None:
    # 1.0.0+build1 == 1.0.0+build2 for ordering purposes.
    v1 = SemVer.parse("1.0.0+build1")
    v2 = SemVer.parse("1.0.0+build2")
    assert not (v1 < v2)
    assert not (v2 < v1)


def test_semver_bumps() -> None:
    v = SemVer.parse("1.2.3")
    assert v.bump_major() == SemVer.parse("2.0.0")
    assert v.bump_minor() == SemVer.parse("1.3.0")
    assert v.bump_patch() == SemVer.parse("1.2.4")
    # Original unchanged (frozen).
    assert v == SemVer.parse("1.2.3")


def test_semver_negative_rejected() -> None:
    with pytest.raises(ValueError):
        SemVer(-1, 0, 0)
