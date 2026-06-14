"""Uvicorn entry point for the project-api.

Run via ``uv run uvicorn vulis_project.main:app --reload --port 8001``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_project.app import create_app

# Module-level ``app`` is what uvicorn imports by default.
app = create_app()


def main() -> None:  # pragma: no cover — convenience wrapper
    import uvicorn

    from vulis_project.config import get_settings

    s = get_settings()
    uvicorn.run("vulis_project.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
