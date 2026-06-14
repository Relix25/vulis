# 02 — État du code maintenant

Ce document décrit **exactement** ce qui existe au moment du handoff (fin M1.1).
Utilise-le comme référence : si un agent propose d'ajouter quelque chose qui
existe déjà, pointe-le ici.

## 1. Structure du monorepo

```
vulis/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # matrix Linux+Win × Py 3.11/3.12, DCO, reuse, lint+test
│   │   ├── changeset-check.yml    # vérifie qu'une PR touchant un package a un changeset
│   │   └── docs.yml               # build + déploiement MkDocs sur GitHub Pages
│   ├── ISSUE_TEMPLATE/            # bug_report.md, feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml             # pip (par package), github-actions, docker
│
├── .gitignore, .editorconfig, .gitattributes
├── pyproject.toml                 # workspace uv racine
├── Taskfile.yml                   # runner unifié (task install / up / test / check)
├── CODEOWNERS, REUSE.toml
│
├── LICENSE                        # BSL 1.1
├── NOTICE                         # attributions + 3rd-party
├── LICENSES/
│   ├── LicenseRef-Vulis-BSL-1.1.txt
│   └── AGPL-3.0-only.txt
│
├── README.md, CONTRIBUTING.md, GOVERNANCE.md, ARCHITECTURE.md, SECURITY.md
├── mkdocs.yml
│
├── ADR/
│   ├── README.md                  # index
│   ├── 0000-template.md
│   └── 0001-license.md ... 0010-air-gap-git-mirror.md
│
├── docs/
│   ├── index.md
│   ├── architecture.md
│   ├── licensing.md
│   ├── contributing.md, governance.md, security.md
│   ├── getting-started/ (quick-start.md, concepts.md)
│   ├── adr/index.md
│   └── handoff/  ← ce dossier
│
├── docker/compose/
│   ├── docker-compose.dev.yml     # Postgres 16, Mosquitto 2, Redis 7, Keycloak 25
│   ├── mosquitto/mosquitto.conf   # MQTT 5, anon OK (dev), Sparkplug-ready
│   └── keycloak/realms/           # placeholder (realm export à ajouter en M1.2)
│
├── libs/
│   ├── core-py/      ← exceptions, types, config, logging
│   ├── storage/      ⭐ StorageBackend + backends
│   ├── obs-py/       ← OpenTelemetry wrapper + métriques vulis.*
│   ├── proto/        ← protobuf schemas + buf config
│   └── schemas/      ← SQLAlchemy Base + Alembic
│
├── services/         ← VIDE pour l'instant (M1.3+)
├── apps/             ← VIDE (M1.7)
├── tools/            ← VIDE (M1.8)
├── tests/            ← VIDE (intégration cross-services, plus tard)
└── changes/          ← VIDE (changesets, alimenté à chaque PR)
```

## 2. Les 5 libs partagées

Chaque lib est pip-installable indépendamment, mais liées via le workspace
uv (cf. `pyproject.toml` racine).

### 2.1 `libs/core-py` — `vulis_core`

**Dépendances runtime :** `pydantic>=2.6`, `pydantic-settings>=2.2`, `structlog>=24.1`.

**API publique :**

```python
from vulis_core import (
    # Config
    VulisSettings,         # BaseSettings avec prefix VULIS_
    get_settings,          # cached, appelle cache_clear() en tests

    # Exceptions
    VulisError,            # base
    NotFoundError, AlreadyExistsError, ConflictError, ValidationError,
    UnauthorizedError, ForbiddenError,
    StorageError, ObjectNotFoundError, ChecksumMismatchError,
    RegistryError, InvalidTransitionError,
    ExternalServiceError,  # service=, upstream_error= kwargs

    # Logging
    init_logging,          # init_logging(service=, level=, fmt=, force=)
    get_logger,            # get_logger(name=None, **binds)
    bind_context,          # cm: bind_context(project_id=..., line_id=...)
    get_correlation_id, set_correlation_id,

    # Types
    EntityId,              # base class avec .prefix classvar
    ProjectId, LineId, TaskId,
    DatasetId, DatasetVersionId,
    ModelId, ModelVersionId,
    CampaignId, EdgeId, TenantId,
    SemVer,                # SemVer.parse("1.2.3"), SemVer.parse("1.0.0-alpha")
    ParseError,
)
```

**Points clés à retenir :**

- Tous les IDs ont un préfixe (`ProjectId` → `"proj_<uuid>"`). Utilise
  `ProjectId.new()`, `ProjectId.from_string("proj_abc")`, `ProjectId.try_parse()`.
- Les IDs sont **frozen dataclass**, hashables, comparables entre eux par UUID.
  Deux IDs de types différents avec le même UUID ne sont **pas égaux**
  (`ProjectId(u) != DatasetId(u)`).
- `SemVer` implémente SemVer 2.0.0 §11 (pré-release < release, build metadata
  ignoré pour l'ordre). Ne pas utiliser l'`order=True` du dataclass : l'ordre
  custom via `_sort_key()` est la source de vérité.
- `VulisSettings` : prefix `VULIS_`, champs principaux `surface`, `service_name`,
  `environment`, `log_level`, `storage_backend`, `postgres_dsn`, `mqtt_*`,
  `keycloak_*`, etc. `masked_dump()` retourne secrets masqués (***).
- `init_logging()` est **idempotent** sauf si `force=True`. Le factory
  `PrintLoggerFactory()` (sans arg) résout `sys.stdout` lazily — **ne pas**
  passer `file=sys.stdout` au factory (ça casse le capture pytest).
- `bind_context()` est async-safe (ContextVar), nestable, scoped au `with`.

**Tests :** `libs/core-py/tests/test_exceptions.py`, `test_types.py`,
`test_logging_config.py` — 56 tests, tous au vert.

---

### 2.2 `libs/storage` — `vulis_storage` ⭐

**Dépendances runtime :** `vulis-core-py`, `smbprotocol>=1.15`, `pydantic>=2.6`.

**API publique :**

```python
from vulis_storage import (
    # Types
    StorageBackend,        # Protocol (runtime_checkable)
    ObjectInfo,            # dataclass: key, size, last_modified, etag, content_type, metadata
    BackendConfig,         # dataclass frozen: backend, smb_*, local_root, s3_*, root_prefix

    # Backends concrets
    LocalFSBackend,        # backend="local-fs", défaut dev/tests
    SmbProtocolBackend,    # backend="smb-protocol", DÉFAUT production
    SmbMountBackend,       # backend="smb-mount", option perf (montage OS)
    S3Backend,             # backend="s3", STUB (lève StorageError à l'init)

    # Factory
    build_backend,         # build_backend(BackendConfig) → StorageBackend
    build_from_settings,   # build_from_settings(VulisSettings) → StorageBackend

    # Helpers (publics)
    normalize_key,         # POSIX-normalize une clé (résout . et ..)
    hash_bytes,            # sha256 (ou autre algo) de bytes
    hash_stream,           # idem pour un stream (64KB chunks)
    content_addressed_key, # "sha256/<hex>" à partir d'un digest
)
```

**Contrat `StorageBackend` (Protocol) :**

```python
class StorageBackend(Protocol):
    kind: str
    # writes
    def put_bytes(self, key: str, data: bytes, *, overwrite: bool = True) -> str: ...
    def put_stream(self, key: str, stream: IO[bytes], *, overwrite: bool = True) -> str: ...
    def put_blob(self, data: bytes, *, algo: str = "sha256") -> str: ...  # content-addressed
    # reads
    def get_bytes(self, key: str) -> bytes: ...
    def get_stream(self, key: str) -> IO[bytes]: ...
    # metadata
    def stat(self, key: str) -> ObjectInfo: ...
    def exists(self, key: str) -> bool: ...
    # listing
    def list(self, prefix: str = "", *, recursive: bool = True) -> Iterator[ObjectInfo]: ...
    # deletion
    def delete(self, key: str) -> None: ...   # idempotent
    # lifecycle
    def close(self) -> None: ...
```

**Points clés :**

- **Keys sont POSIX-style** (forward slashes), indépendamment de l'OS. Les
  backends traduisent en natif (backslash pour SMB).
- **put_blob** est content-addressed : hash → `"<algo>/<hex>"`, idempotent.
- **delete est idempotent** : supprimer une clé absente ne lève pas.
- **ObjectNotFoundError** lève sur `stat`/`get_*` d'une clé absente (c'est une
  sous-classe de `StorageError` ET `NotFoundError`).
- **Le contrat est testé une fois pour tous les backends** dans
  `tests/test_contract.py` (paramétré). Pour ajouter un backend, ajoute un
  tuple à `BACKENDS` en haut du fichier.
- **Tests SMB live** sont skippés sans `--smb-host/--smb-share/--smb-user/--smb-pass`
  (ou env vars `VULIS_SMB_*`). Les options CLI sont déclarées dans `conftest.py`
  (PAS dans le module de test — sinon pytest ne les trouve pas).

**100 tests + 5 skipped.**

---

### 2.3 `libs/obs-py` — `vulis_obs`

**Dépendances runtime :** `vulis-core-py`, `opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-grpc`.

**API publique :**

```python
from vulis_obs import (
    # Setup
    init_observability,    # init_observability(service=, endpoint=, surface=, force=)
    is_initialized,
    set_global_attribute,  # bind un attr par défaut à tous les spans futurs
    global_attributes,

    # Tracing
    span,                  # cm: with span("op.name", **attrs): ...
    meter,                 # alias de span (pour le README)
    current_span,
    set_span_attribute,

    # Metrics
    counter,               # counter("vulis.dataset.samples_imported")
    histogram,             # histogram("vulis.serving.inference_seconds")
    up_down_counter,
    PREDEFINED,            # dict name → (kind, unit, description)
)
```

**Points clés :**

- `init_observability(endpoint=None)` → no-op provider (sûr pour CLI/tests).
- `counter(name)` cherche `name` dans `PREDEFINED` pour récupérer unit/description,
  sinon utilise les kwargs. Noms custom autorisés.
- Toutes les méthodes attrapent silencieusement en l'absence d'OTel (pas de crash).
- `span()` est un context manager qui merge `global_attributes()` avec les
  attrs passés.
- **API OTel réelle** : `counter.add(n, attributes={...})` — PAS
  `counter.add(n, key=value)` (kwargs ne marchent pas).

**15 tests.**

---

### 2.4 `libs/proto` — `vulis_proto`

**Dépendances runtime :** `grpcio`, `protobuf`.

**Schemas `.proto` définis** (sous `proto/vulis/<domain>/v1/`) :

- `common.proto` — `EntityId`, `SemVer`, `TaskKind`, `Surface`, `Error`,
  `PageRequest`/`PageResponse`.
- `project.proto` — `Project`, `Line`, `Task`, `Phase`, `TaskState`,
  `ProjectService` (CreateProject, GetProject, ListProjects, UpdateProject,
  DeleteProject, CreateLine, ListLines, CreateTask, ListTasks, TransitionTask).
- `dataset.proto` — `Dataset`, `DatasetVersion`, `Sample`, `Split`,
  `DatasetService` (CreateDataset, GetDataset, ListDatasets, CreateVersion,
  GetVersion, ListVersions, GetManifest, AddSamples (client streaming),
  PublishVersion).
- `model.proto` — `Model`, `ModelVersion`, `OnnxTensorSpec`, `ModelStatus`,
  `ModelRegistryService` (CreateModel, GetModel, ListModels, UploadVersion
  (client streaming), GetVersion, ListVersions, PromoteVersion, GetModelCard).

**Codegen :** `buf.gen.yaml` configuré pour Python + gRPC (Go commenté pour
plus tard). **Pas encore généré** — le package `vulis_proto` est vide côté
Python stubs. La première fois qu'un service en a besoin, lancer
`buf generate` (ou protoc équivalent).

**Points clés :**

- Tous les `EntityId` sont passés en string sur le wire (forme préfixée).
- Les versions (`SemVer`) sont des messages, pas des strings.
- Les messages streaming client→serveur (UploadVersion, AddSamples)
  utilisent un `oneof payload` : premier message = metadata, suivants = chunks.
- `buf.yaml` + `buf.gen.yaml` à la racine de `libs/proto/`.

---

### 2.5 `libs/schemas` — `vulis_schemas`

**Dépendances runtime :** `vulis-core-py`, `SQLAlchemy>=2.0`, `alembic>=1.13`,
`psycopg[binary]>=3.1`.

**API publique :**

```python
from vulis_schemas import (
    Base,                  # DeclarativeBase partagé
    VulisMetaData,         # MetaData avec naming convention Vulis
    NamingConvention,      # dict: ix/uq/ck/fk/pk
    UUIDPrimaryKey,        # mixin: id String(64) PK
    TenantScoped,          # mixin: tenant_id String(64) FK→tenants
    Timestamped,           # mixin: created_at, updated_at (tz-aware)
    SoftDelete,            # mixin: deleted_at nullable
)
```

**Tables partagées** (créées par `alembic upgrade head`) :

- `tenants(id PK, display_name, created_at, keycloak_realm)`
- `audit_events(id PK, tenant_id FK, actor, action, target_type, target_id,
  diff, correlation_id, occurred_at)` — **append-only** : trigger PG
  `vulis_block_audit_mutation` lève sur UPDATE/DELETE.

**Alembic :**

- Config : `libs/schemas/alembic.ini`, env dans `alembic/env.py`.
- URL résolue dans cet ordre : `--x url=` CLI > `SQLALCHEMY_URL` env >
  `VULIS_POSTGRES_DSN` env.
- `target_metadata = Base.metadata`.
- Migration `0001_initial.py` : crée `tenants` + `audit_events` + triggers
  anti-mutation + indexes.
- **Pour ajouter une migration** : `alembic revision --autogenerate -m "add projects"`
  puis éditer (autogenerate n'est pas parfait, surtout pour les triggers).

**Points clés :**

- La **naming convention** est dans `VulisMetaData`, attachée à `Base.metadata`.
  Toutes les FK/PK/UQ/CK suivent `fk_<table>_<col>_<reftable>` etc.
- `Base.metadata.create_all(engine)` crée toutes les tables déclarées,
  **y compris les mixins-referenced** (`tenants` doit exister pour que
  `TenantScoped` fonctionne).
- Les services ajoutent leurs modèles en important `Base` depuis
  `vulis_schemas` et en déclarant des classes ORM. Alembic voit ces classes
  si elles sont importées avant `target_metadata`.

## 3. Comment installer / tester

```bash
# Toutes les commandes à lancer depuis la racine du monorepo.

# Installer toutes les libs (workspace uv)
task install                          # ou : uv sync --all-packages

# Installer une lib seule avec ses dev deps
cd libs/core-py
uv sync --extra dev

# Lancer les tests d'une lib
uv run pytest -q

# Lancer ruff sur une lib
uv run ruff check src tests
uv run ruff format --check src tests

# Lancer toute la suite qualité
task check                            # lint + format-check + typecheck + test + reuse

# Démarrer la stack dev (Postgres, Mosquitto, Redis, Keycloak)
task up
task logs                             # suivre les logs
task down                             # arrêter (keep volumes)
task down-v                           # arrêter + supprimer volumes (destructif)
```

**Outils requis :**

- Python 3.11+ (3.11 et 3.12 testés en CI)
- [uv](https://docs.astral.sh/uv/) (gestionnaire de paquets)
- [Task](https://taskfile.dev) (runner) — `winget install Task.Task` sur Windows
- Docker (ou équivalent compatible `docker compose`)

## 4. Ce qui n'existe PAS encore

À ne pas supposer existant :

- ❌ Aucun service dans `services/` (vide)
- ❌ Aucune app dans `apps/` (vide)
- ❌ Aucun outil dans `tools/` (vide, dont `vulis-cli`)
- ❌ Pas de `docker-compose.platform.yml` (juste le `dev`)
- ❌ Pas de realm Keycloak exporté
- ❌ Pas de codegen protobuf (juste les `.proto`)
- ❌ Pas de CI qui build des images Docker
- ❌ Pas de signature SIGSTORE/cosign
- ❌ Pas de CVAT intégré
- ❌ Pas de miroir Git local serveur (outils à venir)

## 5. Bugs déjà corrigés (à ne pas réintroduire)

Voir `05-pitfalls.md` pour le détail. En résumé :

1. `SemVer` ordering custom (ne pas utiliser `order=True` du dataclass).
2. `PrintLoggerFactory()` sans arg (lazy stdout) — ne pas passer `file=`.
3. Pas de backslash dans les f-strings en Python 3.11.
4. `pytest_addoption` dans `conftest.py`, pas dans les modules de test.
5. `naming_convention` sur `MetaData`, pas sur `registry`.
6. `ruff B017` : `pytest.raises(Exception)` trop large → ignoré dans `tests/**`
   via `per-file-ignores` (légitime pour tester "n'importe quelle exception").
