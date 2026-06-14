"""Aggregated APIRouter for the project-api.

Each resource (projects, lines, tasks, campaigns) lives in its own file
and contributes a router here.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter

from vulis_project.routes import campaigns, lines, projects, tasks

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(lines.router)
api_router.include_router(tasks.router)
api_router.include_router(campaigns.router)


__all__ = ["api_router"]
