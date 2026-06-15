"""Service-level settings for the registry service.

Inherits from ``vulis_core.VulisSettings`` (env prefix ``VULIS_``).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_core import VulisSettings


class RegistrySettings(VulisSettings):
    """Settings for the model registry service.

    Inherits the Vulis-wide settings. The header-based auth stub is
    the M1.5 default; ``VULIS_USE_HEADER_AUTH=false`` switches to JWT
    once the gateway (M1.6) is in front.
    """

    service_name: str = "registry-api"
    host: str = "127.0.0.1"
    port: int = 8003
    use_header_auth: bool = True
    # Maximum ONNX upload size (in bytes). Defaults to 512 MB — the
    # largest single ONNX file we've seen in the field is ~250 MB.
    # Bump via env if needed.
    max_upload_bytes: int = 512 * 1024 * 1024


_cached: RegistrySettings | None = None


def get_settings() -> RegistrySettings:
    """Return a cached ``RegistrySettings`` instance.

    Call ``_reset_settings_cache()`` in tests after mutating env vars.
    """
    global _cached
    if _cached is None:
        _cached = RegistrySettings()
    return _cached


def _reset_settings_cache() -> None:
    """Clear the cached settings instance (test helper)."""
    global _cached
    _cached = None


__all__ = ["RegistrySettings", "_reset_settings_cache", "get_settings"]
