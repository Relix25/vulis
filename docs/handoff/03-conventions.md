# 03 — Conventions pour les prochaines étapes

Ce document est le **guide de style** que tout nouvel agent doit suivre. Les
prochains services (M1.3+) doivent s'y conformer strictement pour rester
cohérents avec `libs/` et avec les goûts du mainteneur.

## 1. Structure type d'un service FastAPI

Quand tu crées `services/<name>/`, suis ce template :

```
services/<name>/
├── pyproject.toml          # name=vulis-<name>, dépend de vulis-core-py, vulis-storage, vulis-obs-py, vulis-schemas
├── README.md               # scope, quick start, API sommaire
├── src/vulis_<name>/
│   ├── __init__.py         # version + re-exports minimaux
│   ├── app.py              # factory: create_app() → FastAPI
│   ├── config.py           # <Name>Settings(VulisSettings) avec env_prefix="VULIS_<NAME>_"
│   ├── models.py           # SQLAlchemy 2.x ORM (import Base depuis vulis_schemas)
│   ├── schemas.py          # pydantic request/response models
│   ├── repositories.py     # couche DB (sessions SQLAlchemy, queries)
│   ├── routes/
│   │   ├── __init__.py     # APIRouter agrégé
│   │   └── <resource>.py   # un fichier par ressource REST
│   ├── services.py         # logique métier (entre routes et repositories)
│   ├── dependencies.py     # FastAPI Depends: get_session, get_current_user, get_storage
│   ├── exceptions.py       # (optionnel) sous-classes de vulis_core.exceptions
│   └── main.py             # point d'entrée uvicorn: `python -m vulis_<name>` ou entry point
└── tests/
    ├── conftest.py         # fixtures: engine SQLite mem, client TestClient, etc.
    ├── test_models.py
    ├── test_routes_<resource>.py
    └── test_services.py
```

**Règles :**

- **Toujours** une factory `create_app()` (pas une instance module-level).
  Rend les tests propres (un app neuf par test si besoin).
- **Sessions SQLAlchemy** : `Depends(get_session)` qui yield une session
  bornée à la requête.
- **Storage** : injecté via `Depends(get_storage)` qui build depuis settings.
- **Auth** : `Depends(get_current_user)` qui valide le token OIDC Keycloak
  et renvoie un objet `User` avec `tenant_id` + rôles.
- **Routes sous `/api/v1/<resource>`**. Versionnage dans l'URL.

### Exemple squelette (à copier)

```python
# services/dataset/src/vulis_dataset/app.py
from fastapi import FastAPI
from vulis_core import init_logging
from vulis_dataset.routes import api_router
from vulis_dataset.config import DatasetSettings, get_settings


def create_app(settings: DatasetSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_logging(service="dataset", level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title="Vulis Dataset Service",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.include_router(api_router, prefix="/api/v1")
    return app
```

## 2. Gestion d'erreurs — mapper `vulis_core.VulisError` → HTTP

Chaque service enregistre un exception handler qui convertit les exceptions
Vulis en réponses HTTP structurées. Voici la table de mapping (à mettre dans
`app.py` ou un module dédié) :

| Exception Vulis | HTTP status |
|---|---|
| `NotFoundError`, `ObjectNotFoundError` | 404 |
| `AlreadyExistsError` | 409 |
| `ConflictError`, `InvalidTransitionError` | 409 |
| `ValidationError` | 422 |
| `UnauthorizedError` | 401 |
| `ForbiddenError` | 403 |
| `StorageError` | 500 (ou 502 si backend down) |
| `RegistryError` | 500 |
| `ExternalServiceError` | 502 |
| `VulisError` (catch-all) | 500 |

**Format de réponse** (cohérent partout) :

```json
{
  "error": {
    "code": "VULIS_NOT_FOUND",
    "message": "Dataset not found: ds_abc123",
    "details": { "key": "ds_abc123" },
    "correlation_id": "abc123..."
  }
}
```

Helper à écrire dans `libs/core-py` ou dans chaque service (TODO pour M1.3) :

```python
def vulis_error_handler(request, exc):
    status = MAPPING.get(type(exc).__name__, 500)
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": type(exc).__name__.replace("Error", "").upper(),
                "message": str(exc),
                "details": exc.details,
                "correlation_id": get_correlation_id(),
            }
        },
    )

app.add_exception_handler(VulisError, vulis_error_handler)
```

## 3. Tests

### Conventions

- **Un test par comportement**, pas un test par méthode. Les noms décrivent
  le comportement : `test_returns_404_when_dataset_missing`, pas `test_get_1`.
- **Tests paramétrés** quand plusieurs cas testent la même logique (voir
  `libs/storage/tests/test_contract.py` pour le pattern).
- **Fixtures dans `conftest.py`** (pas de `pytest.fixture` dans les modules de
  test pour les fixtures partagées).
- **`pytest_addoption` dans `conftest.py`** (PAS dans les modules de test).
- **Aucune dépendance réseau** en CI. Les tests "live" (SMB, MQTT réel)
  doivent être `@pytest.mark.<thing>` et skippés sans option CLI.

### Stack de test recommandée

- `pytest` (déjà en place)
- `pytest-asyncio` pour les routes async
- `httpx.AsyncClient` + FastAPI `TestClient` pour les routes
- SQLite in-memory pour les tests DB unitaires (cf. `libs/schemas/tests/test_base.py`)
- `factory-boy` ou fixtures simples pour les entités

### Pattern : test d'intégration d'une route FastAPI

```python
# services/dataset/tests/test_routes_datasets.py
import pytest
from fastapi.testclient import TestClient
from vulis_dataset.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VULIS_STORAGE_BACKEND", "local-fs")
    monkeypatch.setenv("VULIS_STORAGE_LOCAL_ROOT", str(tmp_path))
    app = create_app()
    return TestClient(app)


def test_create_dataset_returns_201(client):
    resp = client.post("/api/v1/datasets", json={
        "tenant_id": "tenant_x",
        "project_id": "proj_y",
        "name": "my-dataset",
        "task_kind": "DETECTION",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-dataset"
    assert body["id"].startswith("ds_")
```

## 4. ruff / mypy / format

### Config racine (déjà posée)

- `target-version = "py311"`
- `line-length = 100`
- Rules : `E, F, I, B, UP, SIM, RUF`
- `tests/**` ignore `B017` (`pytest.raises(Exception)` autorisé)
- `libs/proto/src/vulis_proto/gen` exclu (code généré)

### Quand un agent ajoute un package

Le `pyproject.toml` du nouveau package doit contenir :

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
per-file-ignores = { "tests/**" = ["B017"] }

[tool.mypy]
python_version = "3.11"
strict = true                  # strict sur libs, plus souple possible sur services
warn_unused_ignores = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

### AVANT de commit

Toujours :

```bash
uv run ruff format src tests
uv run ruff check --fix src tests
uv run mypy src
uv run pytest -q
```

Si tu n'as pas `uv`/`ruff`/`mypy`/`pytest` dans le package, `uv sync --extra dev`
les installe via le workspace.

## 5. Conventions de nommage

- **Packages pip** : `vulis-<name>` (avec tiret). Package Python : `vulis_<name>`
  (avec underscore).
- **Tables DB** : `snake_case` pluriel (`projects`, `dataset_versions`).
- **Classes ORM** : `PascalCase` singulier (`Project`, `DatasetVersion`).
- **Routes** : `/api/v1/<resource-plural>` (`/datasets`, `/models`).
- **ID préfixes** : `proj_`, `ds_`, `dsv_`, `mdl_`, `mdlv_`, `line_`, `task_`,
  `camp_`, `edge_`, `tenant_`.
- **Migrations Alembic** : `NNNN_description_snake_case.py`, `revision` =
  `"NNNN"` (4 chiffres, pas d'hash).

## 6. Logging / observabilité par service

Chaque service appelle :

```python
from vulis_core import init_logging
from vulis_obs import init_observability

init_logging(service="dataset", level=settings.log_level, fmt=settings.log_format)
init_observability(
    service="dataset",
    endpoint=settings.otel_endpoint,
    surface=settings.surface,
    environment=settings.environment,
)
```

Et dans chaque endpoint :

```python
from vulis_core import get_logger, bind_context
from vulis_obs import span

log = get_logger(__name__)

@router.post("/datasets")
async def create_dataset(req, session=Depends(get_session), user=Depends(get_current_user)):
    with span("dataset.create", **{"vulis.tenant_id": user.tenant_id}):
        with bind_context(tenant_id=user.tenant_id):
            log.info("dataset.creating", name=req.name)
            ...
```

## 7. RBAC / multi-tenant

- **Tenant = Keycloak realm**. Chaque requête authentifiée porte un token
  OIDC avec `tenant_id` claim.
- **Rôles** : `admin`, `data-scientist`, `annotator`, `operator`, `reviewer`.
  Les endpoints déclarent `Depends(require_role("admin"))` ou similaire.
- **Isolation** : chaque query porte `WHERE tenant_id = :tenant_id`. Pas de
  cross-tenant sauf admin explicite.
- **Audit trail** : chaque mutation (POST/PUT/DELETE) écrit une ligne dans
  `audit_events` (actor, action, target_type, target_id, diff JSON).

## 8. Storage — comment l'utiliser dans un service

```python
from vulis_storage import build_from_settings
from vulis_core import get_settings

def get_storage() -> StorageBackend:
    # En prod : settings.storage_backend == "smb-protocol"
    # En dev/test : settings.storage_backend == "local-fs"
    return build_from_settings(get_settings())

# Dans un endpoint :
storage = Depends(get_storage)
key = storage.put_blob(image_bytes)  # → "sha256/abc..."
manifest["samples"].append({"key": key, "label": "defect"})
storage.put_bytes(f"manifests/{version_id}.json", json.dumps(manifest).encode())
```

**Jamais** d'appel `open()` direct sur un chemin partagé. Si tu lis un
fichier de config local au service, OK ; si c'est une image, un modèle,
un manifeste, un dataset → storage backend.

## 9. Migrations Alembic

- Une migration par PR qui change le schéma.
- **Toujours** tester la migration avec `alembic upgrade head` puis
  `alembic downgrade -1` puis `alembic upgrade head` (round-trip).
- Les triggers Postgres doivent être ajoutés/supprimés dans la même migration
  (voir `0001_initial.py` pour le pattern).

## 10. Documentation par package

Chaque `services/<name>/README.md` contient :

1. Scope du service (1 paragraphe).
2. Quick start (`uv sync && uv run uvicorn vulis_<name>.main:app`).
3. Variables d'env (les `VULIS_<NAME>_*`).
4. Sommaire de l'API (lien vers `/docs` OpenAPI auto-généré).
5. Où sont les tests + comment les lancer.

## 11. Anti-patterns à proscrire

- ❌ Instance `FastAPI()` module-level. **Toujours** une factory `create_app()`.
- ❌ `open(path)` sur un blob partagé. **Toujours** le `StorageBackend`.
- ❌ ID en string brute sans type (`str` au lieu de `DatasetId`). Utiliser
  les types `vulis_core`.
- ❌ `print()` pour log. **Toujours** `get_logger(__name__)`.
- ❌ `datetime.now()` sans tz. **Toujours** tz-aware (UTC).
- ❌ `time.sleep()` dans les tests. Utiliser des fixtures de cycle de vie.
- ❌ Magic strings pour les enums. Utiliser des `enum.StrEnum` ou `Literal`.
- ❌ Backslash dans une f-string (Python 3.11 interdit). Concaténation à la place.
