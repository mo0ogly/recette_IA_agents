# recette_agentrail

> Application : **inspect_ia_agents** -- console + plateforme de recette +
> couche de gouvernance runtime.

Recette et corpus ground-truth pour inspect_ia_agents : valide la gouvernance runtime
des actions d'agents IA (policy allow/deny/escalate, approbation humaine
bloquante, audit immuable) sur les outils discovery et identification.

## Installation et demarrage

Prerequis : **Python >= 3.11**, **Node.js + npm >= 20**, `bash`/`curl`/`ss`.
Guide complet : [docs/runbooks/installation.md](docs/runbooks/installation.md).

Installer (le venv projet est repris automatiquement par `recette.sh`) :

```
python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e '.[api]'
```

Tout se pilote ensuite par `./recette.sh` (menu interactif ou CLI). Une seule
commande lance **le serveur applicatif** (API gouvernee `:8090`) **et les
serveurs appeles par les agents** (lab mock `:8082`, les 11 systemes simules) ;
puis la console :

```
./recette.sh platform up
./recette.sh console start
```

Puis ouvrir le **cockpit** sur **http://localhost:5173**. Il demarre sur
l'onglet **Cockpit** : choisir un agent, mock ou IA reelle, le lancer, suivre
le flux live, l'arreter. Onglet **Recette** pour scorer discovery /
identification vs ground-truth ; onglet **Campagnes** pour des jeux d'agents
persistes avec replay deterministe (I4). Arret : `./recette.sh platform down` ;
en cas de serveur bloque : `./recette.sh platform purge`.

> Note : l'API tourne sur :8090 (ou 1er port libre 8090-8099, voir
> `.run/api.port`) -- port JSON, pas une page web (`GET /` renvoie `404`
> normalement). L'UX graphique est le cockpit sur :5173.

Guide complet du menu et de l'application :
[docs/runbooks/recette-sh.md](docs/runbooks/recette-sh.md).

**Documentation de fond** (raison d'etre, architecture, diagrammes, types
d'agents en detail, chemin d'execution gouverne) :
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Composants

| Composant | Description | Doc |
|-----------|-------------|-----|
| **Cockpit (console UX)** | Interface React/Vite de recette discovery : configurer/lancer/arreter des agents (mock ou IA reelle), scorer discovery + identification vs ground-truth, campagnes persistees + replay deterministe (I4), CRUD ai-backends. | [console/README.md](console/README.md), [recette-sh.md](docs/runbooks/recette-sh.md) |
| **Runs & campagnes** | Lancement d'agents Lane B (mock/IA), runners discovery/identification, campagnes persistees, enregistrements rejouables. API `/runs`, `/campaigns`, `/recordings` + WebSocket live. | [platform.md](docs/runbooks/platform.md) |
| **Plateforme gouvernee (mock)** | Gateway (I2), policy engine versionne (deny-by-default), approbations (I6), event store SQLite append-only hash-chaine (I1), proxy lab (I5). Catalogue de 118 actions. Onglets secondaires, en attente de tri. | [platform.md](docs/runbooks/platform.md) |
| **Track U -- API (U1)** | Expose les capacites CLI (identification / discovery / Lane B), config et catalogue d'agents en HTTP + WebSocket. Defaut lab forge (zero effet de bord), secrets en env (R8). | [api.md](docs/runbooks/api.md) |
| **Discovery recette** | Corpus de repos de test + scorecard d'invariants pour l'outil de discovery. | [github-discovery-recette.md](docs/runbooks/github-discovery-recette.md) |
| **Lab (doubles realistes)** | 14 domaines simules (`recette/lab/domains/`) : champs metier par action, validation -> 422, deterministes (I4). Campagnes multi-domaines composees. | [lab-realistic-doubles.md](docs/runbooks/lab-realistic-doubles.md) |

## Tests et qualite

```
./recette.sh test     # unittest stdlib (offline)
./recette.sh gates    # ruff + mypy + bandit
./recette.sh platform up && ./recette.sh campaign run redteam-probe   # boite noire
```

## Licence

Source-available sous **PolyForm Noncommercial License 1.0.0** : usage,
etude, modification et recette libres a des fins **non commerciales**
(recherche, enseignement, organismes publics, projets personnels). Tout
usage commercial requiert une licence separee du mainteneur
(mo0ogly@proton.me). Texte complet : [LICENSE](LICENSE).
