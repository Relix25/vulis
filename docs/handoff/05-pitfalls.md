# 05 — Pièges connus & solutions

Liste des pièges déjà rencontrés (et résolus) pendant M1.0 + M1.1. Un nouvel
agent doit les lire pour ne pas tomber dedans à nouveau.

## 1. Python 3.11 vs 3.12 — f-strings avec backslash

### Le problème

```python
# Python 3.12+ : OK
return f"{base}\\{nk.replace('/', '\\')}"

# Python 3.11 : SyntaxError
# "Cannot use an escape sequence (backslash) in f-strings"
```

C'est documenté comme une nouveauté 3.12. Mais Vulis cible **3.11+**, donc
ce pattern casse le build.

### La solution

Concaténation stricte à la place des f-strings pour les UNC paths :

```python
# BON
root = "\\\\" + self._host + "\\" + self._share
if self._root_prefix:
    root = root + "\\" + self._root_prefix
return root

# OU : construire les composants puis join
parts = ["", "", self._host, self._share, self._root_prefix]
return "\\".join(p for p in parts if p)
```

**Règle :** si tu as un backslash dans une f-string en Python <3.12, refactor.

## 2. Hook linter / format on save

### Le problème

L'éditeur (ou un hook ZCode) reformate les fichiers juste après qu'on les
lit. L'Edit échoue alors avec :

```
File has been modified since read, either by the user or by a linter.
```

Surtout quand on édite le même fichier plusieurs fois de suite.

### Les solutions

1. **Relire juste avant l'édition** via `Read` (court) puis `Edit` immédiat.
2. Si le hook se déclenche en boucle sur un fichier, **réécrire tout le
   fichier** via `Write` (sans re-lire préalablement si le contenu est
   maîtrisé).
3. En dernier recours, **patcher via un script Python inline** :

   ```python
   # _patch.py
   import io
   p = "libs/x/src/y.py"
   with io.open(p, encoding="utf-8") as f: s = f.read()
   old = "..."  # bloc exact
   new = "..."
   assert old in s
   with io.open(p, "w", encoding="utf-8") as f: f.write(s.replace(old, new))
   ```

   Puis `python _patch.py && del _patch.py`.

## 3. Windows cmd.exe — pas de `tail`, `head`, pipes fragiles

### Le problème

Le shell par défaut est `cmd.exe`. Beaucoup de commandes Unix ne marchent pas :

- `tail -20` → commande inconnue.
- `head -5` → commande inconnue.
- `findstr` (l'équivalent de `grep`) mais avec une syntaxe différente.
- Pipes avec `&` (pas `&&` pour séquence ; `&` exécute en parallèle).

### Les solutions

- **Lancer ruff/uv sans pipes** : `uv run ruff check src tests 2>&1` puis
  lire la sortie directement.
- Pour filtrer : `uv run pytest -q 2>&1 | findstr /R "passed failed"`.
- Multi-commandes séquentielles : `cd /d ... && uv run pytest` (avec `&&`).
- Multi-commandes parallèles : `cmd1 & cmd2 & cmd3` (avec `&` simple).
  ⚠️ en cmd.exe, `&` lance en parallèle, pas séquentiel.
- Pour `cd` vers un autre disque : `cd /d H:\path` (le `/d` est indispensable).

## 4. `pytest_addoption` — placement

### Le problème

```python
# tests/test_smb_protocol_live.py
def pytest_addoption(parser):
    parser.addoption("--smb-host", ...)
```

→ `ValueError: no option named '--smb-host'` quand on essaie d'y accéder.

### La cause

`pytest_addoption` est un hook qui doit être dans un **plugin ou un
`conftest.py`**. Dans un module de test, pytest ne l'enregistre pas.

### La solution

Toujours déclarer les options CLI et les markers dans `tests/conftest.py` :

```python
# tests/conftest.py
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--smb-host", action="store", default=None)

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smb: live SMB share required")
```

## 5. SQLAlchemy — naming convention au mauvais endroit

### Le problème

```python
class VulisRegistry(registry):
    def __init__(self):
        super().__init__(naming_convention=NamingConvention)
# TypeError: registry.__init__() got an unexpected keyword argument 'naming_convention'
```

### La cause

`naming_convention` est un argument de `MetaData`, pas de `registry`. Et
`DeclarativeBase` n'expose pas `registry.naming_convention`.

### La solution

Créer un `MetaData` avec la convention, l'attacher au `Base` via l'attribut
`metadata` :

```python
from sqlalchemy import MetaData
VulisMetaData = MetaData(naming_convention=NamingConvention)

class Base(DeclarativeBase):
    metadata = VulisMetaData
```

## 6. structlog — capture stdout dans les tests

### Le problème

```python
def test_log_emits(capsys):
    log.info("hello")
    out = capsys.readouterr().out
    assert "hello" in out  # FAIL : out est vide
```

### La cause

`structlog.PrintLoggerFactory(file=sys.stdout)` capture la **référence** à
`sys.stdout` au moment du `configure()`. Mais `pytest` remplace `sys.stdout`
plus tard, donc structlog écrit toujours vers le vieux stdout (non capturé).

### La solution

1. **Ne pas passer `file=` au factory** : `PrintLoggerFactory()` résout
   `sys.stdout` à chaque write (lazy).
2. **Utiliser `capfd` au lieu de `capsys`** dans les tests : `capfd` capture
   au niveau file descriptor, indépendamment de `sys.stdout`.
3. **`cache_logger_on_first_use=False`** pour que la re-config soit prise
   en compte (sinon le logger reste caché après le premier appel).

## 7. SemVer — ne pas faire confiance à l'`order=True` du dataclass

### Le problème

```python
@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    pre_release: tuple = ()

assert SemVer.parse("1.0.0-alpha") < SemVer.parse("1.0.0")  # FAIL
```

### La cause

L'`order=True` génère une comparaison tuple-à-tuple. Une `pre_release` non
vide est considérée "plus grande" qu'une vide (tuple non vide > tuple vide).
C'est l'inverse de la spec SemVer §11.

### La solution

Implémenter `_sort_key()` custom qui encode :
- Le core numérique normalement.
- Un booléen "has_pre_release" inversé (1 si pas de pre-release = plus grand,
  0 si pre-release = plus petit).
- Les identifiants pre-release : numériques avant strings (via tuple `(0, int)`
  vs `(1, str)`).

Implémenter `__eq__`, `__lt__`, etc. manuellement, et `__hash__` sur le
sort_key (pas sur les champs bruts).

## 8. `normalize_key` — résolution de `..`

### Le problème

```python
def normalize_key(key):
    parts = [p for p in key.split("/") if p not in ("", ".")]
    parts = [p for p in parts if p != ".."]   # drop naïf
    return "/".join(parts)

assert normalize_key("a/../b") == "b"  # FAIL : renvoie "a/b"
```

### La cause

Drop naïf ne résout pas `..`, il l'ignore. `"a/../b"` devrait donner `"b"`.

### La solution

Stack-based, type résolution POSIX :

```python
stack = []
for part in key.replace("\\", "/").split("/"):
    if part in ("", "."):
        continue
    if part == "..":
        if stack:
            stack.pop()  # résout ..
        # sinon : drop (ne jamais sortir de la racine)
        continue
    stack.append(part)
return "/".join(stack)
```

## 9. ruff B017 — `pytest.raises(Exception)` trop large

### Le problème

```python
with pytest.raises(Exception):  # ruff B017
    cfg.backend = "s3"
```

ruff râle car `Exception` est trop large — ça peut cacher un vrai bug.

### La solution (officielle)

Préciser le type : `pytest.raises(FrozenInstanceError)` ou
`pytest.raises(ValidationError)`.

### La solution (pragmatique, adoptée)

Pour les cas où on veut juste tester "n'importe quelle exception est levée"
(par exemple pour un stub S3 qui lève une `StorageError` custom), on a
autorisé B017 dans les tests via `per-file-ignores` :

```toml
[tool.ruff.lint]
per-file-ignores = { "tests/**" = ["B017"] }
```

À utiliser avec parcimonie. Préférer le type précis quand c'est possible.

## 10. uv workspace — `license-files` et `LicenseRef-`

### Le problème

```toml
license = "LicenseRef-Vulis-BSL-1.1"
license-files = ["../../LICENSE"]
```

PyPI/hatch peuvent râler sur `LicenseRef-` (pas un SPDX standard dans leur
liste). Pour l'instant on n'a pas publié, donc ça passe, mais à surveiller
avant publication PyPI.

### Solution (à appliquer si besoin)

Si PyPI rejette : retirer `license-files` du `pyproject.toml` ou ajouter une
`license = { text = "BSL-1.1" }` alternative. À trancher avant publication.

## 11. Alembic — `target_metadata` doit voir toutes les classes

### Le piège

Alembic autogenerate ne voit QUE les modèles déjà importés quand
`env.py` s'exécute. Si tu ajoutes un modèle dans `services/dataset/` mais
que l'`env.py` de `libs/schemas` ne l'importe pas, autogenerate ne le verra
pas.

### La solution

Chaque service doit avoir son propre `alembic env.py` qui :

1. Importe `Base.metadata` depuis `vulis_schemas`.
2. Importe **tous ses modèles** (`from vulis_dataset.models import *`).
3. Pointe `target_metadata` sur le `Base.metadata` partagé (les tables
   s'accumulent dedans).

OU : avoir un seul `alembic env.py` central qui importe tous les modèles
de tous les services. C'est plus simple mais couple les services. **À
décider en M1.3** quand le premier service arrive.

## 12. Mock-ingrérence `pytest` — `sys.modules` checks

### Le piège

```python
fmt = "console" if (sys.stderr.isatty() and "pytest" not in sys.modules) else "json"
```

C'est un hack pour éviter la sortie console en mode test. Fragile. À éviter
dans le nouveau code : préférer passer `fmt=` explicitement depuis le
paramétrage de test.

## 13. Mosquitto config — `message_size_limit`

### Le piège

Par défaut Mosquitto limite les messages à 1 MB. Sparkplug B peut dépasser
pour les payloads de télémétrie volumineux (images). Régler
`message_size_limit` dans la conf.

### Solution

```conf
# docker/compose/mosquitto/mosquitto.conf
message_size_limit 1048576    # 1MB par défaut, à augmenter si besoin
```

Mais : **ne jamais envoyer de gros blobs via MQTT**. MQTT ne signale que
l'existence ; les binaires sont pull via HTTP depuis le serveur.

## 14. Keycloak — export du realm en dev

### Le piège

L'export Keycloak via `kc.sh export` nécessite un realm déjà créé. Si tu
démolis les volumes, le realm disparaît.

### Solution (workflow dev)

1. Démarrer `task up` (Keycloak neuf, pas d'import).
2. Aller sur l'UI admin, créer le realm `vulis` + rôles + users + clients.
3. Exporter vers `docker/compose/keycloak/realms/vulis-realm-dev.json`.
4. Commit ce fichier.
5. Au prochain `task up`, Keycloak importe automatiquement.

## 15. Don't re-implement existing vulis_core types

### Le piège fréquent

```python
# MAUVAIS : un service réinvente ses propres IDs
class DatasetService:
    def create(self, dataset_id: str) -> ...   # str brut

# BON : utiliser les types vulis_core
from vulis_core import DatasetId
class DatasetService:
    def create(self, dataset_id: DatasetId) -> ...   # typé
```

**Toujours** importer et utiliser les types `vulis_core` (EntityId subclasses,
SemVer, exceptions, settings). Ne pas réinventer.

---

## Récap des "si tu ne te souviens de rien d'autre"

1. **`task check` avant commit.** Lint + format + typecheck + tests + reuse.
2. **Pas de f-string avec backslash** (Py 3.11).
3. **`pytest_addoption` dans `conftest.py`**, jamais dans les modules de test.
4. **Tests logging avec `capfd`**, pas `capsys`.
5. **Types `vulis_core` partout**, pas de `str` brut pour les IDs.
6. **Stockage via `StorageBackend`**, jamais `open()`.
7. **Factory `create_app()`** pour FastAPI, pas d'instance module-level.
8. **Une migration Alembic par changement de schéma**, test round-trip.
9. **ADR pour toute décision non-triviale** (copier `0000-template.md`).
10. **Commits Conventional + DCO sign-off**.
