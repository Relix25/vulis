"""Vulis configuration base.

All Vulis services and libraries derive their configuration from
``VulisSettings`` (a pydantic-settings ``BaseSettings``). This gives us:

- environment-variable driven configuration (12-factor),
- type validation,
- a single ``VULIS_*`` namespace to avoid collisions,
- a deterministic way to dump/redact secrets.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "Surface",
    "VulisSettings",
    "get_settings",
]


Surface = Literal["workstation", "server", "edge"]
"""The three Vulis deployment surfaces (see ADR 0005)."""


class VulisSettings(BaseSettings):
    """Base settings shared by every Vulis component.

    Subclass this in each service to add service-specific fields, e.g.::

        class DatasetSettings(VulisSettings):
            model_config = SettingsConfigDict(env_prefix="VULIS_DATASET_")
            max_upload_bytes: int = 5_000_000_000
    """

    model_config = SettingsConfigDict(
        env_prefix="VULIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── identity / runtime ────────────────────────────────────
    surface: Surface = Field(default="server", description="Deployment surface.")
    service_name: str = Field(default="vulis", description="Component name, for logs/traces.")
    environment: Literal["dev", "staging", "prod"] = Field(default="dev")

    # ── observability ─────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = Field(default="json")
    otel_endpoint: str | None = Field(
        default=None,
        description="OpenTelemetry OTLP endpoint (e.g. http://otel:4317).",
    )

    # ── infrastructure endpoints ──────────────────────────────
    postgres_dsn: SecretStr | None = Field(
        default=None,
        description="PostgreSQL DSN, e.g. postgresql://user:pass@host:5432/db",
    )
    redis_url: SecretStr | None = Field(
        default=None,
        description="Redis URL, e.g. redis://host:6379/0",
    )
    mqtt_host: str = Field(default="localhost")
    mqtt_port: int = Field(default=1883)
    mqtt_username: str | None = None
    mqtt_password: SecretStr | None = None

    # ── storage ───────────────────────────────────────────────
    storage_backend: Literal["smb-protocol", "smb-mount", "local-fs", "s3"] = Field(
        default="local-fs",
        description="Storage backend to use (see ADR 0006).",
    )
    storage_smb_host: str | None = None
    storage_smb_share: str | None = None
    storage_smb_username: str | None = None
    storage_smb_password: SecretStr | None = None
    storage_smb_domain: str | None = None
    storage_local_root: str = Field(default="./.vulis-storage")

    # ── security ──────────────────────────────────────────────
    keycloak_url: str | None = Field(default=None, description="Keycloak base URL.")
    keycloak_realm: str = Field(default="vulis")
    keycloak_client_id: str = Field(default="vulis")
    keycloak_client_secret: SecretStr | None = None

    # ── helpers ───────────────────────────────────────────────
    def masked_dump(self) -> dict[str, str]:
        """Return a dict suitable for logging: secrets masked."""
        out: dict[str, str] = {}
        for name, value in self.model_dump(mode="python").items():
            if isinstance(value, SecretStr):
                out[name] = "***" if value.get_secret_value() else "<empty>"
            elif value is None:
                out[name] = "<none>"
            else:
                out[name] = str(value)
        return out


@lru_cache(maxsize=1)
def get_settings() -> VulisSettings:
    """Return the cached process-wide settings.

    Tests should call ``get_settings.cache_clear()`` after monkeypatching
    environment variables.
    """
    return VulisSettings()
