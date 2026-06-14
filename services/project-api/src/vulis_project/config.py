"""Service-level settings for the project-api.

Inherits from ``vulis_core.VulisSettings`` (env prefix ``VULIS_``) and adds
project-api-specific fields with prefix ``VULIS_PROJECT_``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_core import VulisSettings


class ProjectSettings(VulisSettings):
    """Settings for the project-api service.

    Inherits the Vulis-wide settings (``surface``, ``service_name``,
    ``log_level``, ``postgres_dsn``, ...). Service-specific knobs are
    exposed under the same ``VULIS_`` namespace — pydantic-settings does
    not concatenate env_prefix across inheritance, so we use the
    parent's prefix to keep the common settings (``VULIS_POSTGRES_DSN``,
    ``VULIS_KEYCLOAK_URL``) working without per-service overrides.
    """

    # NOTE: no env_prefix here — we inherit VULIS_* from VulisSettings.
    # Service-specific values land in the same namespace; if a collision
    # emerges across services, we'll switch to Field(alias=...) rather
    # than fight pydantic-settings prefix inheritance.

    service_name: str = "project-api"
    host: str = "127.0.0.1"
    port: int = 8001
    # When True, the auth dependency falls back to header-based stub (the
    # M1.3 default). Set to False once the gateway (M1.6) is in front of
    # this service in production and forwards validated claims.
    use_header_auth: bool = True


_cached: ProjectSettings | None = None


def get_settings() -> ProjectSettings:
    """Return a cached ``ProjectSettings`` instance.

    Call ``_reset_settings_cache()`` in tests after mutating env vars.
    """
    global _cached
    if _cached is None:
        _cached = ProjectSettings()
    return _cached


def _reset_settings_cache() -> None:
    """Clear the cached settings instance (test helper)."""
    global _cached
    _cached = None
