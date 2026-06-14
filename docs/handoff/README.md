# Vulis — Handoff dossier

> **À destination :** d'un agent (humain ou IA) qui reprend le développement
> de Vulis après l'achèvement de M1.0 + M1.1.
>
> **Date de rédaction :** 2026-06-14
> **État du projet :** M1.0 + M1.1 terminés, 176 tests verts, ruff OK sur les 4 libs.

---

## Comment utiliser ce dossier

Lis les documents **dans l'ordre** :

| # | Document | Ce que tu y trouves |
|---|---|---|
| 0 | **README.md** (ce fichier) | Mode d'emploi du dossier |
| 1 | [01-context.md](./01-context.md) | Topologie 3-surfaces, contraintes industrielles, choix techniques validés, ce qui a été décidé et pourquoi |
| 2 | [02-state.md](./02-state.md) | État exact du code maintenant : quelles libs existent, leur API publique, comment installer/tester, structure du repo |
| 3 | [03-conventions.md](./03-conventions.md) | Patterns à respecter pour la suite : structure d'un service FastAPI, gestion d'erreurs, conventions de tests, ruff |
| 4 | [04-roadmap.md](./04-roadmap.md) | Le détail des prochaines étapes M1.2 → M1.8, avec modèles de données, signatures d'API, critères de fin |
| 5 | [05-pitfalls.md](./05-pitfalls.md) | Pièges connus (Python 3.11 vs 3.12, hook linter, Windows shell, etc.) pour ne pas tomber dedans |

## Lecture rapide (TL;DR)

Si tu n'as que 5 minutes :

1. **Vulis** = plateforme de vision industrielle open-source (BSL → AGPL), air-gap-ready, multi-tâches (détection/classification/segmentation).
2. **3 surfaces** : Workstation (train, internet), Serveur Windows (control plane, air-gap, SMB), Edge GPU (inférence, air-gap total).
3. **Stack** : Python-first, Rust seulement côté Tauri. MQTT 5 + Sparkplug B pour edge↔serveur. Stockage via `smbprotocol` (pur Python) avec abstraction multi-backend.
4. **Layout** : monorepo modulaire (`libs/` + `services/` + `apps/` + `tools/`), workspace `uv`, 10 briques B1-B10.
5. **Fait** : M1.0 (repo, licence, docs, ADR, CI, compose, Taskfile) + M1.1 (`libs/core-py`, `libs/storage`, `libs/obs-py`, `libs/proto`, `libs/schemas`).
6. **À faire** : M1.2 (plateforme compose) → M1.3 (project-api) → M1.4 (dataset) ⭐ → M1.5 (registry) ⭐ → M1.6 (gateway+fleet) → M1.7 (UI) → M1.8 (CLI relay).
7. **Démarrer** : `cd libs/core-py && uv sync --extra dev && uv run pytest`.

## Fichiers source de vérité

Outre ce dossier, les documents canoniques à consulter :

- [`ARCHITECTURE.md`](../../ARCHITECTURE.md) — vue d'architecture vivante
- [`ADR/`](../../ADR/) — 10 ADR numérotés + template
- [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — conventions de contribution
- [`README.md`](../../README.md) — présentation publique

## Conventions pour la suite

- **Commits** : Conventional Commits (`feat(dataset): ...`), DCO sign-off (`-s`).
- **Décisions non triviales** : obligatoirement un ADR (copier `ADR/0000-template.md`).
- **Trunk-based** : `main` toujours déployable, feature branches courtes, PR requises.
- **Tests** : paramétrés quand possible (voir le contrat `libs/storage/tests/test_contract.py`).
- **Reviews** : par le propriétaire humain (Basti). Les agents implémentent et soumettent.
