# Installation et demarrage -- inspect_ia_agents

Cette doc installe le projet et lance, **uniquement via `./recette.sh`**
(R19 -- point d'entree unique), les deux familles de serveurs :

- le **serveur applicatif** : l'API gouvernee (`:8090`) + la console UX (`:5173`) ;
- les **serveurs appeles par les agents** : le lab mock (`:8082`) plus les 12
  serveurs par-domaine (`:9101`-`:9112`) qui simulent les 16 systemes gouvernes
  (okta, github, gitlab, finance, slack, comms, compliance, ...). C'est ce que touche
  un agent quand il execute une action -- jamais un vrai SaaS par defaut (lab
  forge, zero effet de bord, I5).

> `./recette.sh platform up` demarre **dans l'ordre** le lab mock PUIS l'API : un
> seul commande couvre le serveur applicatif et les serveurs appeles par les
> agents.

---

## 1. Prerequis

| Outil | Version | Role |
|-------|---------|------|
| Python | >= 3.11 | recette, lab mock, API |
| Node.js + npm | >= 20 | console UX (vite) |
| bash, curl, ss | -- | `recette.sh` et ses sondes de sante |

Le lab mock (les serveurs appeles par les agents) est en **stdlib pure** : aucune
dependance a installer pour lui. Seule l'API a besoin de l'extra `[api]`
(FastAPI + uvicorn).

---

## 2. Recuperer le code

```
git clone <url-du-repo> recette_agentrail
cd recette_agentrail
```

---

## 3. Installer les dependances

### 3a. Python (venv projet)

`recette.sh` utilise automatiquement `.venv/bin/python` s'il existe, sinon le
`python3` du systeme. Creer le venv et installer l'extra API :

```
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e '.[api]'
```

`-e '.[api]'` tire `jsonschema` (coeur recette) + `fastapi` + `uvicorn` (serveur
applicatif). Extras optionnels selon besoin : `.[real]` (vrais GitHub/GitLab),
`.[dev]` (ruff/mypy/pytest), `.[bundle]`, `.[postgres]`, `.[nats]`.

### 3b. Console UX (Node)

Rien a faire a la main : `./recette.sh console start` lance `npm install` au
premier demarrage.

---

## 4. Lancer les serveurs via `recette.sh`

```
./recette.sh platform up
./recette.sh console start
```

- `platform up` demarre le **lab mock `:8082`** + les 12 serveurs par-domaine
  (`:9101`-`:9112`, les 16 systemes appeles par les
  agents) puis l'**API gouvernee `:8090`** (ou 1er port libre 8090-8099, persiste
  dans `.run/api.port`).
- `console start` lance la **console `:5173`**, cablee automatiquement sur le
  port API resolu (`VITE_INSPECT_IA_AGENTS_API_URL`).

Ouvrir ensuite **http://localhost:5173** (l'UX graphique ; l'API `:8090` est du
JSON, `GET /` y renvoie `404` -- normal).

### Serveurs cibles supplementaires

Le lab mock `:8082` est le serveur appele par defaut. Pour brancher d'autres
cibles (un mock local dedie, une URL declaree, un SaaS reel), les declarer dans
l'onglet **Servers** de la console -- ils sont demarres/arretes a la demande par
l'API (`mock_local` lance son propre process ; `declared_url` pointe une URL
existante ; `real_saas` tape un vrai systeme). Ces serveurs-la ne passent pas par
`recette.sh` mais par la console / l'API.

---

## 5. Verifier

```
./recette.sh platform status
curl -s http://127.0.0.1:8082/healthz        # lab mock (serveurs agents)
curl -s http://127.0.0.1:8090/health         # API applicative (adapter le port via .run/api.port)
```

`platform status` affiche le pid/port de chaque service et l'etat de la chaine
d'audit (`GET /audit/verify`).

---

## 6. Arreter

```
./recette.sh platform down       # arret propre lab + API (+ console)
./recette.sh console stop        # console seule
./recette.sh platform purge      # si un serveur local du repo est reste bloque
```

`purge` ne balaie que les process ancres dans CE repo (API, lab, vite) ; jamais
un container Docker ni un process exterieur.

---

## 7. Ports et configuration

| Service | Port defaut | Override (env, R5) |
|---------|-------------|--------------------|
| API applicative | 8090 (auto 8090-8099) | `INSPECT_IA_AGENTS_API_PORT` |
| lab mock (serveurs agents) | 8082 | `INSPECT_IA_AGENTS_LAB_PORT` |
| console UX | 5173 | `INSPECT_IA_AGENTS_CONSOLE_PORT` |

Defauts dans `cicd/lib/common.sh`. Etat d'execution sous `.run/` (`api.pid`,
`api.port`, `lab.pid`, `console.pid`, `*.log`). Aucun secret stocke (R8) -- les
credentials de systemes reels viennent de l'environnement.

---

## 8. Voir aussi

- Guide operateur complet (menu interactif + toutes les commandes) :
  [recette-sh.md](recette-sh.md).
- Architecture, plans Control/Data/Audit, types d'agents : [../ARCHITECTURE.md](../ARCHITECTURE.md).
- API Track U : [api.md](api.md). Plateforme + e2e : [platform.md](platform.md).
