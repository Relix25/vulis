# vulis-core-py

Shared core library for Vulis. Provides:

- **Exceptions** — a small hierarchy every service derives from.
- **Types** — typed identifiers (`ProjectId`, `DatasetId`, `ModelId`, ...) and
  a SemVer implementation.
- **Configuration** — a `Settings` base using `pydantic-settings`, with
  environment-variable driven config.
- **Logging** — structured logging via `structlog`, pre-wired with
  correlation IDs and a Vulis context.

## Install

```bash
uv pip install -e libs/core-py
```

## Quick usage

```python
from vulis_core import ProjectId, VulisError, get_logger, init_logging

init_logging(service="dataset", level="INFO")
log = get_logger(__name__)

pid = ProjectId.new()
log.info("project.created", project_id=str(pid))

try:
    ...
except VulisError as e:
    log.error("project.failed", error=str(e))
    raise
```

See [tests/](./tests) for more examples.

## License

BSL 1.1 → AGPL-3.0 on 2030-06-14. See [../../LICENSE](../../LICENSE).
