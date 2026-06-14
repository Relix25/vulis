# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1


from vulis_core import (
    AlreadyExistsError,
    ChecksumMismatchError,
    ConflictError,
    ExternalServiceError,
    InvalidTransitionError,
    NotFoundError,
    ObjectNotFoundError,
    RegistryError,
    StorageError,
    VulisError,
)


def test_base_is_exception_subclass() -> None:
    assert issubclass(VulisError, Exception)


def test_message_and_details_roundtrip() -> None:
    err = VulisError("boom", details={"k": 1})
    assert err.message == "boom"
    assert err.details == {"k": 1}
    assert str(err) == "boom"


def test_repr_includes_details_when_present() -> None:
    err = VulisError("boom", details={"k": 1})
    r = repr(err)
    assert "VulisError" in r
    assert "'boom'" in r
    assert "details" in r


def test_repr_omits_details_when_absent() -> None:
    err = VulisError("boom")
    assert repr(err) == "VulisError('boom')"


def test_empty_message_falls_back_to_class_name() -> None:
    err = VulisError()
    assert str(err) == "VulisError"


def test_storage_error_hierarchy() -> None:
    assert issubclass(StorageError, VulisError)
    assert issubclass(ObjectNotFoundError, StorageError)


def test_object_not_found_is_both_storage_and_notfound() -> None:
    # Multiple inheritance: callers can catch either branch.
    assert issubclass(ObjectNotFoundError, StorageError)
    assert issubclass(ObjectNotFoundError, NotFoundError)
    err = ObjectNotFoundError("missing", details={"key": "abc"})
    assert isinstance(err, StorageError)
    assert isinstance(err, NotFoundError)


def test_checksum_mismatch() -> None:
    err = ChecksumMismatchError("hash differs", details={"expected": "a", "actual": "b"})
    assert err.details["expected"] == "a"


def test_invalid_transition_is_registry_and_conflict() -> None:
    assert issubclass(InvalidTransitionError, RegistryError)
    assert issubclass(InvalidTransitionError, ConflictError)


def test_external_service_carries_upstream_info() -> None:
    err = ExternalServiceError(
        "broker down", service="mosquitto", upstream_error="ECONNREFUSED"
    )
    assert err.service == "mosquitto"
    assert err.upstream_error == "ECONNREFUSED"
    assert err.details["service"] == "mosquitto"
    assert err.details["upstream_error"] == "ECONNREFUSED"


def test_details_default_is_independent_dict() -> None:
    # Each instance must get its own dict, not a shared default.
    a = VulisError("a")
    b = VulisError("b")
    a.details["x"] = 1
    assert "x" not in b.details


def test_details_mapping_is_copied() -> None:
    src: dict[str, int] = {"k": 1}
    err = VulisError("x", details=src)
    src["k"] = 999  # mutate the source — must not leak
    assert err.details["k"] == 1


def test_already_exists_and_conflict_are_distinct() -> None:
    # Both are "409-ish" but semantically different — they must not subclass
    # one another.
    assert not issubclass(AlreadyExistsError, ConflictError)
    assert not issubclass(ConflictError, AlreadyExistsError)
    assert issubclass(AlreadyExistsError, VulisError)
    assert issubclass(ConflictError, VulisError)
