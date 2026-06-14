"""Alembic environment for Vulis.

Reads the database URL from (in priority order):
  1. ``--x url=...`` (CLI override),
  2. ``SQLALCHEMY_URL`` environment variable,
  3. ``VULIS_POSTGRES_DSN`` environment variable (Vulis convention).

Target metadata is the shared ``vulis_schemas.Base.metadata`` plus any
models registered by imported service packages (via entry points or direct
imports — extend the ``EXTRA_MODEMS`` list below as services land).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the local package is importable when alembic runs.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from vulis_schemas import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    cli_url = context.get_x_argument(as_dictionary=True).get("url")
    if cli_url:
        return cli_url
    if os.environ.get("SQLALCHEMY_URL"):
        return os.environ["SQLALCHEMY_URL"]
    dsn = os.environ.get("VULIS_POSTGRES_DSN")
    if dsn:
        # Vulis stores the DSN as a SecretStr; if it leaked into env, strip it.
        return dsn
    raise RuntimeError(
        "No database URL configured. Set VULIS_POSTGRES_DSN or pass --x url=."
    )


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _resolve_url()
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
