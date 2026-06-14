# Vulis Keycloak realm (dev)

This directory contains the **dev** Keycloak realm export, imported
automatically on first boot of the platform stack.

## Files

- **`vulis-realm-dev.json`** — the dev realm definition. Keycloak imports
  it on first start (via the `--import-realm` flag in
  `docker-compose.platform.yml`).

## What's in the realm

- **Realm name:** `vulis`
- **Roles (5):** `admin`, `data-scientist`, `annotator`, `operator`, `reviewer`
- **Users (5 — dev only, password = username):**
  - `admin` / `admin`
  - `data-scientist` / `data-scientist`
  - `annotator` / `annotator`
  - `operator` / `operator`
  - `reviewer` / `reviewer`
- **Clients (3):**
  - `vulis-web` — public + PKCE, for the React webapp (M1.7).
  - `vulis-tauri` — public + PKCE, for the Tauri workstation app (M1.7).
  - `vulis-cli` — confidential + service account, for the `vulis` CLI (M1.8).
- **Group:** `/tenants/default` — carries all 5 realm roles. Models
  multi-tenancy via Keycloak groups.

## Re-exporting the realm

If you change anything in the running Keycloak (via the admin UI) and want
to commit the changes back to this file:

```bash
# Start the platform stack
task up:platform
task init:platform

# Export the realm from the running Keycloak
docker compose -p vulis-platform -f docker-compose.platform.yml exec keycloak \
  /opt/keycloak/bin/kc.sh export --realm vulis \
  --dir /opt/keycloak/data/import --users realm_file

# Copy the file out
docker compose -p vulis-platform -f docker-compose.platform.yml cp \
  keycloak:/opt/keycloak/data/import/vulis-realm.json \
  ./keycloak/realms/vulis-realm-dev.json
```

## Security

This is a **dev** realm. Passwords are weak on purpose (so they're easy to
type during local dev). **Do not use these credentials in any non-dev
environment.**

For production, export a separate realm with strong passwords and secrets,
and keep it out of git (or in a private git repo).
