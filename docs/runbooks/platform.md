# Runbook du lab plateforme -- execution gouvernee (gateway + lab mock + e2e)

Exploite le lab docker L1 : l'API inspect_ia_agents (Gateway, plan
Control/Audit) cablee au lab d'external-systems simules, plus la recette
end-to-end du flux gouverne qui prouve l'ensemble du chemin.

## Architecture

Trois plans, un seul chemin gouverne. Aucune action n'atteint un external
system sans decision de policy (I2), les effets de bord ne transitent que par
le proxy (I5), chaque etape est un evenement d'audit append-only (I1).

```
        agent / console / curl
                 |
                 v
  +---------------------------------------------+
  | api (recette.api, :8090)        CONTROL     |
  |                                              |
  |  POST /actions/execute                       |
  |     |  capture timestamp (I4 input)          |
  |     v                                        |
  |  Gateway: resolve agent (config store, I3*)  |
  |     -> normalize to PlatformActionEvent      |
  |     -> policy decide (versioned, deny-by-    |
  |        default)                              |
  |          allow    -> execute via proxy       |
  |          deny     -> audit, never executed   |
  |          escalate -> pending, BLOCKED (I6)   |
  +-----------------+---------------------------+
                    | allow / approved only
                    v
  +---------------------------------------------+
  | LabHttpProxy (I5)               DATA         |
  |   POST http://lab-mock:8082/{target}/execute |
  |   -> side_effect_hash recorded               |
  +-----------------+---------------------------+
                    | every transition
                    v
  +---------------------------------------------+
  | SQLite event store (/data/events.db) AUDIT   |
  |   append-only, hash-chained (I1)             |
  |   GET /audit/events, GET /audit/verify       |
  +---------------------------------------------+
```

Services Docker (docker-compose.yml) :

| Service | Cible d'image | Role |
|---------|--------------|------|
| `platform-init` | runtime (en root, one-shot) | chown du volume `platform-data` fraichement cree vers l'utilisateur non-root `recette` |
| `lab-mock` | runtime | double lab des 16 external systems, `:8082` |
| `api` | runtime | gateway + API control/audit, `:8090`, etat sur `platform-data` |
| `e2e` | audit | execute `tests/e2e/test_governed_flow.py` contre `api` |

## Endpoints

| Methode | Chemin | Objet |
|--------|------|---------|
| GET | `/health` | liveness |
| POST | `/actions/execute` | soumettre une action gouvernee ; `202` quand escaladee en pending |
| GET | `/actions/{event_id}` | evenement stocke ; `resolution` renseigne une fois le pending resolu |
| GET | `/approvals?state=pending` | boite de reception d'approbation (fold sur le log d'evenements) |
| POST | `/approvals/{event_id}/approve` | resout pending -> approved, execute via le proxy |
| POST | `/approvals/{event_id}/deny` | resout pending -> denied, jamais execute |
| POST | `/approvals/sweep-timeouts` | expire les pendings ; `{"now": ISO-8601}` optionnel (I4 input) |
| GET | `/audit/events` | requete sur le log d'evenements (`from_seq`, `agent_id`, `target_system`, `kind`, `limit`) |
| GET | `/audit/verify` | rapport de verification de la hash-chain |
| GET | `/policies` | liste des versions de policy |
| GET | `/policies/active` | document de policy actif |
| PUT | `/policies/active` | bascule la version active (ne mute jamais un document) |
| GET | `/policies/{version}` | une version immuable |
| POST | `/policies` | publie une nouvelle version |
| GET / POST | `/config/agents` | registre des agents (source d'identite, voir limitations) |
| PUT / DELETE | `/config/agents/{id}` | met a jour / supprime un agent |
| GET / POST / DELETE | `/config/ai-backends` | registre des backends IA (aucun secret stocke, R8) ; 8 providers : anthropic, openai, gemini, groq, mistral, deepseek, xai, openai_compat (`base_url`) |
| POST | `/config/ai-backends/{id}/test` | sonde de connectivite (un appel reel minimal) ; toujours 200 avec `{ok, latency_ms, error?}` -- diagnostic fail-safe, jamais un 500 |
| GET / POST | `/config/servers` | registre des serveurs : `mock_local` (port), `declared_url` (base_url, contrat wire du lab), `real_saas` (pas encore de proxy) |
| PUT / DELETE | `/config/servers/{id}` | met a jour / supprime une entree serveur |
| POST | `/config/servers/{id}/start`, `/stop` | cycle de vie d'un serveur lab `mock_local` (ServerManager) ; `{"status": "down", "error": ...}` est un resultat metier, pas une erreur de transport |
| GET | `/config/servers/{id}/status` | statut live : poll de process (`mock_local`), sonde d'URL (`declared_url`), `n/a` (`real_saas`) |
| GET | `/config/servers/{id}/log?after=N` | tail incremental du log d'acces JSONL du serveur (curseur `next`) |
| POST | `/config/servers/{id}/test` | declenche une action (`{action_type, resource?, payload?}`) vers le serveur via le proxy de run (I5) ; renvoie `{ok, latency_ms, status_code, response, side_effect_hash, error?}` -- fail-safe (serveur down / action invalide -> `ok:false`, jamais un 500) ; id inconnu 404, `real_saas` 400 |
| GET | `/catalog/actions` | catalogue des actions a haut risque (verdicts + niveaux de risque) |
| GET | `/agents`, POST `/agents/register` | catalogue des agents Lane B |
| POST | `/runs` | lance un run ; `kind` = `lane_b` \| `discovery` \| `identification` \| `campaign` \| `replay` |
| GET | `/runs/{id}`, `/runs/{id}/events`, WS `/runs/{id}/ws` | statut du run, frames bufferisees, flux live de frames |
| POST | `/runs/{id}/stop` | arret cooperatif |
| GET / POST | `/campaigns` | liste / cree une campagne persistee (lancements d'agents ordonnes) |
| GET / DELETE | `/campaigns/{id}` | une campagne / la supprime |
| POST | `/campaigns/{id}/run` | execute la campagne ; streame via le WebSocket de run, persiste un recording par etape |
| GET | `/recordings`, `/recordings/{id}` | liste / recupere les recordings rejouables |
| POST | `/recordings/{id}/replay` | rejoue deterministiquement un recording (I4) ; la frame `replay_result` reporte `matches_original` |

## Types de run et frames

Chaque run est execute dans un thread worker par le RunManager et emet des
frames `{seq, type, data}` bufferisees sur le run et poussees en live aux
abonnes WebSocket. La premiere frame est toujours `start`, la derniere est `end`
avec le statut final.

| Kind | Params du body | Frames metier |
|------|-------------|---------------|
| `lane_b` | `agent_id`, `stub_script` optionnel (mock ; sinon l'`ai_backend` de l'agent pilote un LLM live, cle depuis l'env, R8) | `step` (par action de l'agent), `result` (actions enregistrees) |
| `discovery` | `surface` optionnel (par defaut toutes) | `scorecard` par surface (total/passed/false_positives/false_negatives/all_passed) |
| `identification` | aucun | `agent_result` par agent (verdict predit vs attendu), `scorecard` final (+ detection_rate) |
| `campaign` | (via `/campaigns/{id}/run`) | `agent_start` / `step` / `agent_done` par etape, `campaign_done` final ; un recording persiste par etape |
| `replay` | (via `/recordings/{id}/replay`) | `step` par decision rejouee, `replay_result` avec `matches_original` (I4) |

`capability_scope` est l'ensemble des actions du catalogue qu'un agent peut
appeler (152 actions reparties sur 16 systemes, `GET /agent-actions`), pas un nom
de systeme. Les 11 actions git canoniques (`read_repo` ... `trigger_ci`) sont le
sous-ensemble github/gitlab.

Routage de cible par agent : un agent avec un binding `server` execute via un
`ProxyForge` (HTTP reel vers le serveur resolu, I5) ; sans binding il conserve le
`LabForge` en memoire. Une reference de serveur pendante ou non supportee fait
echouer le run -- jamais un fallback silencieux.

## Variables d'environnement (R5)

| Variable | Utilisee par | Defaut | Valeur du lab Docker |
|----------|---------|---------|------------------|
| `INSPECT_IA_AGENTS_API_HOST` | api | `127.0.0.1` | `0.0.0.0` |
| `INSPECT_IA_AGENTS_API_PORT` | api | `8090` | `8090` |
| `INSPECT_IA_AGENTS_LAB_URL` | api (proxy) | `http://localhost:8082` | `http://lab-mock:8082` |
| `INSPECT_IA_AGENTS_EVENT_STORE_PATH` | api (audit) | `data/inspect_ia_agents.events.db` | `/data/events.db` |
| `INSPECT_IA_AGENTS_POLICIES_DIR` | api (policy store) | `config/policies` | `/data/policies` |
| `INSPECT_IA_AGENTS_CONFIG_PATH` | api (config agent/backend) | `config/inspect_ia_agents.config.json` | `/data/config.json` |
| `INSPECT_IA_AGENTS_CAMPAIGNS_PATH` | api (catalogue de campagnes) | `config/campaigns.json` | `/data/campaigns.json` |
| `INSPECT_IA_AGENTS_RECORDINGS_DIR` | api (recordings rejouables) | `data/recordings` | `/data/recordings` |
| `INSPECT_IA_AGENTS_CORS_ORIGINS` | api (console cross-origin) | `http://localhost:5173,http://127.0.0.1:5173` | origine(s) de la console |
| `INSPECT_IA_AGENTS_LAB_PORT` | lab-mock | `8082` | `8082` |
| `INSPECT_IA_AGENTS_LAB_ACCESS_LOG` | lab-mock | non defini (pas de log) | defini par le ServerManager par serveur gere (`data/lab/{id}.access.jsonl`) ; une ligne JSONL `{event_id, target_system, action_type, resource, status}` par requete -- la surface de capture runtime pour la discovery |
| `INSPECT_IA_AGENTS_E2E_API_URL` | tests e2e | non defini (suite skippee) | `http://api:8090` |
| `LAB_HOST_PORT` | mapping de port compose | `8082` | port hote pour lab-mock |
| `API_HOST_PORT` | mapping de port compose | `8090` | port hote pour api |
| `VITE_INSPECT_IA_AGENTS_API_URL` | console (Vite) | `http://localhost:8090` | mis a l'URL de l'api |

## Modes de defaillance (fail-safe, jamais fail-open)

| Defaillance | Comportement |
|---------|----------|
| L'evaluation de policy leve une exception | DENY par defaut + evenement `platform_error` audite ; l'action ne s'execute jamais |
| Identite d'agent inconnue | DENY, audite (`deny_reason: unknown agent identity`) |
| Proxy lab down / non-2xx | evenement `platform_error` audite, `executed: false`, pas de bypass, pas de retry-around |
| L'ecriture dans l'event store echoue sur le chemin deny/pending | l'action n'est pas executee : une action non auditee ne doit pas tourner |
| Timeout d'approbation | resolution explicite `timeout` via le sweep, jamais d'auto-approve (I6) |
| Aucune version de policy active | erreur dure -> DENY ; la gateway ne devine jamais une policy |

## Limitations connues

- I3 est partiel : l'identite de l'agent est resolue depuis le config store par
  id. Il n'y a pas de liaison cryptographique (pas de requetes signees, pas de
  mTLS). Travail de Phase 2 documente.
- Le service d'approbation est un placeholder Temporal : les pendings sont un
  fold sur le log d'evenements et les timeouts sont resolus par un endpoint de
  sweep explicite, pas par un workflow durable.
- `risk_score` est un mapping statique depuis le niveau de risque du catalogue
  (low/medium/high/critical), pas une sortie calculee d'un Risk Engine.
- Le mock du lab est deterministe et stateless ; il ne simule pas les
  defaillances des external systems (utiliser les tests de mode de defaillance
  du proxy pour cela).

## Comment lancer

### Via `recette.sh` (recommande pour le dev local)

Le chemin le plus simple -- demarre le mock du lab + l'API avec le cablage
complet de la plateforme, choisit automatiquement un port libre si 8090 est pris,
et expose la console et les campagnes :

```
./recette.sh platform up
./recette.sh console start
./recette.sh campaign run identity-offboarding --json
./recette.sh platform status
./recette.sh platform down
./recette.sh platform purge
```

Le port d'API resolu est persiste dans `.run/api.port` ; les commandes console et
campaign le lisent automatiquement. Voir
[recette-sh.md](recette-sh.md) pour le menu complet et la reference des commandes.

### Lab Docker (le build a lieu a la premiere utilisation)

```
make platform-lab
make platform-e2e
make platform-down
```

Smoke manuel contre l'API dockerisee (une commande par ligne, R24) :

```
curl -s http://localhost:8090/health
curl -s -X POST http://localhost:8090/config/agents -H "Content-Type: application/json" -d '{"id":"demo-admin","runtime":"lab","role":"identity_admin","capability_scope":["okta"]}'
curl -s -X POST http://localhost:8090/actions/execute -H "Content-Type: application/json" -d '{"agent_id":"demo-admin","action_type":"suspend_user","target_system":"okta","resource":"user:demo-1","payload":{}}'
curl -s "http://localhost:8090/approvals?state=pending"
curl -s -X POST http://localhost:8090/approvals/EV000000000000000001000001/approve -H "Content-Type: application/json" -d '{"approver":"ops","reason":"demo"}'
curl -s http://localhost:8090/audit/verify
```

Remplacer l'id `EV...` par l'`event_id` renvoye par l'appel execute.

Lancement local sans docker (trois terminaux, ou mettre les deux premiers en
arriere-plan) :

```
INSPECT_IA_AGENTS_LAB_PORT=8082 python3 -m recette.lab.mock_server
INSPECT_IA_AGENTS_LAB_URL=http://127.0.0.1:8082 INSPECT_IA_AGENTS_EVENT_STORE_PATH=/tmp/inspect_ia_agents/events.db INSPECT_IA_AGENTS_POLICIES_DIR=/tmp/inspect_ia_agents/policies INSPECT_IA_AGENTS_CONFIG_PATH=/tmp/inspect_ia_agents/config.json python3 -m recette.api
INSPECT_IA_AGENTS_E2E_API_URL=http://127.0.0.1:8090 python3 -m unittest tests.e2e.test_governed_flow -v
```

La suite e2e est opt-in : sans `INSPECT_IA_AGENTS_E2E_API_URL` tous ses tests sont
skippes, de sorte que la suite normale `make test` reste offline-green.

Smoke e2e agent+serveur (serveur mock gere, agent lie, campagne, capture de
l'access-log, replay deterministe) contre n'importe quelle API en cours :

```
python3 scripts/smoke_lab.py --api http://127.0.0.1:8090 --server-port 9111
```

Exit 0 = `SMOKE PASS` (les six etapes assertees). Re-executable de suite : le
script supprime ses propres entites de fixture (`smoke-*`) en amont et lit
l'access log depuis un curseur, de sorte que les runs precedents ne polluent
jamais les assertions.

Raccourci (demarre l'API si necessaire, puis lance le smoke du lab) :

```
./recette.sh smoke
make smoke
```

Smoke navigateur (boucle la chaine console -> API -> serveur mock -> replay dans
un vrai Chromium) : pilote l'UI reelle -- /servers Start->up, /campaigns
Lancer->completed, /servers Stop->down, recording visible, Replay->completed
(I4). Necessite une console en cours pointee sur l'API et le navigateur chromium
(`python3.11 -m playwright install chromium`) :

```
VITE_INSPECT_IA_AGENTS_API_URL=http://127.0.0.1:8090 npm --prefix console run dev -- --port 5173 --strictPort
python3.11 scripts/smoke_console.py --console http://localhost:5173 --api http://127.0.0.1:8090 --server-port 9131
```

L'origine de la console doit etre dans l'allow-list CORS de l'API
(`INSPECT_IA_AGENTS_CORS_ORIGINS`, par defaut `localhost:5173` + `127.0.0.1:5173`) ;
un port de console non-defaut necessite l'ajout de ce port, sinon le fetch du
navigateur est bloque. Utilise les bindings Python Playwright (python3.11 systeme
ici ; le venv [api] a fastapi mais pas playwright).

Persistance d'etat : le lab docker conserve l'event store, les policies et la
config d'agent sur le volume nomme `platform-data`. `make platform-down` le
conserve ; `docker compose down -v` l'efface (hash chain fraiche, inbox vide).

## Console

La console d'approbation (React/Vite) parle directement a l'API :

```
cd console
VITE_INSPECT_IA_AGENTS_API_URL=http://localhost:8090 npm run dev
```

Ou `make console` depuis la racine du repo (utilise les valeurs d'env par defaut
propres a la console ; positionner `VITE_INSPECT_IA_AGENTS_API_URL` dans
`console/.env.local` pour pointer sur l'API du lab).

## Registre des serveurs (mock_local / declared_url / real_saas)

Les serveurs sont des entites CRUD dans `config/inspect_ia_agents.config.json`
(section `servers`) et dans l'onglet Servers de la console. Trois modes :

- `mock_local` : la plateforme lance un vrai process HTTP local
  (`python -m recette.lab.mock_server`) sur le port configure. Start/stop depuis
  la console ou `POST /config/servers/{id}/start|stop`. `GET /health` le sonde.
  Chaque requete recue est ajoutee a `data/lab/{id}.access.jsonl` et restituee
  par `GET /config/servers/{id}/log?after=N` (le panneau de log de la console en
  fait le tail).
- `declared_url` : tout serveur externe parlant le format wire du lab
  (`POST /{target_system}/execute`, enveloppe `{"success","data"}`).
- `real_saas` : reserve ; l'execution echoue explicitement jusqu'a ce que le
  cablage du proxy realmode arrive.

Un agent portant `"server": "<id>"` execute via le proxy resolu depuis le
registre (I5). Une reference pendante fait echouer le run explicitement -- jamais
un fallback silencieux. Flux de demo verifie en live :

```bash
curl -X POST localhost:8090/config/servers -d '{"id":"okta-mock","system":"okta","mode":"mock_local","port":9122}' -H 'Content-Type: application/json'
curl -X POST localhost:8090/config/servers/okta-mock/start
curl -X POST localhost:8090/config/servers/okta-mock/test -H 'Content-Type: application/json' -d '{"action_type":"suspend_user","resource":"user:jdoe"}'
curl -X POST localhost:8090/runs -H 'Content-Type: application/json' -d '{"kind":"lane_b","params":{"agent_id":"okta-rogue","stub_script":[{"kind":"tool_call","tool_name":"suspend_user","tool_args":{"resource":"user:jdoe"}},{"kind":"final","text":"done"}]}}'
curl "localhost:8090/config/servers/okta-mock/log?after=0"
```

Note : les handlers de domaine du lab simulent l'ensemble des actions a risque du
catalogue ; les actions canoniques de type lecture (`read_repo`, `open_pr`) ne
sont pas simulees par le domaine github et renvoient 404 (le run echoue alors
explicitement, par conception).

### Les serveurs du lab (pilotes par la config, un par target system)

La section `servers` de la config livre un serveur `mock_local` par
`target_system` qu'un agent peut affronter. L'ensemble est PILOTE PAR LA CONFIG
et grossit avec le corpus (ne pas coder en dur un nombre) ; les ports vont de
9101+. Au 2026-06-17 il y en a 13 (12 `mock_local` + 1 `honeypot`) :

| Id du serveur | `system` | port |
|-----------|----------|------|
| `gh-mock` | github | 9101 |
| `okta-mock` | okta | 9102 |
| `finance-mock` | finance | 9103 |
| `support-desk-mock` | support_desk | 9104 |
| `slack-mock` | slack | 9105 |
| `cloud-mock` | cloud | 9106 |
| `hris-mock` | hris | 9107 |
| `legal-dms-mock` | legal_dms | 9108 |
| `product-cms-mock` | product_cms | 9109 |
| `knowledge-base-mock` | knowledge_base | 9110 |
| `mcp-mock` | mcp | 9111 |
| `gitlab-mock` | gitlab | 9112 |
| `shadow-db-sink` (honeypot) | - | 9113 |

Un agent qui vise une cible HTTP reelle la lie via son champ `server` (un agent
sans `server` retombe sur le LabForge in-process). Tous les serveurs executent le
MEME `recette.lab.mock_server` (il sert chaque domaine) ; le couple `system`/port
donne juste a chaque famille d'agents son propre endpoint. Un serveur non demarre
fait echouer un run lie avec `target server ... unreachable` (fail-safe, pas de
fallback, I5).

`./recette.sh platform up` demarre automatiquement chaque serveur `mock_local`
(une fois l'API saine, `cicd/platform.sh::_lab_servers_start` lit la liste
`servers` et POST `/config/servers/{id}/start` pour chacun -- un nouveau serveur
ne necessite donc aucune modif de script). Ils appartiennent au ServerManager de
l'API, donc `platform down` (arret de l'API) les demonte ; `platform status`
liste chacun avec son etat live up/down. Pour en (re)demarrer un a la main :

```bash
curl -X POST localhost:8090/config/servers/support-desk-mock/start
```

### Editer un domaine du lab : hot-reload (sans redemarrage)

Les serveurs mock_local sont longue-duree et chargent chaque domaine une fois.
Avec `INSPECT_IA_AGENTS_LAB_RELOAD` actif (R5 ; `platform up` le pose, OFF par
defaut pour le determinisme test/replay, I4), `mock_server` recharge un module
`recette/lab/domains/*.py` dont la source a change, de sorte qu'un handler edite
est servi SANS redemarrage. Seuls les serveurs DEMARRES avec le flag
s'auto-rechargent ; un serveur demarre avant lui continue de servir du code
perime (symptome : un corps fin `status: simulated` dans l'echange du cockpit)
jusqu'a son redemarrage.

### Page Agents : quatre onglets

La page Agents a quatre onglets :

- **Configuration** -- la table CRUD d'agents + formulaire ; le bouton *Run* par
  ligne declenche un run rapide du scenario stocke.
- **Corpus** -- navigateur en lecture seule des sujets ground-truth
  (`GET /subjects`, le composant `CorpusPage` reutilise ici ; la route autonome
  `/corpus` continue de deep-linker). Chaque sujet de test, toutes familles
  confondues (git_agent, maf_agent, maf_orchestration) avec sa categorie, son axe
  casse (violation_type) et son verdict attendu.
- **Cockpit -- lancer & debug** -- le lanceur detaille + flux live + log reseau.
- **Run log** -- le journal de frames live (start/step/result/end) du dernier run
  demarre depuis le bouton *Run* de la table Configuration.

#### Corpus vs Cockpit -- le corrige vs l'examen

La distinction la plus souvent confondue, enoncee comme un examen scolaire pour
que l'equipe recette ne les melange jamais :

- **Corpus = le corrige note.** Pour chaque agent, le verdict attendu (correct ou
  non, et pourquoi). Fige, en lecture seule -- on ne lance rien ici. C'est la
  verite terrain contre laquelle un outil externe est juge.
- **Cockpit = passer l'examen.** On lance un agent ; il agit pour de vrai contre
  le lab et produit sa copie (l'action-log : ce qu'il a *fait*).
- **La recette = corriger la copie contre le corrige.** Comparer ce que l'agent a
  fait (Cockpit) a la reponse attendue (Corpus). Concordance = pass.

Point cle : un agent n'est jamais juge sur ce qu'il *declare* (son manifest/code)
mais sur ce qu'il *fait* -- l'echange reseau dans le log. La declaration peut
mentir ; l'acte non. Chaque onglet porte un rappel d'une ligne en langage clair
de son role (`TAB_NOTES` dans `console/src/pages/agents/index.tsx`).

### Log reseau du Cockpit (traces de proxy)

Le Cockpit (un onglet de la page Agents) montre, sous le panneau de lancement,
les traces PROXY d'effets de bord (I5) du run actif -- les appels reseau reels
que l'agent a faits a son serveur lie (`action target/resource -> status`),
echecs inclus. C'est la vue de debug ; le log d'audit gouverne ne voit jamais les
runs lane_b. Elle est gatee par `INSPECT_IA_AGENTS_PROXY_DEBUG` (R5, off par
defaut ; `platform up` le pose on) : sinon `/proxy` et ce panneau n'enregistrent
rien (le panneau le dit au lieu d'afficher une boite vide silencieuse).

Cliquer une ligne de trace (ou la derniere auto-selectionnee) ouvre l'**echange
agent <-> serveur** dans le viewer Monaco : le `request_payload` que l'agent a
envoye et le `response` serveur qu'il a recu en retour. Un select **Afficher** le
restreint a la requete agent seule, la reponse serveur seule, ou les deux. Deux
autres selects (**Agent** / **Serveur**, par defaut **Tous**) filtrent les lignes
affichees aux valeurs presentes dans le run. Seuls les agents lies a un `server`
(proxy HTTP) tracent ; un agent sans `server` tourne en LabForge in-process et ne
produit aucun appel reseau.

La trace porte le corps `response` du serveur (`ProxyTrace.response`, depuis
`ExecutionResult.response`) ; un corps fin `status: simulated` signifie
generalement que le serveur mock_local sert du code de domaine perime -- voir la
note hot-reload ci-dessus.

## Providers IA

Backends de `recette/llm.py` : anthropic, openai, gemini, groq, mistral,
deepseek, xai, plus `openai_compat` (tout vendor OpenAI-wire via `base_url` --
Ollama, OpenRouter, vLLM...). Cles via env uniquement : `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`,
`DEEPSEEK_API_KEY`, `XAI_API_KEY`. `POST /config/ai-backends/{id}/test` fait un
appel live minimal et renvoie `{ok, latency_ms, kind|error}` -- cable au bouton
Test du panneau AI Backends de la console.

## Scoring de verdict (recette de l'outil externe)

Les agents peuvent porter un bloc `ground_truth` (`detectable`,
`expected_identity`, 4 `dimensions`, `expected_verdict`). L'outil externe de
discovery/identification pousse ses resultats :

```bash
curl -X POST localhost:8090/verdicts -H 'Content-Type: application/json' -d '{"tool":"discovery-v1","results":[{"agent_id":"demo-gh-bot","detected":true,"verdict":"correct","identity":"bot@acme","dimensions":{"identity":true,"capabilities":true,"policy":true,"behavior":true}}]}'
curl localhost:8090/verdicts/scorecard
```

Chaque resultat est juge contre le ground truth de l'agent (PASS/FAIL/SKIP +
detail par check + ids d'evenements de preuve depuis le log d'audit).
`GET /verdicts/scorecard` agrege le taux de detection, l'accuracy par dimension,
les faux positifs/negatifs. L'onglet Verdicts de la console rend le banner, la
table par agent (preuve depliable) et accepte un upload JSON comme alternative au
push HTTP.

### Soumettre un run termine comme verdict (boucle interne)

Au-dela de l'outil externe, un run lance dans la console peut etre pousse sur le
meme board sans aucun outil externe. `POST /runs/{id}/submit-verdict` juge
l'action-log reel du run (`judge_run`, pur/deterministe I4), le forme en entree de
resultat `/verdicts` (`detected:true`, `identity=principal`, le verdict du run +
4 dimensions) et le stocke via le chemin de juge partage sous le nom d'outil
`run:<id>` :

```bash
RUN=$(curl -sX POST localhost:8090/runs -H 'Content-Type: application/json' -d '{"kind":"lane_b","params":{"agent_id":"demo-gh-bot","stub_script":[{"kind":"tool_call","tool_name":"read_repo","tool_args":{"resource":"acme/x"}},{"kind":"final","text":"done"}]}}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
curl -sX POST localhost:8090/runs/$RUN/submit-verdict
curl -s localhost:8090/verdicts
```

Il est juge contre le meme `ground_truth`, donc un agent sans ground truth donne
SKIP (jamais un PASS vide). Dans la console c'est le bouton "Soumettre aux
Verdicts" (oeil de l'agent -> onglet Verdict) et l'auto-submit du dashboard en fin
de run -- bouclant la boucle launch -> act -> judge -> Verdicts.
`GET /verdicts/history` liste chaque soumission (tool/run, seq, PASS/FAIL/SKIP),
affichee dans le panneau "Historique des soumissions" de la console.

## Surfaces d'observabilite pour l'outil externe

1. Trafic HTTP reel contre les serveurs mock_local (sniff/scan des ports).
2. `GET /audit/events` (filtrable) et `GET /audit/export.jsonl` (flux NDJSON
   complet du log d'evenements append-only, hash-chaine).
3. L'API REST elle-meme (agents, servers, runs, campaigns, verdicts).
