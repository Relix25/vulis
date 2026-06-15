"""Aggregated APIRouter for the dataset service.

Each resource (datasets, versions, imports) lives in its own file and
contributes a router here.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi import APIRouter

from vulis_dataset.routes import datasets, imports, samples, versions

api_router = APIRouter()
api_router.include_router(datasets.router)
api_router.include_router(versions.router)
api_router.include_router(samples.router)
api_router.include_router(imports.router)


__all__ = ["api_router"]
