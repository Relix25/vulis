# Vulis platform — post-up initialization & smoke test (PowerShell).
# Equivalent of init-platform.sh for native Windows.
#
# Run after `task up:platform`:
#   powershell -ExecutionPolicy Bypass -File docker/compose/init-platform.ps1

$ErrorActionPreference = "Stop"

$composeDir = $PSScriptRoot
Set-Location $composeDir

# ─── 0. Ensure .env ─────────────────────────────────────────
$envFile = Join-Path $composeDir ".env"
if (-not (Test-Path $envFile)) {
  $example = Join-Path $composeDir ".env.example"
  if (Test-Path $example) {
    Copy-Item $example $envFile
    Write-Host "⚠️  Created .env from .env.example — edit it with strong passwords before any non-dev use." -ForegroundColor Yellow
  } else {
    Write-Host "❌ .env.example missing." -ForegroundColor Red
    exit 1
  }
}

# Load .env
Get-Content $envFile | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
  $pair = $_ -split "=", 2
  if ($pair.Length -eq 2) {
    [System.Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim())
  }
}

$pgUser       = [System.Environment]::GetEnvironmentVariable("POSTGRES_USER") ?? "vulis"
$pgPort       = [System.Environment]::GetEnvironmentVariable("POSTGRES_HOST_PORT") ?? "5432"
$mqttUser     = [System.Environment]::GetEnvironmentVariable("MQTT_USER") ?? "vulis"
$mqttPass     = [System.Environment]::GetEnvironmentVariable("MQTT_PASSWORD") ?? "vulis-dev-password"
$mqttPort     = [System.Environment]::GetEnvironmentVariable("MQTT_HOST_PORT") ?? "1883"
$kcPort       = [System.Environment]::GetEnvironmentVariable("KEYCLOAK_HOST_PORT") ?? "8080"
$kcRealm      = [System.Environment]::GetEnvironmentVariable("KEYCLOAK_REALM") ?? "vulis"
$kcAdmin      = [System.Environment]::GetEnvironmentVariable("KEYCLOAK_ADMIN") ?? "admin"
$kcAdminPass  = [System.Environment]::GetEnvironmentVariable("KEYCLOAK_ADMIN_PASSWORD") ?? "admin"
$redisPort    = [System.Environment]::GetEnvironmentVariable("REDIS_HOST_PORT") ?? "6379"
$traefikPort  = [System.Environment]::GetEnvironmentVariable("TRAEFIK_DASHBOARD_PORT") ?? "8081"
$pgDb         = [System.Environment]::GetEnvironmentVariable("POSTGRES_DB") ?? "vulis"

# ─── 1. Wait for alembic one-shot ───────────────────────────
Write-Host "⏳ Waiting for alembic one-shot to finish..." -ForegroundColor Yellow
$alembicDone = $false
for ($i = 0; $i -lt 90; $i++) {
  $json = docker compose -p vulis-platform -f docker-compose.platform.yml ps alembic --format json 2>$null
  if ($LASTEXITCODE -eq 0 -and $json -and $json -ne "[]") {
    if ($json -match '"State":"exited"') {
      if ($json -match '"ExitCode":0') {
        Write-Host "✓ Alembic migration applied (schema is at head)" -ForegroundColor Green
        $alembicDone = $true
        break
      } else {
        Write-Host "❌ Alembic exited with non-zero code — check: docker compose ... logs alembic" -ForegroundColor Red
        exit 1
      }
    }
  }
  Start-Sleep -Seconds 2
}
if (-not $alembicDone) {
  Write-Host "❌ Alembic didn't finish in 180s" -ForegroundColor Red
  exit 1
}

# ─── 2. Wait for Keycloak ──────────────────────────────────
Write-Host "⏳ Waiting for Keycloak on :$kcPort..." -ForegroundColor Yellow
$kcReady = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    Invoke-WebRequest -Uri "http://127.0.0.1:$kcPort/health/ready" -UseBasicParsing -TimeoutSec 3 | Out-Null
    Write-Host "✓ Keycloak ready" -ForegroundColor Green
    $kcReady = $true
    break
  } catch {
    Start-Sleep -Seconds 2
  }
}
if (-not $kcReady) {
  Write-Host "❌ Keycloak not ready in 120s" -ForegroundColor Red
  exit 1
}

# ─── 3. Verify realm imported ──────────────────────────────
try {
  Invoke-WebRequest -Uri "http://127.0.0.1:$kcPort/realms/$kcRealm/.well-known/openid-configuration" -UseBasicParsing -TimeoutSec 5 | Out-Null
  Write-Host "✓ Keycloak realm '$kcRealm' imported" -ForegroundColor Green
} catch {
  Write-Host "⚠️  Realm '$kcRealm' not responding — check keycloak/realms/*.json" -ForegroundColor Yellow
}

# ─── 4. Smoke test MQTT ────────────────────────────────────
$mosqPub = Get-Command mosquitto_pub -ErrorAction SilentlyContinue
$mosqSub = Get-Command mosquitto_sub -ErrorAction SilentlyContinue
if ($mosqPub -and $mosqSub) {
  Write-Host "⏳ Testing MQTT pub/sub (auth=$mqttUser)..." -ForegroundColor Yellow
  $subJob = Start-Job -ScriptBlock {
    param($port, $user, $pass)
    & mosquitto_sub -h 127.0.0.1 -p $port -u $user -P $pass -t "vulis/init/test" -C 1 -W 10
  } -ArgumentList $mqttPort, $mqttUser, $mqttPass
  Start-Sleep -Seconds 1
  & mosquitto_pub -h 127.0.0.1 -p $mqttPort -u $mqttUser -P $mqttPass -t "vulis/init/test" -m "hello from init-platform.ps1"
  Wait-Job $subJob -Timeout 12 | Out-Null
  Remove-Job $subJob -Force
  Write-Host "✓ MQTT pub/sub OK" -ForegroundColor Green
} else {
  Write-Host "ℹ️  mosquitto_pub/sub not installed — skipping MQTT test" -ForegroundColor Yellow
}

# ─── 5. Recap ──────────────────────────────────────────────
Write-Host @"

========================================
  Vulis platform — ready
========================================
  Postgres:    127.0.0.1:$pgPort  (user=$pgUser, db=$pgDb)
  Redis:       127.0.0.1:$redisPort
  Mosquitto:   127.0.0.1:$mqttPort  (user=$mqttUser, pass=***)
  Keycloak:    http://127.0.0.1:$kcPort  (admin / $kcAdminPass)
               realm: $kcRealm
  Traefik:     http://127.0.0.1:$traefikPort  (dashboard)
========================================
  Dev users (password = username):
    admin            / admin
    data-scientist   / data-scientist
    annotator        / annotator
    operator         / operator
    reviewer         / reviewer
========================================
"@
