# vulis-schemas

Shared database layer for Vulis services.

Provides:

- a single **SQLAlchemy 2.x declarative base** (`vulis_schemas.Base`),
- common **typed mixins** (`UUIDPrimaryKey`, `Timestamped`, `TenantScoped`),
- an **Alembic environment** and the **migrations** shared by all services.

## Why shared?

Vulis services share a single Postgres database (multi-schema inside), so
foreign keys and constraints must stay coherent. Putting the base + mixins +
migrations in one place avoids drift and lets each service import only what
it needs.

## Layout

```
src/vulis_schemas/
├── base.py        # declarative Base + naming convention + mixins
├── types.py       # custom SQLAlchemy types (EntityId, SemVer)
└── ...
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_initial.py   # creates the core tables + audit_events
alembic.ini
```

## Usage

```python
from sqlalchemy.orm import Mapped, mapped_column
from vulis_schemas import Base, UUIDPrimaryKey, Timestamped, TenantScoped

class Project(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255))
```

## Running migrations

```bash
# Apply all migrations to the configured database:
alembic -c libs/schemas/alembic.ini upgrade head

# Generate a new revision (after editing models):
alembic -c libs/schemas/alembic.ini revision --autogenerate -m "add projects"
```

In M1.2 the platform compose applies migrations automatically on startup.

## License

BSL 1.1 → AGPL-3.0 on 2030-06-14. See [../../LICENSE](../../LICENSE).
