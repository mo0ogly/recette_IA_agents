# Runbook -- Recette Discovery GitHub

Comment un developpeur valide le GitHubScanner du plan Discovery / Enrichment (`:8081`)
contre les depots d'agents de test ground-truth de ce repo.

## Ce que vous obtenez

- 4 depots d'agents de test realistes sous `corpus/repos/` (benin read-only, PR bot moyen,
  syncer d'infra a haut risque, et une bibliotheque vrai-negatif).
- Un harnais qui note le scanner sur des proprietes invariantes (detection, count/dedup,
  couverture d'action, target, ordre relatif de risque, determinisme, presence de policy, FP/FN).
- Un oracle de reference hors ligne pour que la recette ait du sens meme avant que `:8081` soit joignable.

## Installation (one shot)

### Prerequis

| Prerequis | Pourquoi | Verification |
|-------------|-----|-------|
| Python >= 3.11 | `StrEnum` + typing moderne dans le package recette | `python3 --version` |
| Checkout du repo accessible en ecriture | le script cree `.venv` et `.venv-pyaudit` dans l'arbre | `test -w .` |
| Docker + Compose v2 (optionnel) | lab reproductible (`runtime` ~153MB, `audit` ~324MB) | `docker compose version` |
| Port TCP 8081 libre (chemin Docker uniquement) | le service Discovery mock s'y attache | `ss -ltn 'sport = :8081'` |

Docker est optionnel : passer `--no-docker` (ou `make install` sur un hote sans Docker saute
simplement le lab avec un `[WARN]`, l'installation native reussit quand meme).

```bash
make install          # native venv + Docker lab, each step smoke-tested
make install-check    # report status only, change nothing
```

`scripts/install.sh` cree `.venv` (recette installe en editable), bootstrappe le venv d'audit
(`.venv-pyaudit`), puis verifie : `recette validate`, la scorecard de discovery hors ligne
(`VERDICT: PASS`), la suite unittest, et -- quand Docker est present -- construit les
images `runtime`/`audit` et lance les tests conteneur, les gates strictes, et la recette
discovery HTTP contre le mock `:8081`. Flags : `--no-docker`, `--with-real`, `--check`.

Le script est idempotent et reexecutable sans risque (`set -Eeuo pipefail` ; une interruption ou
une erreur demonte automatiquement le lab Docker afin qu'aucun conteneur orphelin ne subsiste). Il ne
revendique jamais le succes sans avoir execute la recette, et sort en code non-nul si une etape echoue. Les
executions paralleles n'entrent pas en collision : chaque invocation utilise un `COMPOSE_PROJECT_NAME` unique et un
port hote ephemere (`DISCOVERY_HOST_PORT=0`), de sorte que son teardown ne touche que ses propres conteneurs.
`make lab` interactif garde le `:8081` fixe par commodite.

### Si une etape echoue

| Symptome (sortie du script) | Cause | Correction |
|-------------------------|-------|-----|
| `python3 not found` / `... too old` | Python < 3.11 | installer Python 3.11+, relancer |
| `pyproject.toml not found ...` | execution hors du repo | `cd` dans la racine du repo d'abord |
| `Repo root ... is not writable` | permissions | corriger ownership/permissions du checkout |
| `docker build FAILED` | daemon down / pas de disque | demarrer Docker, liberer du disque, ou `make install` avec `--no-docker` |
| `docker-compose.yml is invalid` | fichier compose invalide/edite | `docker compose config` pour voir l'erreur |
| `HTTP discovery recette FAILED` | port 8081 occupe ou mock unhealthy | `make lab-down`, liberer `:8081`, relancer |
| pip bloque/avorte | reseau/proxy instable | le script retente 3x ; verifier la connectivite/`HTTPS_PROXY`, relancer |

Les secrets (`INSPECT_IA_AGENTS_DISCOVERY_TOKEN`, `gh auth`) proviennent uniquement de votre environnement -- ne jamais
les committer. Les extras `--with-real` (`PyGithub`, `python-gitlab`) sont optionnels et seulement
necessaires pour la section B contre une org reelle.

## 0. Lab Docker (reproductible, recommande)

Tout s'execute dans un conteneur pour que la toolchain (Python + outils d'audit) et le service
Discovery mock soient identiques pour tout le monde :

```bash
make docker-build            # build the lab image
make lab                     # discovery recette over HTTP vs the mock :8081 -> scorecard PASS
make docker-test             # full test suite in the image (51 tests)
make docker-gates            # strict ruff + ruff format + mypy + bandit -> gates PASS
make lab-down                # stop the lab
```

`make lab` demarre `discovery-mock` (un service `:8081` stdlib adosse a l'oracle de reference
-- un double de lab du plan Discovery/Enrichment du collegue) et lance le service
`recette` contre lui via le reseau Docker. Pour cibler le service REEL du collegue
a la place, definir `INSPECT_IA_AGENTS_DISCOVERY_URL` sur le service `recette` dans
`docker-compose.yml` (ou lancer `recette discovery --adapter http` avec cet env en local).

## A. Pre-vol hors ligne (aucun scanner requis)

```bash
python3 -m recette validate
python3 -m recette discovery --adapter reference
python3 -m unittest discover -s tests
```

`discovery --adapter reference` doit afficher `VERDICT: PASS`. Cela prouve que le corpus +
le ground-truth sont coherents en interne et definissent exactement ce qu'un scanner correct doit produire.

## B. Publier les depots d'agents de test sur GitHub

Dry-run d'abord (affiche le plan, ne touche a rien) :

```bash
python3 -m recette publish gh-readonly-reporter --owner <your-test-org>
python3 -m recette publish gh-pr-bot --owner <your-test-org>
python3 -m recette publish gh-admin-overreach --owner <your-test-org>
python3 -m recette publish gh-no-agent --owner <your-test-org>
```

Les creer pour de vrai (requiert `gh auth login` sur un compte ayant les droits de creation sur l'org) :

```bash
python3 -m recette publish gh-readonly-reporter --owner <your-test-org> --apply
python3 -m recette publish gh-pr-bot --owner <your-test-org> --apply
python3 -m recette publish gh-admin-overreach --owner <your-test-org> --apply
python3 -m recette publish gh-no-agent --owner <your-test-org> --apply
```

Le publisher refuse de toucher un depot qui existe deja et ne force-push jamais.

## C. Pointer le scanner Discovery sur les depots et le noter

Definir la connexion (tenant de dev + URL du service + token depuis votre environnement) :

```bash
export INSPECT_IA_AGENTS_DISCOVERY_URL=http://127.0.0.1:8081
export INSPECT_IA_AGENTS_TENANT=<tenant>
export INSPECT_IA_AGENTS_DISCOVERY_TOKEN=<token>
python3 -m recette discovery --adapter http
```

Le harnais enregistre chaque depot publie comme `discovery_source`, declenche un scan, lit
`discovery_risks`, et affiche la scorecard.

> Les routes REST `:8081` et la forme JSON `estimated_risk` sont presumees dans
> `recette/http_adapter.py` (constantes `ROUTE_*`, `_unwrap`, et le parsing `risks()`).
> Si l'API Discovery reelle differe, ajuster ce seul fichier -- rien d'autre ne change.

## D. Lire la scorecard

Un scanner correct produit :
- detection 100% (3 agents trouves, `gh-no-agent` non signale -> 0 faux positifs),
- couverture d'action 100% (les patterns d'action plantes remontes),
- ordre de risque OK (`gh-readonly-reporter` < `gh-pr-bot` < `gh-admin-overreach`),
- determinisme OK (re-scan identique),
- policy emise pour les agents moyen/haut.

Toute cellule `MISS` ou un compte de faux positifs/negatifs non-nul pointe le depot exact et la
dimension exacte a investiguer contre son `discovery-ground-truth.json`.

## Notes

- La recette ne compare jamais de valeurs opaques (`canonical_agent_id`, score de risque exact) -- seulement
  des proprietes invariantes (l'invariant d'archi 2 + le fingerprinting sont internes au scanner).
- Le realisme est statique : les depots contiennent du vrai code d'agent executable + CI/CD + manifest, mais
  la recette ne les execute pas (aucun effet de bord GitHub reel).
