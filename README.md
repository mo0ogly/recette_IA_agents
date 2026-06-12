# recette_agentrail

Recette et corpus ground-truth pour AgentRail : valide la gouvernance runtime
des actions d'agents IA (policy allow/deny/escalate, approbation humaine
bloquante, audit immuable) sur les outils discovery et identification.

## Demarrage rapide

Tout se pilote par `./recette.sh` (menu interactif ou CLI). Pour la plateforme
d'execution gouvernee + la console + une campagne :

```
./recette.sh platform up
./recette.sh console start
./recette.sh campaign run identity-offboarding --json
```

Puis ouvrir l'interface graphique sur **http://localhost:5173** (onglet
Approvals pour approuver les actions en attente). Arret : `./recette.sh
platform down` ; en cas de serveur bloque : `./recette.sh platform purge`.

> Note : l'API tourne sur :8090 (port JSON, pas une page web -- `GET /` y
> renvoie `404` normalement). L'UX graphique est la console sur :5173.

Guide complet du menu et de l'application :
[docs/runbooks/recette-sh.md](docs/runbooks/recette-sh.md).

## Composants

| Composant | Description | Doc |
|-----------|-------------|-----|
| **Plateforme gouvernee** | Gateway (I2), policy engine versionne (deny-by-default), approbations (I6), event store SQLite append-only hash-chaine (I1), proxy lab (I5). Catalogue de 118 actions sensibles sur 11 systemes. | [recette-sh.md](docs/runbooks/recette-sh.md), [platform.md](docs/runbooks/platform.md) |
| **Console UX** | Interface React/Vite : parametrage IA des agents, editeur de policy, inbox d'approbations, journal d'audit. | [recette-sh.md](docs/runbooks/recette-sh.md) |
| **Campagnes** | Scenarios JSON d'actions gouvernees, executes en boite noire avec verification de chaine d'audit. | [recette-sh.md](docs/runbooks/recette-sh.md) |
| **Track U -- API (U1)** | Expose les capacites CLI (identification / discovery / Lane B), config et catalogue d'agents en HTTP + WebSocket. Defaut lab forge (zero effet de bord), secrets en env (R8). | [api.md](docs/runbooks/api.md) |
| **Discovery recette** | Corpus de repos de test + scorecard d'invariants pour l'outil de discovery. | [github-discovery-recette.md](docs/runbooks/github-discovery-recette.md) |

## Tests et qualite

```
./recette.sh test     # unittest stdlib (offline)
./recette.sh gates    # ruff + mypy + bandit
./recette.sh platform up && ./recette.sh campaign run redteam-probe   # boite noire
```
