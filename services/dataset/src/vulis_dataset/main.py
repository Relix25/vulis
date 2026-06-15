"""Uvicorn entry point for the dataset service.

Run via ``uv run uvicorn vulis_dataset.main:app --reload --port 8002``.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from vulis_dataset.app import create_app

# Module-level ``app`` is what uvicorn imports by default.
app = create_app()


def main() -> None:  # pragma: no cover — convenience wrapper
    import uvicorn

    from vulis_dataset.config import get_settings

    s = get_settings()
    uvicorn.run("vulis_dataset.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
