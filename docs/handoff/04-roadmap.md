# 04 — Roadmap détaillée M1.2 → M1.8

Ce document est le **cahier des charges** des prochaines étapes. Chaque
milestone a : objectif, modèles de données, signatures d'API, critère de fin,
dépendances. Les autres agents doivent s'y référer pour ne pas dévier.

> **Rappel de l'ordre des dépendances :** M1.2 (plateforme) → M1.3 (project-api)
> → M1.4 (dataset) ⭐ → M1.5 (registry) ⭐ → M1.6 (gateway+fleet) → M1.7 (UI)
> → M1.8 (CLI relay).
>
> Le critère de fin global de M1 : depuis la workstation (CLI ou app Tauri
> amorcée), créer un projet, importer un dataset (stocké sur share SMB via
> smbprotocol), enregistrer un modèle ONNX validé, suivre son approval — avec
> audit trail complet. Webapp serveur expose la même chose. Fleet Manager
> liste les edge mockés et lit les heartbeats MQTT.

---

## M1.2 — Plateforme serveur (B10)

**Objectif :** un `docker-compose.platform.yml` complet qui démarre tout le
backend central de façon reproductible.

### Services à mettre en place

```yaml
# docker/compose/docker-compose.platform.yml
services:
  postgres:      # Postgres 16-alpine, schéma vulis, user/password via .env
  mosquitto:     # Mosquitto 2, config Sparkplug-ready, auth par user/pass
  redis:         # Redis 7-alpine
  keycloak:      # Keycloak 25, OIDC, realm "vulis" importé
  traefik:       # reverse proxy, auto-discovery, TLS-terminator (self-signed en dev)
  alembic:       # one-shot: alembic upgrade head avant les autres services
```

### Realm Keycloak à exporter

Le fichier `docker/compose/keycloak/realms/vulis-realm-dev.json` doit contenir :

- **Realm** `vulis`.
- **5 rôles** : `admin`, `data-scientist`, `annotator`, `operator`, `reviewer`.
- **5 utilisateurs dev** (un par rôle, password = nom du rôle) :
  `admin/admin`, `data-scientist/data-scientist`, etc.
- **3 clients OIDC** :
  - `vulis-web` (public, PKCE) pour la webapp React.
  - `vulis-tauri` (public, PKCE, redirect localhost) pour l'app Tauri.
  - `vulis-cli` (confidential, client_credentials) pour le CLI machine-to-machine.
- **Groupes** : `tenants/<tenant-name>` pour modéliser le multi-tenant.
  En dev, un seul tenant `default`.

Pour produire le realm :

```bash
task up
# Aller sur http://localhost:8080, admin/admin, créer le realm + rôles + users + clients
# Exporter:
docker compose -f docker/compose/docker-compose.dev.yml exec keycloak \
  /opt/keycloak/bin/kc.sh export --realm vulis \
  --dir /opt/keycloak/data/import --users realm_file
# Copier le JSON dans docker/compose/keycloak/realms/
```

### Script d'init

`docker/compose/init-platform.sh` (bash + Windows-compatible via WSL) :

1. Attend que Postgres soit sain.
2. Crée la DB `vulis` si absente.
3. Lance `alembic upgrade head` (depuis `libs/schemas/`).
4. Crée les buckets MinIO… ah non, on est en SMB. Skip.
5. Attend que Keycloak soit sain.
6. Vérifie que le realm `vulis` est importé.
7. Affiche un récap (URLs, users de dev).

### Variables d'env (template `.env.example`)

```env
VULIS_SURFACE=server
VULIS_ENVIRONMENT=dev
VULIS_POSTGRES_DSN=postgresql://vulis:vulis@postgres:5432/vulis
VULIS_REDIS_URL=redis://redis:6379/0
VULIS_MQTT_HOST=mosquitto
VULIS_MQTT_PORT=1883
VULIS_KEYCLOAK_URL=http://keycloak:8080
VULIS_KEYCLOAK_REALM=vulis
VULIS_STORAGE_BACKEND=smb-protocol
VULIS_STORAGE_SMB_HOST=nas.plant.local
VULIS_STORAGE_SMB_SHARE=vulis
VULIS_STORAGE_SMB_USERNAME=vulis
VULIS_STORAGE_SMB_PASSWORD=changeme
VULIS_STORAGE_LOCAL_ROOT=/data/vulis  # fallback dev
VULIS_OTEL_ENDPOINT=                  # vide en dev
```

### Critère de fin M1.2

- `task up platform` démarre tous les services, healthchecks OK.
- `alembic upgrade head` s'applique sans erreur.
- On peut se logguer à Keycloak avec `admin/admin`, voir le realm `vulis`.
- Le broker Mosquitto accepte une connexion anonyme (dev) et publie/subscribe
  un message de test (`mosquitto_pub` / `mosquitto_sub`).
- Le SMB share est accessible depuis le compose (test: écriture d'un fichier
  via `smbclient`).

### Dépendances

- `libs/schemas` (déjà en place) pour les migrations.

---

## M1.3 — Gestion projet/workflow (B7)

**Objectif :** service `services/project-api/` qui gère les entités
`Project`, `Line`, `Task`, `Campaign` + audit trail + RBAC.

### Modèle de données (SQLAlchemy)

```python
# services/project-api/src/vulis_project/models.py
from sqlalchemy import String, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from vulis_schemas import Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete
import enum


class Phase(str, enum.Enum):
    POC = "POC"
    PILOT = "PILOT"
    PRE_PROD = "PRE_PROD"
    PROD = "PROD"
    ARCHIVED = "ARCHIVED"


class TaskKind(str, enum.Enum):
    DETECTION = "DETECTION"
    CLASSIFICATION = "CLASSIFICATION"
    SEGMENTATION = "SEGMENTATION"


class TaskState(str, enum.Enum):
    BACKLOG = "BACKLOG"
    IN_PROGRESS = "IN_PROGRESS"
    IN_VALIDATION = "IN_VALIDATION"
    DEPLOYED = "DEPLOYED"
    MONITORING = "MONITORING"
    RETRAINING = "RETRAINING"


class Project(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    phase: Mapped[Phase] = mapped_column(SAEnum(Phase), default=Phase.POC)
    # tags en JSONB
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)
    lines: Mapped[list["Line"]] = relationship(back_populates="project")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Line(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "lines"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Liste d'edge_ids en JSONB (ou table associatives plus tard)
    edge_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    project: Mapped["Project"] = relationship(back_populates="lines")


class Task(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "tasks"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[TaskKind] = mapped_column(SAEnum(TaskKind), nullable=False)
    state: Mapped[TaskState] = mapped_column(SAEnum(TaskState), default=TaskState.BACKLOG)
    project: Mapped["Project"] = relationship(back_populates="tasks")


class Campaign(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "campaigns"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64))  # data_collection|validation|pilot|ab
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # ...
```

### Migration Alembic `0002_projects.py`

Crée `projects`, `lines`, `tasks`, `campaigns` + FK + indexes sur
`(tenant_id, project_id)`. Penser aux FK vers `tenants`.

### API REST

```
POST   /api/v1/projects                       → 201 Project
GET    /api/v1/projects?project_id=...        → 200 Project[]
GET    /api/v1/projects/{id}                  → 200 Project
PATCH  /api/v1/projects/{id}                  → 200 Project        (partial update)
DELETE /api/v1/projects/{id}                  → 204                (soft delete)

POST   /api/v1/projects/{pid}/lines           → 201 Line
GET    /api/v1/projects/{pid}/lines           → 200 Line[]

POST   /api/v1/projects/{pid}/tasks           → 201 Task
GET    /api/v1/projects/{pid}/tasks           → 200 Task[]
POST   /api/v1/tasks/{tid}:transition         → 200 Task           (state machine)

POST   /api/v1/projects/{pid}/campaigns       → 201 Campaign
GET    /api/v1/projects/{pid}/campaigns       → 200 Campaign[]
```

### State machine des Tasks

```
BACKLOG ──start──► IN_PROGRESS ──submit──► IN_VALIDATION
                       ▲                        │
                       │                        ├──approve──► DEPLOYED
                       │                        │                │
                       └──reject────────────────┘                │
                                                                  ▼
                                                              MONITORING
                                                                  │
                                                                  ▼
                                                              RETRAINING
                                                                  │
                                                                  └─► IN_PROGRESS
```

Toute transition interdit par la state machine → `InvalidTransitionError`.

### Audit trail

Helper à créer dans `services/project-api/src/vulis_project/audit.py` :

```python
def log_audit(
    session: Session,
    *,
    tenant_id: str,
    actor: str,
    action: str,           # "project.create", "task.transition", ...
    target_type: str,      # "project", "task", ...
    target_id: str,
    diff: dict | None = None,
    correlation_id: str | None = None,
) -> None:
    session.execute(
        audit_events_table.insert().values(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            diff=json.dumps(diff) if diff else None,
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
        )
    )
```

À appeler après chaque mutation réussie, dans la même transaction.

### RBAC

- `require_role(*roles)` dependency qui vérifie le rôle Keycloak.
- `admin` : tout.
- `data-scientist` : create/update projects, tasks, campaigns, transitions.
- `annotator` : lecture seule sur projects/tasks.
- `operator` : transitions de task (deployed → monitoring).
- `reviewer` : validations (transition `in_validation → deployed`).

### Critère de fin M1.3

- `task up platform && uv run uvicorn vulis_project.main:app --reload` démarre le service.
- `POST /api/v1/projects` crée un projet (audit trail écrit).
- `GET /api/v1/projects` liste avec pagination.
- Les transitions de task respectent la state machine.
- Tout endpoint non authentifié → 401 ; mauvais rôle → 403.
- Coverage ≥ 70% sur `services/project-api/`.

### Dépendances

- `libs/core-py`, `libs/schemas`, `libs/obs-py` (déjà en place).
- **Pas de dépendance** vers M1.4/M1.5 (project-api est autonome).

---

## M1.4 — Dataset (B2) ⭐ CŒUR

**Objectif :** service `services/dataset/` qui gère datasets versionnés avec
manifestes content-addressed stockés via `libs/storage`.

### Modèle de données

```python
class Dataset(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    __tablename__ = "datasets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    task_kind: Mapped[TaskKind] = mapped_column(SAEnum(TaskKind), nullable=False)
    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset")


class DatasetVersion(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "dataset_versions"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    major: Mapped[int]
    minor: Mapped[int]
    patch: Mapped[int]
    is_published: Mapped[bool] = mapped_column(default=False)
    manifest_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # sha256 of the manifest JSON; null tant que la version est en draft
    manifest_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sample_count: Mapped[int] = mapped_column(default=0)
    size_bytes: Mapped[int] = mapped_column(default=0, BigInteger)
    created_by: Mapped[str] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
    __table_args__ = (
        UniqueConstraint("dataset_id", "major", "minor", "patch",
                         name="uq_dataset_versions_semver"),
    )


class Sample(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "dataset_samples"
    version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    blob_key: Mapped[str] = mapped_column(String(512))   # storage key (content-addressed)
    relative_path: Mapped[str] = mapped_column(String(1024))
    annotation_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    split: Mapped[Split] = mapped_column(SAEnum(Split), default=Split.TRAIN)
    # sha256 du contenu (pour dédup + intégrité)
    blob_digest: Mapped[str] = mapped_column(String(128))
```

### Versioning type DVC

- Une `DatasetVersion` en draft accumule des `Sample`s.
- À `PublishVersion`, on calcule le manifeste JSON :

  ```json
  {
    "version": "1.2.0",
    "dataset_id": "ds_abc",
    "samples": [
      {"key": "sha256/...", "path": "train/img_001.png", "label": "ok", "split": "train"},
      ...
    ]
  }
  ```

- Le manifeste est hashé (`sha256`) et stocké via `storage.put_blob(manifest_bytes)`
  → `manifest_key = "sha256/<hash>"`, `manifest_digest = <hash>`.
- `is_published = True`. La version devient immuable.
- Pour recréer une version identique : on peut vérifier que
  `sha256(manifest) == manifest_digest`.

### Import

Sources supportées en M1.4 :

1. **Dossier local** (sur le serveur) : `POST /api/v1/datasets/{id}/versions/{vid}/import`
   avec `{"source": "local", "path": "/data/raw/mydataset"}`. Le service parcourt,
  upload chaque fichier via `storage.put_blob`, crée les Samples.
2. **Archive ZIP** uploadée : `POST .../import` avec multipart file.
3. **Export CVAT** : JSON 1.1 (à parser). Pas de connexion directe à CVAT avant M8.
4. **Bucket S3** : `{"source": "s3", "endpoint": "...", "bucket": "...", "prefix": "..."}`.
   (Optional — peut être M1.5+ si trop long.)

### Splits

- **Manuel** : `POST .../samples/{id}` avec `{"split": "VAL"}`.
- **Stratifié** : `POST .../versions/{vid}:split` avec
  `{"strategy": "stratified", "ratios": {"train": 0.7, "val": 0.15, "test": 0.15},
   "stratify_by": "label"}`.

### API REST

```
POST   /api/v1/datasets                              → 201 Dataset
GET    /api/v1/datasets?project_id=...               → 200 Dataset[]
GET    /api/v1/datasets/{id}                         → 200 Dataset

POST   /api/v1/datasets/{id}/versions                → 201 DatasetVersion (draft)
GET    /api/v1/datasets/{id}/versions                → 200 DatasetVersion[]
GET    /api/v1/datasets/{id}/versions/{vid}          → 200 DatasetVersion
GET    /api/v1/datasets/{id}/versions/{vid}/manifest → 200 Manifest

POST   /api/v1/datasets/{id}/versions/{vid}/import   → 202 {job_id}   (async)
GET    /api/v1/import-jobs/{job_id}                  → 200 ImportJob

POST   /api/v1/datasets/{id}/versions/{vid}:split    → 200 DatasetVersion
POST   /api/v1/datasets/{id}/versions/{vid}:publish  → 200 DatasetVersion (immutable)
```

### Async pour les imports bulk

Les imports peuvent prendre du temps (des milliers d'images). Pattern :

1. `POST /import` crée un `ImportJob` en DB (status=`pending`), renvoie 202 + `job_id`.
2. Un worker (peut être simple : `asyncio.create_task` ou un process séparé)
   traite le job, update le status en `running` puis `done`/`failed`.
3. Le client poll `GET /import-jobs/{job_id}`.
4. À terme (M2+) : utiliser NATS ou Celery pour la file. Pour M1.4, un worker
   in-process suffit.

### Métriques OTel à émettre

```python
from vulis_obs import counter, histogram

counter("vulis.dataset.samples_imported").add(n, attributes={"dataset_id": ...})
histogram("vulis.dataset.import_seconds").record(elapsed)
histogram("vulis.dataset.size_bytes").record(total_bytes)
counter("vulis.storage.write_bytes").add(total_bytes)
```

### Critère de fin M1.4

- Je peux créer un dataset, créer une version draft, importer un dossier
  de ~100 images, publier la version.
- Le manifeste est retrouvable, hash vérifié.
- Les Samples sont stockés via `storage.put_blob` (content-addressed).
- Re-publier une version déjà publiée → 409.
- Coverage ≥ 70%.

### Dépendances

- `libs/storage` (déjà en place).
- M1.3 (project-api) : `Dataset.project_id` FK vers `projects`.

---

## M1.5 — Model Registry (B2) ⭐ CŒUR

**Objectif :** service `services/registry/` qui gère modèles + versions ONNX
+ workflow d'approval industriel.

### Modèle de données

```python
class Model(Base, UUIDPrimaryKey, TenantScoped, Timestamped, SoftDelete):
    __tablename__ = "models"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    task_kind: Mapped[TaskKind] = mapped_column(SAEnum(TaskKind), nullable=False)
    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model")


class ModelStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    STAGING = "STAGING"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"


class ModelVersion(Base, UUIDPrimaryKey, TenantScoped, Timestamped):
    __tablename__ = "model_versions"
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), nullable=False)
    major: Mapped[int]
    minor: Mapped[int]
    patch: Mapped[int]
    status: Mapped[ModelStatus] = mapped_column(SAEnum(ModelStatus), default=ModelStatus.DRAFT)
    artifact_key: Mapped[str] = mapped_column(String(512))           # storage key ONNX
    artifact_digest: Mapped[str] = mapped_column(String(128))        # sha256 ONNX
    artifact_size_bytes: Mapped[int] = mapped_column(BigInteger)
    trained_on_dataset_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    onnx_opset: Mapped[int]
    model_card: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    model: Mapped["Model"] = relationship(back_populates="versions")
    __table_args__ = (
        UniqueConstraint("model_id", "major", "minor", "patch",
                         name="uq_model_versions_semver"),
    )


class OnnxTensorSpec(Base, UUIDPrimaryKey):
    __tablename__ = "model_onnx_specs"
    version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    direction: Mapped[str]  # "input" | "output"
    name: Mapped[str]
    dtype: Mapped[str]
    shape: Mapped[list[int]] = mapped_column(JSONB)  # [-1, 3, 224, 224]
```

### Workflow d'approval (state machine)

```
DRAFT ──submit_for_review──► INTERNAL_REVIEW
                                 │
       ┌──approve─────────────────┴──reject──► REJECTED
       │                                        ▲
       ▼                                        │
    STAGING ──approve──► APPROVED               │
       │                    │                   │
       │                    ├──deploy──► DEPLOYED
       │                    │                │
       └──reject────────────┘                │
                                              ▼
                                          ARCHIVED ◄──archive
```

Transitions controlées par rôle :

- `data-scientist` : `DRAFT → INTERNAL_REVIEW`.
- `reviewer` : `INTERNAL_REVIEW → STAGING | REJECTED`.
- `reviewer` : `STAGING → APPROVED | REJECTED`.
- `operator` ou `admin` : `APPROVED → DEPLOYED`.
- `admin` : `* → ARCHIVED`.

Chaque transition → `InvalidTransitionError` si hors state machine, + log audit.

### Upload ONNX (streaming)

Endpoint streaming (gRPC) ou chunked HTTP. En REST pour M1.5 :

```
POST /api/v1/models/{id}/versions:upload   (multipart/form-data, fields: file + metadata)
```

1. Reçoit le fichier en stream, le passe à `storage.put_stream(key, stream)`.
2. Calcule le sha256 à la volée.
3. Valide l'ONNX avec `onnx.load` (opset, shapes, metadata).
4. Crée le `ModelVersion` (status DRAFT) + `OnnxTensorSpec`s.
5. Stocke l'artifact_key = `"sha256/<hash>"`.

### Validation ONNX (helpers à écrire)

```python
# services/registry/src/vulis_registry/onnx_validate.py
import onnx
from onnx import shape_inference

def validate_onnx(data: bytes) -> OnnxMetadata:
    model = onnx.load_from_string(data)  # ou load_from_bytes
    # opset
    opset = next((o.version for o in model.opset_import if o.domain in ("", "ai.onnx")), None)
    if opset is None:
        raise ValidationError("Missing default opset")
    # shapes
    inferred = shape_inference.infer_shapes(model)
    inputs = [(i.name, str(i.type), shape_from(i.type)) for i in inferred.graph.input]
    outputs = [(o.name, str(o.type), shape_from(o.type)) for o in inferred.graph.output]
    return OnnxMetadata(opset=opset, inputs=inputs, outputs=outputs)
```

### API REST

```
POST   /api/v1/models                              → 201 Model
GET    /api/v1/models?project_id=...               → 200 Model[]
GET    /api/v1/models/{id}                         → 200 Model

POST   /api/v1/models/{id}/versions:upload         → 201 ModelVersion (streaming/chunked)
GET    /api/v1/models/{id}/versions                → 200 ModelVersion[]
GET    /api/v1/models/{id}/versions/{vid}          → 200 ModelVersion
GET    /api/v1/models/{id}/versions/{vid}/card     → 200 ModelCard (markdown)
GET    /api/v1/models/{id}/versions/{vid}/artifact → 302 redirect vers presigned URL (ou stream)

POST   /api/v1/models/{id}/versions/{vid}:promote  → 200 ModelVersion (transition)
```

### Model Card auto-générée

Template Markdown (Jinja2) avec : nom, version, tâche, dataset d'entraînement,
métriques (depuis MLflow si `mlflow_run_id`), specs ONNX (inputs/outputs),
historique des transitions, disclaimer BSL.

### Critère de fin M1.5

- Upload d'un modèle ONNX valide → `ModelVersion` créé avec `status=DRAFT`.
- Upload d'un fichier non-ONNX → 422.
- Transitions d'approval respectent state machine + rôles.
- Model Card accessible et contient les specs.
- Artifact récupérable via l'API.
- Coverage ≥ 70%.

### Dépendances

- `libs/storage`, `libs/schemas`.
- M1.4 (dataset) : `ModelVersion.trained_on_dataset_version_id` FK.
- M1.3 (project-api) : `Model.project_id` FK.
- Dépendance PyPI : `onnx>=1.16` (pour la validation).

---

## M1.6 — Gateway + Fleet Manager squelette

**Objectif :** deux services simples.

### B8 — Gateway (`services/gateway/`)

- **Python + Traefik** derrière.
- Validate les tokens OIDC Keycloak.
- Route vers `project-api`, `dataset`, `registry`.
- Agrège les OpenAPI sur `/docs`.
- Healthchecks `/healthz` et `/readyz`.
- Rate-limit basique (Redis) — optionnel en M1.6, peut attendre.

Le gateway n'a pas de logique métier : il valide + proxy.

### B5 — Fleet Manager squelette (`services/fleet/`)

- Catalogue des edge nodes en DB (`edges` table).
- Subscribe aux topics Sparkplug B (`spBv1.0/Vulis/NDATA/+/+/+`,
  `spBv1.0/Vulis/DBIRTH/+/+/+`, `spBv1.0/Vulis/DDEATH/+/+/+`).
- Maintient un état `online/offline` par edge.
- API REST :

  ```
  GET  /api/v1/fleet/edges                → 200 Edge[]  (avec last_seen, online)
  GET  /api/v1/fleet/edges/{id}           → 200 Edge
  POST /api/v1/fleet/edges/{id}:register  → 200 Edge    (enregistrement manuel)
  ```

- **OTA en M5** — pour M1.6 juste le squelette + lecture heartbeats.
- Mock : un script Python publie des birth/death/ndata fictifs sur Mosquitto
  pour tester.

### Dépendances

- `libs/core-py`, `libs/obs-py`.
- PyPI : `paho-mqtt>=2.0` (client MQTT).
- Dépend de M1.2 (Mosquitto démarré).

---

## M1.7 — UI minimale

**Objectif :** `apps/web/` (React) + amorçage `apps/tauri-app/`.

### `apps/web/`

- **Stack** : React 18 + Vite + TypeScript + shadcn/ui + TanStack Query.
- **Auth** : `react-keycloak-js` ou `oidc-client-ts`.
- **Pages M1.7** :
  - Login (redirect Keycloak).
  - Dashboard : liste des projets.
  - Project detail : lignes, tasks (kanban simple).
  - Datasets : liste + versions.
  - Models : liste + workflow d'approval (boutons promote selon rôle).
- **Pas de polish** : wireframe fonctionnel.

### `apps/tauri-app/`

- `cargo tauri init` dans `apps/tauri-app/`.
- Même frontend React que `apps/web` (composants partagés dans
  `apps/shared-ui/` si trop de duplication).
- Le backend Rust lance un sidecar Python (en M1.7, juste la structure ;
  le vrai sidecar arrive en M2).

### Critère de fin M1.7

- Depuis la webapp serveur, je peux lister projets + datasets + modèles.
- Depuis l'app Tauri, je peux faire pareil (au moins login + lecture).
- Le workflow d'approval est cliquable.

---

## M1.8 — CLI `vulis relay sync`

**Objectif :** `tools/vulis-cli/` avec au minimum `relay sync` et `relay git sync`.

### `tools/vulis-cli/`

- Python, installable via `pipx install vulis-cli`.
- Sous-commandes :
  - `vulis relay sync` — télécharge deps + pousse sur serveur.
  - `vulis relay git sync` — miroir Git local serveur.
  - `vulis dataset ...` — wrapper CLI du service dataset (bonus).
  - `vulis model ...` — wrapper du registry (bonus).

### `relay sync` workflow

1. Lit le `pyproject.toml` de chaque package, résout les deps via `uv pip compile`
   pour **Linux ET Windows** (edge Linux, serveur/workstation Windows).
2. Télécharge les wheels dans `./relay-staging/<py>-<os>/`.
3. Récupère les images Docker (`docker pull` + `docker save` en tar).
4. Télécharge les backbones (timm/anomalib) si demandé.
5. Calcule un `manifest.json` (sha256 de chaque artifact).
6. Signe avec cosign (ou une simple clé PGP en M1.8).
7. Pousse le tout sur le serveur via SMB (`libs/storage`).

### Critère de fin M1.8

- `vulis relay sync` produit un bundle signé sur le serveur.
- Le serveur peut lister les artifacts du depot.
- (Bonus) `vulis relay git sync` met à jour le bare mirror.

---

## Ordre recommandé d'exécution

1. **M1.2** (plateforme compose) — bloque tout le reste.
2. **M1.3** (project-api) — premier service, débloque M1.4/M1.5.
3. **M1.4** (dataset) ⭐ — dépend de M1.3.
4. **M1.5** (registry) ⭐ — dépend de M1.3 + M1.4.
5. **M1.6** (gateway + fleet) — peut se faire en parallèle de M1.4/M1.5.
6. **M1.7** (UI) — dépend de tous les services exposant une API.
7. **M1.8** (CLI relay) — indépendant, peut se faire tôt.

Un agent peut raisonnablement faire **M1.2 + M1.3** dans une session, puis
**M1.4** seul (c'est le plus volumineux), puis **M1.5** seul.
