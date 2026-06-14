# 01 — Contexte & contraintes

Ce document décrit le **pourquoi** de chaque choix, de façon à ce qu'un nouvel
agent puisse défendre les décisions devant un reviewer sans avoir à redeviner
les arbitrages.

## 1. Le projet en une phrase

**Vulis** est une plateforme open-source (BSL 1.1 → AGPL-3.0 en 2030) de
vision par ordinateur pour lignes de production industrielles, conçue pour
un déploiement on-premise air-gap et une topologie multi-surfaces.

## 2. Cas d'usage couverts

| Tâche | Statut |
|---|---|
| Détection de défauts | ✅ cible |
| Classification / tri | ✅ cible |
| Segmentation (sémantique/instance) | ✅ cible |
| Métrologie / mesure 3D | ❌ hors scope M1-M9 |

L'architecture doit traiter la **tâche** comme une notion de premier ordre :
un slot modèle par tâche, des recettes d'entraînement différenciées.

## 3. La topologie 3-surfaces (CRITIQUE)

Tout découle de cette topologie. Apprends-la par cœur.

```
┌──────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
│  SURFACE 1: WORKSTATION  │   │  SURFACE 2: SERVER (Win) │   │  SURFACE 3: EDGE ×N      │
│  (mon PC de travail)     │   │  Control plane. Pas GPU. │   │  PC industriels GPU      │
│                          │   │                          │   │                          │
│  • Internet via proxy    │   │  • AIR-GAP (pas d'inet)  │   │  • AIR-GAP TOTAL         │
│  • GPU local             │   │  • Shares SMB centraux   │   │  • GPU (inférence)       │
│  • App Tauri + CLI       │   │  • Pont UNIQUE vers edge │   │  • Caméras (acquisition) │
│  • Pont air-gap          │   │  • Webapp + REST/gRPC    │   │  • Pull updates serveur  │
│                          │   │  • Fleet manager         │   │                          │
│  → Entraînement          │   │  → Orchestration         │   │  → Acquisition + serving │
└─────────────┬────────────┘   └─────────────┬────────────┘   └─────────────┬────────────┘
              │   LAN (proxy-aware)          │  MQTT 5 + Sparkplug B (pull + push)  │
              └──────────────────────────────┴─────────────────────────────────────┘
```

### Implications structurantes

| Contrainte | Conséquence |
|---|---|
| Serveur sans GPU | Le serveur ne calcule jamais. Compute distribué : train sur workstation, inférence sur edge. |
| Serveur air-gap | Tout artifact externe (wheels, images Docker, backbones) doit être relayé par la workstation via `vulis relay sync` (cf. ADR 0007). |
| Edge air-gap total | Edge = self-contained. Modèles pré-pushés. Updates via MQTT signal + HTTP pull depuis le serveur. |
| Edge non joignable depuis workstation | Le serveur est le pont unique. La communication edge↔serveur doit supporter **pull ET push** (MQTT gère les deux via le broker Mosquitto sur le serveur). |
| Stockage = shares SMB Windows | Abstraction `StorageBackend` avec `SmbProtocolBackend` (pur Python, via `smbprotocol`) en défaut. Cf. ADR 0006. |
| Windows server + Linux edge + Windows workstation | Tous les services doivent tourner sur Linux ET Windows. Pas de techno Linux-only. |

## 4. Décisions techniques (toutes validées par Basti)

| # | Sujet | Choix | ADR |
|---|---|---|---|
| 1 | Licence | **BSL 1.1**, change date **2030-06-14 → AGPL-3.0**. Usage interne OK (usines), revente/SaaS concurrent interdit. | [0001](../../ADR/0001-license.md) |
| 2 | Layout | **Monorepo modulaire** (`libs/` + `services/` + `apps/` + `tools/`), workspace uv. | [0002](../../ADR/0002-monorepo.md) |
| 3 | Stack | **Python partout** (ML, services, acquisition). **Rust uniquement** pour le backend de l'app Tauri. **Pas de Go.** | [0003](../../ADR/0003-stack-python-first.md) |
| 4 | Bus edge↔serveur | **MQTT 5 + Sparkplug B**, broker Mosquitto sur le serveur. Sparkplug B dès le départ (birth/death certs, discovery). | [0004](../../ADR/0004-mqtt-sparkplug.md) |
| 5 | Topologie | 3 surfaces (workstation/server/edge). | [0005](../../ADR/0005-topology-3-surfaces.md) |
| 6 | Stockage | Abstraction `StorageBackend`, **`SmbProtocolBackend` défaut** (pur Python, smbprotocol). `SmbMountBackend` optionnel pour la perf. | [0006](../../ADR/0006-storage-abstraction.md) |
| 7 | Air-gap relay | `vulis relay sync` sur workstation télécharge artifacts via proxy, signe, pousse sur serveur. Serveur redistribue aux edges. | [0007](../../ADR/0007-air-gap-relay.md) |
| 8 | Fleet manager | Service serveur B5, OTA via MQTT signal + HTTP pull, support bare-metal ET Docker. | [0008](../../ADR/0008-edge-fleet.md) |
| 9 | Gestion code | Trunk-based, SemVer indépendant par brique, releases au fil de l'eau, GitHub public + miroir local serveur. | [0009](../../ADR/0009-code-management.md) |
| 10 | Miroir Git air-gap | Bare mirror sur serveur, `vulis relay git sync` depuis la workstation. | [0010](../../ADR/0010-air-gap-git-mirror.md) |

### Décisions hors ADR (validées en discussion)

| Sujet | Choix |
|---|---|
| Auth | **Keycloak** (OIDC, multi-tenant via realms, air-gap) |
| Frontend | **React + Vite + shadcn/ui + TanStack Query** (partagé entre webapp serveur et app Tauri) |
| CLI runner | **Task** (`Taskfile.yml`) |
| Annotation | **CVAT** auto-hébergé, intégré via API (livré en M8) |
| ML | **PyTorch → ONNX Runtime** pour le serving |
| DB | **PostgreSQL 16** |
| Cache | **Redis 7** |
| Reverse proxy | **Traefik** |
| Obs infra | **Prometheus + Loki + Grafana + OpenTelemetry** |
| Drift tabulaire | **Evidently** |
| Drift visuel | **Custom** (pas d'outil mature) |
| Edge runtime | **Bare-metal ET Docker** supportés par le Fleet Manager |

## 5. Les 10 briques (par surface)

| # | Brique | Surface | Langage | M-lien |
|---|---|---|---|---|
| B1 | Acquisition | Edge | Python (Harvester/SDKs) | M3 |
| B2 | Dataset & Model Registry | Serveur | Python (FastAPI) + abstraction storage | **M1.4 + M1.5** |
| B3 | Training | Workstation | Python + shell Tauri (sidecar PyTorch) | M2 |
| B4 | Serving | Edge | Python (ONNX Runtime) | M4 |
| B5 | Edge Fleet Manager ⭐ | Serveur | Python (updates OTA, health Sparkplug B) | squelette M1.6, OTA M5 |
| B6 | Observabilité | Toutes | Python + Grafana/Prometheus + drift custom | M6 |
| B7 | Gestion projet/workflow | Serveur | Python (FastAPI, RBAC, audit trail append-only) | **M1.3** |
| B8 | API Gateway | Serveur | Python (FastAPI) + Traefik | M1.6 |
| B9 | UI | Serveur (web) + Workstation (Tauri) | React/TS partagé | M1.7 |
| B10 | Plateforme | Serveur | Infra (Postgres, Mosquitto, Redis, Keycloak, Traefik, SMB shares) | **M1.2** |

## 6. Build vs integrate (synthèse)

- **~65% intégré** : Postgres, Mosquitto, Redis, Keycloak, Traefik, MLflow tracking, CVAT, Evidently, Prom/Loki/Grafana, OTel, Sparkplug B libs, ONNX Runtime, anomalib/smp/timm.
- **~25% hybride** : abstraction storage (SMB+S3+local), dataset versioning DVC-like, model registry custom (approval+audit industriel), training orchestrateur léger, fleet manager.
- **~10% build pur différenciant** : drift visuel, acquisition multi-vendeurs, dashboards ML métier, app Tauri.

## 7. Conventions immuables

Ne pas contester sans discussion explicite avec Basti :

1. **Python first** — pas de Go, Rust réservé à Tauri.
2. **Air-gap strict** — le serveur et les edges n'ont pas internet.
3. **Linux + Windows** — tous les services doivent fonctionner sur les deux.
4. **BSL 1.1** — pas d'AGPL avant 2030.
5. **Stockage via abstraction** — jamais d'appel direct `open()` sur un chemin partagé.
6. **MQTT 5 + Sparkplug B** — pas de Kafka, pas de gRPC pour la comm edge↔serveur.
7. **Monorepo modulaire** — chaque sous-dossier auto-suffisant, son propre SemVer.

## 8. Profil du mainteneur

- Expert ML + architecture logicielle.
- Connaît très bien Python, moins l'infra/distributed systems.
- Goûte les architectures claires, justifiées, avec ADR.
- Travaille seul pour l'instant ; objectif open-source mature.
- Pas de deadline commerciale dure ; qualité d'abord.
