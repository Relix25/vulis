# vulis-proto

Protobuf schemas + generated Python code for Vulis services.

This package defines the **gRPC contracts** between Vulis services:

```
proto/
├── vulis/common/v1/common.proto     # shared types (EntityId, SemVer, TaskKind, ...)
├── vulis/project/v1/project.proto   # B7 — project/line/task management
├── vulis/dataset/v1/dataset.proto   # B2 — datasets and versions
└── vulis/model/v1/model.proto       # B2 — model registry
```

The generated `*_pb2.py` / `*_pb2_grpc.py` files are produced by
`buf` (or protoc) and committed under `src/vulis_proto/gen/`, so consumers
can install this package without a toolchain.

## Regenerating

```bash
# Option A — buf (recommended)
buf generate

# Option B — plain protoc
python -m grpc_tools.protoc \
    -I proto \
    --python_out=src/vulis_proto/gen \
    --grpc_python_out=src/vulis_proto/gen \
    proto/vulis/**/v1/*.proto
```

## Install

```bash
uv pip install -e libs/proto
```

## Status (M1)

Only the schemas are defined in M1; the services implementing them land in
M1.3 (project), M1.4 (dataset), M1.5 (registry). The generated code is
produced on demand during the first service integration.
