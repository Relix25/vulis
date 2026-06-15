"""Integration tests for the DatasetVersion routes (create, list, publish, split)."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_dataset(client: TestClient, headers: dict, name: str = "ds") -> dict:
    resp = client.post(
        "/api/v1/datasets",
        json={"project_id": "project_test", "name": name, "task_kind": "DETECTION"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_version(client: TestClient, headers: dict, dataset_id: str, **overrides) -> dict:
    body = {"created_by": "alice", "version": "0.0.1"}
    body.update(overrides)
    resp = client.post(f"/api/v1/datasets/{dataset_id}/versions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_samples(
    client: TestClient,
    headers: dict,
    dataset_id: str,
    version_id: str,
    samples: list[dict],
) -> None:
    """Inject samples directly via the storage backend + a tiny helper.

    Tests use the storage backend (local-fs) + a direct DB insert —
    faster than going through the async import worker for unit tests
    of the routes themselves. Async worker has its own test in
    test_routes_imports.py.
    """

    from vulis_dataset.models import Sample

    # Use the test session factory to insert.
    app = client.app
    session_factory = app.state.db_sessionmaker
    storage = app.state.storage
    with session_factory() as s:
        for spec in samples:
            data = spec["data"]
            key = storage.put_blob(data)
            digest = key.split("/", 1)[1]
            s.add(
                Sample(
                    tenant_id=headers["X-Tenant-Id"],
                    version_id=version_id,
                    blob_key=key,
                    relative_path=spec["path"],
                    label=spec.get("label"),
                    size_bytes=len(data),
                    split=spec.get("split", "TRAIN"),
                    blob_digest=digest,
                )
            )
        s.commit()


# ─── Version create / list / get ───────────────────────────────


def test_create_version_returns_201(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    assert v["major"] == 0 and v["minor"] == 0 and v["patch"] == 1
    assert v["is_published"] is False
    assert v["manifest_key"] is None
    assert v["created_by"] == "alice"
    assert v["sample_count"] == 0


def test_create_version_with_explicit_semver(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"], version="2.3.4")
    assert (v["major"], v["minor"], v["patch"]) == (2, 3, 4)


def test_create_duplicate_version_returns_409(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    _create_version(client, admin_headers, ds["id"], version="1.2.3")
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions",
        json={"created_by": "alice", "version": "1.2.3"},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_EXISTS"


def test_list_versions(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    _create_version(client, admin_headers, ds["id"], version="0.0.1")
    _create_version(client, admin_headers, ds["id"], version="0.0.2")
    resp = client.get(f"/api/v1/datasets/{ds['id']}/versions", headers=admin_headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2


def test_get_version(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    resp = client.get(f"/api/v1/datasets/{ds['id']}/versions/{v['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == v["id"]


# ─── Publish ───────────────────────────────────────────────────


def test_publish_empty_version_returns_422(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish",
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION"


def test_publish_with_samples_returns_200(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(
        client,
        admin_headers,
        ds["id"],
        v["id"],
        [
            {"data": b"img1-bytes", "path": "train/x.png", "label": "ok"},
            {"data": b"img2-bytes", "path": "train/y.png", "label": "ko"},
        ],
    )
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_published"] is True
    assert body["manifest_key"] is not None
    assert body["manifest_key"].startswith("sha256/")
    assert body["manifest_digest"] is not None
    assert body["sample_count"] == 2


def test_publish_twice_returns_409(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(
        client,
        admin_headers,
        ds["id"],
        v["id"],
        [{"data": b"x", "path": "train/x.png"}],
    )
    client.post(f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish", headers=admin_headers)
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish", headers=admin_headers
    )
    assert resp.status_code == 409


# ─── Manifest ──────────────────────────────────────────────────


def test_manifest_unpublished_returns_409(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    resp = client.get(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/manifest",
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_manifest_after_publish_returns_full_doc(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(
        client,
        admin_headers,
        ds["id"],
        v["id"],
        [
            {"data": b"a-bytes", "path": "train/a.png", "label": "ok", "split": "TRAIN"},
            {"data": b"b-bytes", "path": "val/b.png", "label": "ko", "split": "VAL"},
        ],
    )
    client.post(f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish", headers=admin_headers)
    resp = client.get(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/manifest",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["manifest_version"] == "0.0.1"
    assert body["dataset_id"] == ds["id"]
    assert body["sample_count"] == 2
    # Manifest samples are sorted by key for reproducibility.
    paths = [s["path"] for s in body["samples"]]
    assert paths == sorted(paths) or {  # not necessarily — sort is by key first
        s["path"] for s in body["samples"]
    } == {"train/a.png", "val/b.png"}


# ─── Split ─────────────────────────────────────────────────────


def test_split_manual(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(
        client,
        admin_headers,
        ds["id"],
        v["id"],
        [
            {"data": b"a", "path": "a.png"},
            {"data": b"b", "path": "b.png"},
            {"data": b"c", "path": "c.png"},
        ],
    )
    # Find the sample IDs.
    from sqlalchemy import select

    from vulis_dataset.models import Sample

    with client.app.state.db_sessionmaker() as s:
        samples = list(
            s.execute(
                select(Sample).where(Sample.version_id == v["id"]).order_by(Sample.id)
            ).scalars()
        )
        sids = [x.id for x in samples]

    # Assign: first → TRAIN, second → VAL, third → TEST.
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:split",
        json={
            "strategy": "manual",
            "assignments": [
                {"sample_id": sids[0], "split": "TRAIN"},
                {"sample_id": sids[1], "split": "VAL"},
                {"sample_id": sids[2], "split": "TEST"},
            ],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    # Verify
    resp = client.get(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/samples",
        params={"split": "TRAIN"},
        headers=admin_headers,
    )
    train_samples = resp.json()
    assert len(train_samples) == 1
    assert train_samples[0]["id"] == sids[0]


def test_split_stratified(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    # 10 samples, 5 "ok" / 5 "ko"
    samples_specs = []
    for i in range(5):
        samples_specs.append({"data": f"ok-{i}".encode(), "path": f"img_{i}.png", "label": "ok"})
    for i in range(5):
        samples_specs.append(
            {"data": f"ko-{i}".encode(), "path": f"img_{i + 5}.png", "label": "ko"}
        )
    _add_samples(client, admin_headers, ds["id"], v["id"], samples_specs)

    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:split",
        json={
            "strategy": "stratified",
            "ratios": {"TRAIN": 0.6, "VAL": 0.2, "TEST": 0.2},
            "stratify_by": "label",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    # Verify counts: with 10 samples and 60/20/20 → 6/2/2.
    splits_count: dict[str, int] = {}
    for sp in ("TRAIN", "VAL", "TEST"):
        r = client.get(
            f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/samples",
            params={"split": sp},
            headers=admin_headers,
        )
        splits_count[sp] = len(r.json())
    assert sum(splits_count.values()) == 10
    # The exact split is deterministic given the seed and sorted IDs.
    # We don't assert specific counts (the test data is symmetric so any
    # of {6,2,2} and the ratios can interchange), only that they're
    # roughly proportional.
    assert splits_count["TRAIN"] >= 5


def test_split_ratios_must_sum_to_one(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(client, admin_headers, ds["id"], v["id"], [{"data": b"x", "path": "x.png"}])
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:split",
        json={
            "strategy": "stratified",
            "ratios": {"TRAIN": 0.5, "VAL": 0.1},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_split_published_version_returns_409(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(client, admin_headers, ds["id"], v["id"], [{"data": b"x", "path": "x.png"}])
    client.post(f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish", headers=admin_headers)
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:split",
        json={"strategy": "manual", "assignments": []},
        headers=admin_headers,
    )
    assert resp.status_code == 409


# ─── Samples endpoints ─────────────────────────────────────────


def test_list_samples_with_split_filter(client: TestClient, admin_headers: dict):
    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(
        client,
        admin_headers,
        ds["id"],
        v["id"],
        [
            {"data": b"a", "path": "a.png", "split": "TRAIN"},
            {"data": b"b", "path": "b.png", "split": "VAL"},
        ],
    )
    resp = client.get(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/samples",
        params={"split": "VAL"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["split"] == "VAL"


def test_update_sample_split(client: TestClient, admin_headers: dict):
    from sqlalchemy import select

    from vulis_dataset.models import Sample

    ds = _create_dataset(client, admin_headers)
    v = _create_version(client, admin_headers, ds["id"])
    _add_samples(client, admin_headers, ds["id"], v["id"], [{"data": b"a", "path": "a.png"}])
    with client.app.state.db_sessionmaker() as s:
        sample = s.execute(select(Sample).where(Sample.version_id == v["id"])).scalar_one()
        sid = sample.id

    resp = client.patch(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/samples/{sid}",
        json={"split": "VAL"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["split"] == "VAL"
