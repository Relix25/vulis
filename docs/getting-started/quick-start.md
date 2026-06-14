# Quick start

> This page is a stub — the commands below will be validated end-to-end
> during M1 implementation.

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11 or 3.12 | Runtime for all services and libs. |
| [uv](https://docs.astral.sh/uv/) | latest | Python dependency & venv manager. |
| [Task](https://taskfile.dev) | 3.x | Build runner. |
| Docker | 24+ | Local dev stack (Postgres, Mosquitto, Redis, Keycloak). |

On Windows: `winget install Task.Task` and use WSL2 + Docker Engine (without
Docker Desktop) — a dedicated setup guide is forthcoming.

## Bootstrap

```bash
git clone https://github.com/vulis/vulis.git
cd vulis

# Install Python dependencies across all packages
task install

# Start the local dev stack
task up
```

## Develop on a single package

```bash
cd libs/storage
uv sync
uv run pytest
```

## Run the checks (CI-equivalent)

```bash
task check
```

## Serve the docs locally

```bash
task docs
# → http://127.0.0.1:8000
```

## Tear down

```bash
task down          # stop containers, keep volumes
task down-v        # stop AND delete volumes (destructive)
```
