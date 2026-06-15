"""Uvicorn entry point for the registry service.

Run via ``uv run uvicorn vulis_registry.main:app --reload --port 8003``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_registry.app import create_app

app = create_app()


def main() -> None:  # pragma: no cover — convenience wrapper
    import uvicorn

    from vulis_registry.config import get_settings

    s = get_settings()
    uvicorn.run("vulis_registry.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
