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
| Rust (rustup) + `bpf-linker` | nightly (epingle) | **moteur discovery Rust (eBPF live)** -- optionnel mais c'est le coeur (section 5) |
| `setcap`/`getcap` (libcap), kernel BTF (`/sys/kernel/btf/vmlinux`) | -- | meme usage : charger l'eBPF (CAP_BPF) |

Le lab mock (les serveurs appeles par les agents) est en **stdlib pure** : aucune
dependance a installer pour lui. Seule l'API a besoin de l'extra `[api]`
(FastAPI + uvicorn). Le **moteur discovery Rust** (section 5) est optionnel : sans
lui, le broker tourne en mode `replay` deterministe (zero privilege) et l'UX
fonctionne ; avec lui, le broker voit les **vraies** comms agent<->serveur au
niveau kernel (exec + connect).

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

## 5. Moteur de discovery Rust (eBPF live) -- le coeur

Le **noyau discovery natif** (`discoveryprobe/`, Rust + eBPF) est le coeur du
produit : il VOIT au niveau kernel ce qu'un agent fait vraiment (exec + connect
sortant), pas seulement ce qui passe par le proxy applicatif. Sans lui, le broker
demarre en mode `replay` (Python, deterministe, zero privilege) -- l'UX marche,
mais sur une rejoue du corpus, pas sur du trafic reel.

Le provisioning est **entierement via `recette.sh`** (R19). Une seule etape est
privilegiee -- accorder CAP_BPF -- car charger un programme eBPF l'exige ; c'est
**ponctuel** (une fois par hote, ou apres un rebuild du broker).

```
./recette.sh discovery-build      # moteurs natifs (catalog, detect, broker)
./recette.sh probe-ebpf-build     # objet eBPF + broker CAP_BPF
./recette.sh probe-grant-caps     # PONCTUEL (sudo) : cap_bpf,cap_perfmon,cap_net_admin,cap_dac_read_search+ep
./recette.sh platform up          # le launcher demarre AUTO le broker LIVE (caps presents)
```

Le launcher detecte les caps (`_probe_live_capable`) et choisit seul le broker
live ; il ecrit le mode dans `.run/probe.mode` et l'API le lit -- pas de variable
d'env a poser a la main. Verifier :

```
cat .run/probe.mode                                  # -> live
curl -s http://127.0.0.1:8090/probe/status           # -> {"configured":true,...,"mode":"live"}
```

Preuve que le moteur voit une vraie comm (capture par PID d'un agent mock lie a
un serveur lab) :

```
curl -s -X POST http://127.0.0.1:8090/probe/process-capture -H 'content-type: application/json' -d '{"agent_id":"dx-live-bot","duration_ms":4000}'
# -> recordings[0].surfaces.ebpf_wire = ["connect:127.0.0.1:9101"], scorecard.ok=true
```

Depuis l'UX : page **Discovery x Echange**, toggle source **eBPF (live)**, ou
lancer un agent en **Mode process (eBPF)** -- le verdict DETECTE/GHOST vient du
broker live, en regard du vrai echange (proxy) a gauche. Le moteur voit, sur la
surface `ebpf_wire` : `exec:` (process), `connect:` (egress, nomme au serveur
declare), `open:` (acces fichier), `dns:` (nom resolu), et les liens
parent->enfant (`sched_process_fork`) pour attribuer un process enfant a l'agent.
Detail : [ebpf-live-capture.md](ebpf-live-capture.md).

> Important : un **rebuild du broker** (`probe-ebpf-build` / `discovery-build`)
> remet a zero les file-caps -> relancer `./recette.sh probe-grant-caps`. C'est la
> seule recurrence. Sans les caps, le broker retombe en `replay` (fail-safe : il
> ne fabrique jamais une capture, il ne tente jamais un load qui ferait EPERM).

Detail (least-privilege vs sudo, manifest, teardown) : [ebpf-live-capture.md](ebpf-live-capture.md).

---

## 6. Verifier

```
./recette.sh platform status
curl -s http://127.0.0.1:8082/healthz        # lab mock (serveurs agents)
curl -s http://127.0.0.1:8090/health         # API applicative (adapter le port via .run/api.port)
```

`platform status` affiche le pid/port de chaque service et l'etat de la chaine
d'audit (`GET /audit/verify`).

---

## 7. Arreter

```
./recette.sh platform down       # arret propre lab + API (+ console)
./recette.sh console stop        # console seule
./recette.sh platform purge      # si un serveur local du repo est reste bloque
```

`purge` ne balaie que les process ancres dans CE repo (API, lab, vite) ; jamais
un container Docker ni un process exterieur.

---

## 8. Ports et configuration

| Service | Port defaut | Override (env, R5) |
|---------|-------------|--------------------|
| API applicative | 8090 (auto 8090-8099) | `INSPECT_IA_AGENTS_API_PORT` |
| lab mock (serveurs agents) | 8082 | `INSPECT_IA_AGENTS_LAB_PORT` |
| console UX | 5173 | `INSPECT_IA_AGENTS_CONSOLE_PORT` |

Defauts dans `cicd/lib/common.sh`. Etat d'execution sous `.run/` (`api.pid`,
`api.port`, `lab.pid`, `console.pid`, `*.log`). Aucun secret stocke (R8) -- les
credentials de systemes reels viennent de l'environnement.

---

## 9. Voir aussi

- Guide operateur complet (menu interactif + toutes les commandes) :
  [recette-sh.md](recette-sh.md).
- Architecture, plans Control/Data/Audit, types d'agents : [../ARCHITECTURE.md](../ARCHITECTURE.md).
- API Track U : [api.md](api.md). Plateforme + e2e : [platform.md](platform.md).
