"""ModelVersion routes — list, get, upload (streaming + ONNX validate),
promote (state machine), card (Markdown), artifact (blob)."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import hashlib
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from vulis_core import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
    VulisError,
)
from vulis_schemas import Base
from vulis_storage import StorageBackend, hash_bytes

from vulis_registry.audit import log_audit
from vulis_registry.dependencies import (
    CurrentUser,
    get_db,
    get_storage,
    require_role,
)
from vulis_registry.model_card import build_model_card
from vulis_registry.models import (
    Model,
    ModelStatus,
    ModelVersion,
    OnnxTensorSpec,
)
from vulis_registry.onnx_validate import validate_onnx
from vulis_registry.schemas import (
    ModelVersionCreate,
    ModelVersionRead,
    OnnxTensorSpecRead,
    PromoteRequest,
)
from vulis_registry.state_machine import (
    ALL_VERBS,
    apply_transition,
    is_verb_ambiguous,
)

# Two routers: one nested under /models/{id}, one top-level for
# /model-versions/{vid}:promote and :card/:artifact access.
nested = APIRouter(prefix="/models/{model_id}", tags=["model-versions"])
root = APIRouter(prefix="/model-versions", tags=["model-versions"])


# ─── Role gating per transition verb ──────────────────────────
#
# Per-verb role gates. Roles not in this map accept the verb (admin
# is always allowed). Mirrors the project-api Task state machine
# pattern, but extended with the new verbs (deploy, archive).

_VERB_ROLES: dict[str, tuple[str, ...]] = {
    "submit_for_review": ("data-scientist",),
    "approve": ("reviewer",),
    "reject": ("reviewer",),
    "deploy": ("operator",),
    "archive": ("admin",),
}


def _require_verb_role(verb: str, user: CurrentUser) -> None:
    """Raise 403 unless the user has a role allowed to invoke ``verb``.

    Admins are always allowed.
    """
    if "admin" in user.roles:
        return
    allowed = _VERB_ROLES.get(verb, ())
    if not (user.roles & set(allowed)):
        raise ForbiddenError(
            f"Role(s) {sorted(user.roles) or 'none'} cannot perform transition "
            f"{verb!r}; required one of {sorted(allowed) or ['admin']}"
        )


# ─── Helpers ────────────────────────────────────────────────────


def _get_active_model(session: Session, model_id: str, tenant_id: str) -> Model:
    model = session.get(Model, model_id)
    if model is None or model.deleted_at is not None or model.tenant_id != tenant_id:
        raise NotFoundError(f"Model {model_id} not found")
    return model


def _get_version(session: Session, version_id: str, tenant_id: str) -> ModelVersion:
    version = session.get(ModelVersion, version_id)
    if version is None or version.tenant_id != tenant_id:
        raise NotFoundError(f"ModelVersion {version_id} not found")
    return version


# ─── GET /models/{id}/versions ────────────────────────────────


@nested.get("/versions", response_model=list[ModelVersionRead])
async def list_versions(
    model_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[ModelVersion]:
    _get_active_model(session, model_id, user.tenant_id)
    stmt = (
        select(ModelVersion)
        .where(ModelVersion.model_id == model_id)
        .where(ModelVersion.tenant_id == user.tenant_id)
        .order_by(ModelVersion.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


# ─── GET /models/{id}/versions/{vid} ──────────────────────────


@nested.get("/versions/{version_id}", response_model=ModelVersionRead)
async def get_version(
    model_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> ModelVersion:
    _get_active_model(session, model_id, user.tenant_id)
    return _get_version(session, version_id, user.tenant_id)


# ─── GET /models/{id}/versions/{vid}/specs ────────────────────


@nested.get(
    "/versions/{version_id}/specs",
    response_model=list[OnnxTensorSpecRead],
)
async def get_version_specs(
    model_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> list[OnnxTensorSpec]:
    _get_active_model(session, model_id, user.tenant_id)
    _get_version(session, version_id, user.tenant_id)
    return list(
        session.execute(
            select(OnnxTensorSpec)
            .where(OnnxTensorSpec.version_id == version_id)
            .order_by(OnnxTensorSpec.direction, OnnxTensorSpec.name)
        ).scalars()
    )


# ─── POST /models/{id}/versions:upload (multipart) ────────────


@nested.post(
    "/versions:upload",
    response_model=ModelVersionRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"description": "File too large (exceeds VULIS_REGISTRY_MAX_UPLOAD_BYTES)"},
        415: {"description": "Uploaded file is not a valid ONNX model"},
        422: {"description": "ONNX validation failed"},
    },
)
async def upload_version(
    model_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist")),
    storage: StorageBackend = Depends(get_storage),
    file: UploadFile = File(..., description="The ONNX model file."),
    version: str | None = Form(default=None),
    major: int | None = Form(default=None, ge=0),
    minor: int | None = Form(default=None, ge=0),
    patch: int | None = Form(default=None, ge=0),
    created_by: Annotated[str | None, Form(min_length=1, max_length=255)] = None,
    trained_on_dataset_version_id: Annotated[str | None, Form()] = None,
    mlflow_run_id: Annotated[str | None, Form(max_length=128)] = None,
    # Metadata is sent as a JSON string (multipart doesn't support
    # nested objects). The route parses it.
    metadata: Annotated[str | None, Form()] = None,
) -> ModelVersion:
    from vulis_registry.config import get_settings

    settings = get_settings()
    model = _get_active_model(session, model_id, user.tenant_id)

    if not created_by:
        created_by = user.actor

    # Parse metadata JSON if provided.
    import json

    metadata_dict: dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
            if not isinstance(metadata_dict, dict):
                raise ValueError("metadata must be a JSON object")
        except (ValueError, TypeError) as e:
            raise ValidationError(
                f"metadata field must be a JSON object: {e}",
            ) from e

    # Build the create schema (re-uses the version resolver).
    create = ModelVersionCreate(
        version=version,
        major=major,
        minor=minor,
        patch=patch,
        created_by=created_by,
        trained_on_dataset_version_id=trained_on_dataset_version_id,
        mlflow_run_id=mlflow_run_id,
        metadata=metadata_dict,
    )
    major_n, minor_n, patch_n = create.resolve_semver()

    # Validate the trained_on_dataset_version_id exists in the same
    # tenant. Cross-service FK at the DB layer is enforced by the
    # migration; this is the application-layer sanity check.
    if trained_on_dataset_version_id is not None:
        from sqlalchemy import text

        exists = session.execute(
            text("SELECT 1 FROM dataset_versions WHERE id = :did AND tenant_id = :tid"),
            {"did": trained_on_dataset_version_id, "tid": user.tenant_id},
        ).first()
        if exists is None:
            raise NotFoundError(f"DatasetVersion {trained_on_dataset_version_id} not found")

    # ─── Stream the file: read in chunks, compute sha256, collect bytes ───
    #
    # We collect the bytes (rather than streaming them straight into
    # the storage backend) because we need the full payload to feed
    # ``onnx.load_from_string`` for validation. For multi-GB ONNX
    # files we'll want a streaming variant (save to a temp file,
    # validate, then upload) — out of scope for M1.5.
    hasher = hashlib.sha256()
    buf = io.BytesIO()
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise _UploadTooLarge(total, settings.max_upload_bytes)
        hasher.update(chunk)
        buf.write(chunk)
    data = buf.getvalue()
    digest = hasher.hexdigest()

    # ─── Validate ONNX ────────────────────────────────────────
    metadata_onnx = validate_onnx(data)  # raises ValidationError on bad ONNX

    # ─── Persist + upload ─────────────────────────────────────
    # Content-addressed put; key = "sha256/<digest>".
    artifact_key = storage.put_blob(data)
    if not artifact_key.endswith(digest):
        raise VulisError(
            f"Storage key {artifact_key!r} does not match computed digest {digest!r}",
            details={"key": artifact_key, "digest": digest},
        )

    new_version = ModelVersion(
        tenant_id=user.tenant_id,
        model_id=model.id,
        major=major_n,
        minor=minor_n,
        patch=patch_n,
        status=ModelStatus.DRAFT,
        artifact_key=artifact_key,
        artifact_digest=digest,
        artifact_size_bytes=total,
        trained_on_dataset_version_id=trained_on_dataset_version_id,
        mlflow_run_id=mlflow_run_id,
        onnx_opset=metadata_onnx.opset,
        created_by=created_by,
        metadata_=metadata_dict,
    )
    session.add(new_version)
    try:
        session.flush()
    except IntegrityError as e:
        raise AlreadyExistsError(
            f"Version {major_n}.{minor_n}.{patch_n} already exists for model {model_id}",
            details={"model_id": model_id, "version": f"{major_n}.{minor_n}.{patch_n}"},
        ) from e

    # Persist ONNX specs.
    for t in metadata_onnx.inputs:
        session.add(
            OnnxTensorSpec(
                version_id=new_version.id,
                direction="input",
                name=t.name,
                dtype=t.dtype,
                shape=list(t.shape),
            )
        )
    for t in metadata_onnx.outputs:
        session.add(
            OnnxTensorSpec(
                version_id=new_version.id,
                direction="output",
                name=t.name,
                dtype=t.dtype,
                shape=list(t.shape),
            )
        )

    # Auto-generate the model card (rendered markdown, persisted on
    # the row for cheap read).
    onnx_specs = list(metadata_onnx.inputs) + list(metadata_onnx.outputs)
    new_version.model_card = build_model_card(
        model=model,
        version=new_version,
        onnx_specs=[
            OnnxTensorSpec(
                version_id=new_version.id,
                direction=t.direction if hasattr(t, "direction") else "input",
                name=t.name,
                dtype=t.dtype,
                shape=list(t.shape),
            )
            for t in onnx_specs
        ],
        transition_rows=[],
    )

    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="model_version.upload",
        target_type="model_version",
        target_id=new_version.id,
        diff={
            "model_id": model_id,
            "version": f"{major_n}.{minor_n}.{patch_n}",
            "artifact_digest": digest,
            "artifact_size_bytes": total,
            "onnx_opset": metadata_onnx.opset,
            "trained_on_dataset_version_id": trained_on_dataset_version_id,
        },
    )
    session.commit()
    session.refresh(new_version)
    return new_version


# ─── GET /models/{id}/versions/{vid}/card ────────────────────


@nested.get(
    "/versions/{version_id}/card",
    response_class=Response,
    responses={
        200: {
            "content": {"text/markdown": {}},
            "description": "Markdown model card.",
        }
    },
)
async def get_model_card(
    model_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
) -> Response:
    model = _get_active_model(session, model_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    if version.model_card is None:
        # Lazy-render if missing (e.g. data inserted via raw SQL).
        specs = list(
            session.execute(
                select(OnnxTensorSpec).where(OnnxTensorSpec.version_id == version.id)
            ).scalars()
        )
        # Pull transitions from the audit log.
        table = Base.metadata.tables["audit_events"]
        audit_rows = list(session.execute(select(table).where(table.c.target_id == version.id)))
        version.model_card = build_model_card(
            model=model, version=version, onnx_specs=specs, transition_rows=audit_rows
        )
        session.commit()
    return Response(content=version.model_card, media_type="text/markdown; charset=utf-8")


# ─── GET /models/{id}/versions/{vid}/artifact ────────────────


@nested.get(
    "/versions/{version_id}/artifact",
    response_class=Response,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "The raw ONNX artifact bytes.",
        }
    },
)
async def get_artifact(
    model_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_role("admin", "data-scientist", "annotator", "reviewer", "operator")
    ),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    _get_active_model(session, model_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    data = storage.get_bytes(version.artifact_key)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(len(data)),
            "X-Content-SHA256": version.artifact_digest,
            "Content-Disposition": (
                f'attachment; filename="{version.artifact_key.split("/")[-1]}.onnx"'
            ),
        },
    )


# ─── POST /models/{id}/versions/{vid}:promote ─────────────────


@nested.post(
    "/versions/{version_id}:promote",
    response_model=ModelVersionRead,
    responses={409: {"description": "Invalid transition for current status"}},
)
async def promote_version(
    model_id: str,
    version_id: str,
    body: PromoteRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("admin", "data-scientist", "reviewer", "operator")),
) -> ModelVersion:
    _get_active_model(session, model_id, user.tenant_id)
    version = _get_version(session, version_id, user.tenant_id)
    verb = body.verb
    if verb not in ALL_VERBS:
        raise ValidationError(f"Unknown transition verb: {verb!r}. Allowed: {', '.join(ALL_VERBS)}")
    _require_verb_role(verb, user)
    # ``approve`` and ``reject`` are ambiguous verbs (mean different
    # things depending on the current state). The state machine
    # itself resolves them — we just need the caller to be allowed
    # the verb. Note the distinction is server-side.
    _ = is_verb_ambiguous  # explicit reference to keep the helper in use
    new_status = apply_transition(version.status, verb)  # raises InvalidTransitionError → 409
    old_status = version.status
    version.status = new_status
    log_audit(
        session,
        tenant_id=user.tenant_id,
        actor=user.actor,
        action="model_version.promote",
        target_type="model_version",
        target_id=version.id,
        diff={
            "verb": verb,
            "from": old_status.value,
            "to": new_status.value,
        },
    )
    session.commit()
    session.refresh(version)
    return version


# ─── Custom exception for upload size ──────────────────────────


class _UploadTooLarge(VulisError):
    """Raised when the uploaded file exceeds the configured size limit."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"Upload too large: {size} bytes (limit: {limit})",
            details={"size": size, "limit": limit},
        )


# Suppress unused-import warning for Annotated / hash_bytes — used
# transitively via FastAPI / content-addressed keys.
_ = Annotated
_ = hash_bytes

# Collect the routers.
router = APIRouter()
router.include_router(nested)
router.include_router(root)


__all__ = ["ALL_VERBS", "router"]


# Re-export AlreadyExistsError for the route's IntegrityError catch.
from vulis_core import AlreadyExistsError  # noqa: E402
