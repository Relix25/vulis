# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

"""Live SMB tests (skipped by default).

Run against a real share via CLI args::

    pytest --smb-host nas.local \\
           --smb-share vulis \\
           --smb-user me \\
           --smb-pass secret
"""

from __future__ import annotations

import os
import uuid

import pytest

# CLI options --smb-host / --smb-share / --smb-user / --smb-pass and the
# `smb` marker are declared in conftest.py (the canonical place for
# pytest hooks).

def _smb_params():
    return (
        os.environ.get("VULIS_SMB_HOST"),
        os.environ.get("VULIS_SMB_SHARE"),
        os.environ.get("VULIS_SMB_USER"),
        os.environ.get("VULIS_SMB_PASS"),
    )


@pytest.fixture(scope="module")
def smb_backend(request: pytest.FixtureRequest):
    host = request.config.getoption("--smb-host") or _smb_params()[0]
    share = request.config.getoption("--smb-share") or _smb_params()[1]
    user = request.config.getoption("--smb-user") or _smb_params()[2]
    pwd = request.config.getoption("--smb-pass") or _smb_params()[3]

    if not all([host, share, user, pwd]):
        pytest.skip("No SMB connection parameters provided (use --smb-* or VULIS_SMB_* env)")

    from vulis_storage import SmbProtocolBackend

    backend = SmbProtocolBackend(
        host=host,
        share=share,
        username=user,
        password=pwd,
        root_prefix=f"vulis-tests/{uuid.uuid4().hex}",
    )
    yield backend
    backend.close()


@pytest.mark.smb
def test_smb_put_get_roundtrip(smb_backend) -> None:
    key = smb_backend.put_bytes("roundtrip.bin", b"hello-smb")
    assert smb_backend.get_bytes(key) == b"hello-smb"


@pytest.mark.smb
def test_smb_exists(smb_backend) -> None:
    smb_backend.put_bytes("e", b"x")
    assert smb_backend.exists("e")
    assert not smb_backend.exists("missing")


@pytest.mark.smb
def test_smb_stat(smb_backend) -> None:
    smb_backend.put_bytes("s", b"0123456789")
    info = smb_backend.stat("s")
    assert info.size == 10


@pytest.mark.smb
def test_smb_delete(smb_backend) -> None:
    smb_backend.put_bytes("d", b"x")
    smb_backend.delete("d")
    assert not smb_backend.exists("d")


@pytest.mark.smb
def test_smb_list(smb_backend) -> None:
    for k in ("list/a", "list/b", "list/c"):
        smb_backend.put_bytes(k, b"x")
    keys = sorted(o.key for o in smb_backend.list("list"))
    assert keys == ["list/a", "list/b", "list/c"]
