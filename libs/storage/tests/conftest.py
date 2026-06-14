# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Shared test fixtures for vulis-storage."""

from __future__ import annotations

import pytest

from vulis_storage import LocalFSBackend


def pytest_addoption(parser: pytest.Parser) -> None:
    """CLI options for the live SMB tests.

    Usage::

        pytest --smb-host nas.local --smb-share vulis \\
               --smb-user me --smb-pass secret
    """
    parser.addoption("--smb-host", action="store", default=None)
    parser.addoption("--smb-share", action="store", default=None)
    parser.addoption("--smb-user", action="store", default=None)
    parser.addoption("--smb-pass", action="store", default=None)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smb: live SMB share required")


@pytest.fixture
def local_backend(tmp_path) -> LocalFSBackend:
    """A fresh LocalFSBackend rooted at a temp dir."""
    return LocalFSBackend(tmp_path / "store")


@pytest.fixture
def local_backend_with_prefix(tmp_path) -> LocalFSBackend:
    return LocalFSBackend(tmp_path / "store", root_prefix="vulis/blobs")
