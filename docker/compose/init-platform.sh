#!/usr/bin/env bash
# Vulis platform — post-up initialization & smoke test (bash).
#
# Assumes `task up:platform` (or `docker compose --profile platform -f
# docker-compose.platform.yml up -d`) has just been run.
#
# What it does:
#   0. Ensure .env exists (copy from .env.example if missing).
#   1. Wait for the alembic one-shot to finish (exit 0 = success).
#   2. Wait for Keycloak to be healthy.
#   3. Verify the "vulis" realm was imported (OIDC discovery).
#   4. Smoke test MQTT (publish/subscribe) with credentials from .env.
#   5. Print a recap of URLs + dev credentials.
#
# Windows: use init-platform.ps1 from PowerShell.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="$ROOT/docker/compose"
cd "$COMPOSE_DIR"

# ─── 0. Ensure .env ───────────────────────────────────────────
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "⚠️  Created .env from .env.example — edit it with strong passwords before any non-dev use." >&2
  else
    echo "❌ .env.example missing." >&2
    exit 1
  fi
fi

# Load .env into the current shell (KEY=VALUE per line, no expansion)
set -a
# shellcheck disable=SC1091
. ./.env
set +a

PG_USER="${POSTGRES_USER:-vulis}"
PG_PORT="${POSTGRES_HOST_PORT:-5432}"

MQTT_USER="${MQTT_USER:-vulis}"
MQTT_PASS="${MQTT_PASSWORD:-vulis-dev-password}"
MQTT_PORT="${MQTT_HOST_PORT:-1883}"

KC_PORT="${KEYCLOAK_HOST_PORT:-8080}"
KC_REALM="${KEYCLOAK_REALM:-vulis}"
KC_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KC_ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

PROJECT="vulis-platform"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.platform.yml)

# ─── 1. Wait for alembic one-shot ─────────────────────────────
# Two outcomes are valid:
#   a) The alembic container is still running (it just ran via `up -d`)
#      → wait for it to exit cleanly.
#   b) The alembic container has already finished and been cleaned up
#      (e.g. the init script is re-run) → just verify the schema is at head.
echo "⏳ Verifying alembic migration is applied..."
ALEMBIC_OK=0
for i in $(seq 1 90); do
  STATUS_JSON="$("${COMPOSE[@]}" ps alembic --format json 2>/dev/null || true)"

  if [ -n "$STATUS_JSON" ] && [ "$STATUS_JSON" != "[]" ] && [ "$STATUS_JSON" != "null" ]; then
    # Container still exists — wait for it to finish.
    STATE=$(echo "$STATUS_JSON" | grep -oE '"State":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
    if [ "$STATE" = "exited" ]; then
      EXIT_CODE=$(echo "$STATUS_JSON" | grep -oE '"ExitCode":[0-9-]+' | head -1 | cut -d':' -f2 || true)
      if [ "${EXIT_CODE:-1}" = "0" ]; then
        echo "✓ Alembic one-shot finished (exit 0)"
        ALEMBIC_OK=1
        break
      else
        echo "❌ Alembic exited with code $EXIT_CODE — check: ${COMPOSE[*]} logs alembic"
        exit 1
      fi
    fi
  else
    # Container gone (likely cleaned up after success) — verify schema.
    if docker exec vulis-platform-postgres-1 psql -U "$PG_USER" -d "${POSTGRES_DB:-vulis}" \
         -tA -c "SELECT version_num FROM alembic_version" 2>/dev/null | grep -qE '^[0-9]+$'; then
      echo "✓ Alembic schema at head (alembic_version present)"
      ALEMBIC_OK=1
      break
    fi
    # Schema not yet applied — trigger alembic ourselves.
    echo "… alembic not run yet, triggering it…"
    "${COMPOSE[@]}" run --rm alembic
    echo "✓ Alembic migration applied"
    ALEMBIC_OK=1
    break
  fi

  sleep 2
  if [ "$i" = 90 ]; then
    echo "❌ Alembic didn't finish in 180s"
    exit 1
  fi
done
[ "$ALEMBIC_OK" = "1" ] || { echo "❌ Alembic verification failed"; exit 1; }

# ─── 2. Wait for Keycloak ─────────────────────────────────────
# Keycloak 25 in start-dev mode doesn't expose /health/ready. The most
# reliable "ready" signal is that the OIDC discovery doc for the master
# realm is responding — which means the server is past startup and the
# DB schema is initialized.
echo "⏳ Waiting for Keycloak on :$KC_PORT..."
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$KC_PORT/realms/vulis/.well-known/openid-configuration" > /dev/null 2>&1; then
    echo "✓ Keycloak ready (vulis realm responding)"
    break
  fi
  sleep 2
  if [ "$i" = 60 ]; then
    echo "❌ Keycloak not ready in 120s"
    exit 1
  fi
done

# ─── 3. Verify realm imported ─────────────────────────────────
if curl -sf "http://127.0.0.1:$KC_PORT/realms/$KC_REALM/.well-known/openid-configuration" > /dev/null 2>&1; then
  echo "✓ Keycloak realm '$KC_REALM' imported"
else
  echo "⚠️  Realm '$KC_REALM' not responding — check keycloak/realms/*.json"
fi

# ─── 4. Smoke test MQTT ───────────────────────────────────────
if command -v mosquitto_pub > /dev/null 2>&1 && command -v mosquitto_sub > /dev/null 2>&1; then
  echo "⏳ Testing MQTT pub/sub (auth=$MQTT_USER)..."
  (mosquitto_sub -h 127.0.0.1 -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "vulis/init/test" -C 1 -W 10) > /tmp/vulis_mqtt_sub.$$ 2>&1 &
  SUB_PID=$!
  sleep 1
  mosquitto_pub -h 127.0.0.1 -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" \
    -t "vulis/init/test" -m "hello from init-platform.sh"
  if wait "$SUB_PID"; then
    echo "✓ MQTT pub/sub OK"
  else
    echo "⚠️  MQTT pub/sub timeout — broker up but sub didn't get the message"
  fi
  rm -f /tmp/vulis_mqtt_sub.$$
else
  echo "ℹ️  mosquitto_pub/sub not installed — skipping MQTT test (broker should still be up)"
fi

# ─── 5. Recap ─────────────────────────────────────────────────
cat <<EOF

========================================
  Vulis platform — ready
========================================
  Postgres:    127.0.0.1:$PG_PORT  (user=$PG_USER, db=${POSTGRES_DB:-vulis})
  Redis:       127.0.0.1:${REDIS_HOST_PORT:-6379}
  Mosquitto:   127.0.0.1:$MQTT_PORT  (user=$MQTT_USER, pass=***)
  Keycloak:    http://127.0.0.1:$KC_PORT  (admin / $KC_ADMIN_PASS)
               realm: $KC_REALM
  Traefik:     http://127.0.0.1:${TRAEFIK_DASHBOARD_PORT:-8081}  (dashboard)
========================================
  Dev users (password = username):
    admin            / admin
    data-scientist   / data-scientist
    annotator        / annotator
    operator         / operator
    reviewer         / reviewer
========================================
EOF
