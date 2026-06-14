"""SMB backend (OS-mounted variant).

For performance-sensitive workloads (e.g. traversing thousands of small
files during training), the operator can mount the SMB share at the OS level
and use this backend. It is a thin specialization of ``LocalFSBackend`` that
records the SMB provenance.

The mount itself is the operator's responsibility (Linux: ``mount -t cifs``;
Windows: ``net use`` or a drive letter). This backend assumes the share is
already reachable as a local path.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_storage.backends.local_fs import LocalFSBackend

__all__ = ["SmbMountBackend"]


class SmbMountBackend(LocalFSBackend):
    """LocalFS variant identifying itself as an OS-mounted SMB share.

    Parameters
    ----------
    mount_path:
        Local path where the SMB share is mounted (e.g. ``/mnt/vulis`` or
        ``Z:\\``).
    root_prefix:
        Optional logical root applied on top of the mount.
    smb_host, smb_share:
        Recorded for provenance / logs only. Not used for I/O.
    """

    kind = "smb-mount"

    def __init__(
        self,
        mount_path: str,
        *,
        root_prefix: str = "",
        smb_host: str | None = None,
        smb_share: str | None = None,
    ) -> None:
        super().__init__(mount_path, root_prefix=root_prefix)
        self.smb_host = smb_host
        self.smb_share = smb_share
