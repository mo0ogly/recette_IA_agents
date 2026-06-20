# RETEX -- Page "Discovery x Echange" (overlay verdict discovery sur l'echange reel)

Date : 2026-06-20
Auteur : session Claude (worktree partage)
Commits : `4bfc211` (feature), `8947aae` (smoke) -- sur `origin/main`.

## Objectif

Combler le chainon manquant de la lisibilite (legibility-first, CLAUDE.md) : une
page console qui superpose, cote a cote, l'ECHANGE REEL agent<->serveur (proxy
hook + wire) et CE QUE LE DISCOVERY A VU (agent detecte/ghost, action identifiee
ou flux wire-only non rattachable). Source oracle deterministe par defaut, eBPF
si broker up. Granularite per-agent + per-echange.

## Livre

| Couche | Fichiers |
|--------|----------|
| Backend pur (I4) | `recette/surface/exchange.py` (`build_exchange_report`) |
| Endpoint | `GET /proxy/discovery-exchange` dans `recette/api/routers/proxy.py` (+ refactor DRY `_build_run_allowlist`) |
| Types/Client | `console/src/types/platform.ts`, `console/src/api/client.ts` (`getDiscoveryExchange`) |
| Page | `console/src/pages/discovery-exchange/{index.tsx,exchangeModel.ts,discovery-exchange.css}` + route/nav `App.tsx` |
| Tests | `tests/test_surface_exchange.py`, `tests/test_api_discovery_exchange.py`, vitest `index.test.tsx` + 2 fixtures |
| Smoke | `_verify_discovery_exchange` dans `scripts/smoke_console.py` + `docs/screenshots/sim/discovery-exchange.png` |

## Preuves (gates)

- Python suite complete : 1584 OK. ruff/format/mypy clean. `test_surface_exchange` 6/6 (dont replay byte-stable I4), `test_api_discovery_exchange` 3/3.
- `tsc --noEmit` clean ; vitest discovery-exchange 3/3 ; `console-build` OK ; `console-test` 432 OK.
- Live R14 : flux navigateur pilote contre la plateforme up -> table rendue, badge `dx-ghost-count` "1 echange(s) ghost", ligne `exchange-outcome=ghost`, screenshot. API live : `ghost_exchanges=1`.

## Ce qui a bien marche

- **Tout reutilise, rien reinvente.** Le verdict = composition de briques
  existantes : `detect_agent` + `score_detections` (oracle surface) +
  `reconcile_strict`/`wire_flow_side_effect_hash` (jointure ghost). Le endpoint
  reutilise la construction d'allowlist de `_reconcile_report`. Zero duplication
  de logique de decision.
- **Exploration d'abord (Explore agent) -> design solide.** La carte du code
  (surface model, reconcile, proxy console, receipts pattern) a evite des
  fausses pistes et donne le pattern R16 a copier (receipts page).
- **Fixtures R16 produites par le vrai serializer backend** (`to_dict()` via
  `python -c`), pas inventees a la main -> contrat reellement valide.

## Ce qui a coince (lecons)

### L1 -- Correction de conception en cours de route : ghost AGENT vs ghost ECHANGE
Le plan initial voulait `detect_agent(agent, traces, wire)` par agent. Faux :
`WireFlow` n'a **pas** d'`agent_id` (c'est ce qui rend un ghost detectable). Passer
tous les flux wire a chaque agent aurait faussement claime "vu sur le wire" pour
chacun. Et un ghost AGENT n'est PAS reconstructible depuis les buffers live (rien
a rattacher). Fix : detection per-agent = HOOK-attribuable seulement (`wire=[]`),
et le signal ghost vit au niveau ECHANGE (`ghost_exchanges` = flux wire-only via
`reconcile_strict`). Le ghost AGENT n'apparait que par la source eBPF.
**Lecon** : verifier la presence d'un identifiant d'attribution AVANT de modeliser
une jointure par entite. L'absence d'`agent_id` sur le wire est une PROPRIETE du
modele (ghost = wire-vu/hook-aveugle), pas un manque a contourner.

### L2 -- Worktree partage = course sur les fichiers partages (R21)
`proxy.py`, `client.ts`, `platform.ts` ont ete committes par une session
concurrente AVEC mes edits dedans -> HEAD s'est retrouve casse (proxy.py importait
`surface.exchange` non encore committe). Mon commit a repare. Puis `smoke_console.py`
a ete edite en concurrence pendant que je le committais (race ×2 : "File modified
since read"), l'autre session ajoutant `# nosec B310` + son `_verify_receipts(api)`.
**Lecon** : sur un fichier partage activement edite, (a) re-Read avant chaque Edit,
(b) valider l'INDEX (`git show :file`) pas seulement le working tree avant commit,
(c) accepter d'embarquer les hunks verts de l'autre session (no-loss > purete du
commit), (d) ne jamais clobber. Vrai fix durable = un worktree par session.

### L3 -- Le pre-commit bandit scanne tout le fichier stage, pas juste ton diff
Bandit `B310` (`urlopen`) sur une ligne PRE-EXISTANTE de `smoke_console.py` a
bloque mon commit parce que je stageais le fichier. **Lecon** : un hook de
securite peut bloquer sur du code voisin non-tien ; un `# nosec` justifie
(URLs localhost internes, jamais file://) est la bonne reponse, pas le bypass
`PRECOMMIT_SKIP`. Ici l'autre session a pose le nosec en parallele.

### L4 -- Le full smoke ne tourne pas sur une plateforme deja up
`./recette.sh smoke` a abort a `_start_server` (port 9111 mcp-mock deja pris). Le
smoke seed son propre serveur et entre en collision avec la plateforme en cours.
Contournement R14 : piloter UNIQUEMENT mon step live en important la fonction
versionnee (pas de script /tmp duplique) -> preuve live obtenue sans casser la
plateforme partagee.
**Lecon** : la preuve live d'UN flux peut reutiliser la fonction du smoke
versionne sans lancer tout le harnais ; l'assertion durable reste dans le smoke.

## Suites possibles

- Quick win : filtre `run_id` dans l'UI (deja porte par l'endpoint) pour scoper
  l'overlay a un run depuis le selecteur, comme `AppTracesPanel`.
- Notable : brancher reellement la colonne eBPF (capture broker) pour afficher un
  ghost AGENT cote source eBPF (aujourd'hui seul le scorecard eBPF est montre).
- Refactor : entree PageHelp `discovery-exchange` (droppee pour ne pas toucher
  `helpTopics.tsx` en cours d'edition concurrente) a ajouter quand le fichier est
  stable.
