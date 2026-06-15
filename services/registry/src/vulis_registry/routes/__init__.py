"""Aggregated APIRouter for the registry service."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter

from vulis_registry.routes import models, versions

api_router = APIRouter()
api_router.include_router(models.router)
api_router.include_router(versions.router)


__all__ = ["api_router"]
