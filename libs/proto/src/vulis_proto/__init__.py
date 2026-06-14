"""vulis-proto — package marker.

The generated protobuf code lives under ``vulis_proto.gen``. We expose the
proto package names here so that importers don't need to know the exact
generated path.

Until the first `buf generate` run, this package is empty; that's fine —
no service depends on the stubs in M1.0/M1.1. The first consumer is M1.3
(project-api).
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

__version__ = "0.1.0"

# Generated code is produced by `buf generate` into vulis_proto/gen.
# We intentionally do NOT import it eagerly here so that this package can
# be installed (and imported) even before code generation runs.
__all__ = ["__version__"]
