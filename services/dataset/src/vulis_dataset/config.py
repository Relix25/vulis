"""Service-level settings for the dataset service.

Inherits from ``vulis_core.VulisSettings`` (env prefix ``VULIS_``).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_core import VulisSettings


class DatasetSettings(VulisSettings):
    """Settings for the dataset-api service.

    Inherits the Vulis-wide settings (``surface``, ``service_name``,
    ``log_level``, ``postgres_dsn``, ``storage_backend``, ...). The
    header-based auth stub is the M1.4 default — set
    ``VULIS_USE_HEADER_AUTH=false`` in production once the gateway
    (M1.6) is in front of this service and forwards validated claims.
    """

    # NOTE: no env_prefix here — we inherit VULIS_* from VulisSettings
    # (same convention as vulis-project).

    service_name: str = "dataset-api"
    host: str = "127.0.0.1"
    port: int = 8002
    use_header_auth: bool = True
    # Where the LOCAL importer reads from on the server. A relative or
    # absolute filesystem path. In production this should be a
    # controlled share or sandbox; in dev/tests it points to a temp dir.
    import_local_root: str = "/data/vulis/imports"


_cached: DatasetSettings | None = None


def get_settings() -> DatasetSettings:
    """Return a cached ``DatasetSettings`` instance.

    Call ``_reset_settings_cache()`` in tests after mutating env vars.
    """
    global _cached
    if _cached is None:
        _cached = DatasetSettings()
    return _cached


def _reset_settings_cache() -> None:
    """Clear the cached settings instance (test helper)."""
    global _cached
    _cached = None


__all__ = ["DatasetSettings", "_reset_settings_cache", "get_settings"]
