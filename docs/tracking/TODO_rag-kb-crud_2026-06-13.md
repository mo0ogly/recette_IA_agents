# TODO / Plan : RAG knowledge-base CRUD + poison scenarios + reset

Date : 2026-06-13
Status : TERMINE -- ce plan a ete entierement implemente (store rag_store.py, scenarios, API /rag/documents|reset|scenarios, CLI rag-kb, frontend KnowledgeBaseManager, tests). Suivi/polish: voir TODO_rag-kb-finition (T1-T5, tous faits). Plan conserve pour tracabilite.
Invariants concernes : I2 (mediation), I4 (replay deterministe), I5 (proxy side-effects)
Auteur du plan : session recette (apex, livrable = ce document)

## Objectif

Donner un lifecycle operateur au RAG de recette : voir le contenu, inserer/supprimer
des documents, appliquer un scenario de poison nomme, et RESET a une baseline propre.
Aujourd'hui le contenu KB est un seul fichier statique committe
`corpus/rag/knowledge_base.json`, charge en lecture seule par le lab handler ; aucune
API/CLI pour le manipuler. Cf. constat 2026-06-13.

Boucle de recette visee :
```
reset -> apply <scenario> (injecte docs poisonnes) -> run agent -> gateway BLOQUE -> reset
```

## Decision d'architecture (retenue)

Store KB **runtime in-memory, baseline-backed** :
- baseline = `corpus/rag/knowledge_base.json` (committe, source de verite).
- `reset` = recharge la baseline -> etat propre deterministe (I4), trivial, pas d'IO destructive.
- CRUD muté en memoire pour la duree d'une session de recette ; rien n'ecrase le fichier baseline.

Alternative rejetee : store **persistant** (fichier mutable / SQLite). Rejet : complexifie le
reset, casse le determinisme (I4) entre runs, et un fichier mutable partage rejoue mal. La
persistance n'apporte rien a une recette dont le but est justement reset+rejeu.

## Garde-fou gouvernance (NON NEGOCIABLE)

Le CRUD operateur sert a PREPARER la recette, HORS chemin agent. Ce n'est PAS une action
d'agent. L'agent, lui, reste soumis a la gateway : `ingest_document` = escalate,
`purge_index` = deny (catalogue knowledge_base). On ne cree AUCUN chemin qui laisse un
agent muter le KB sans mediation (sinon viol I2). Le CRUD est un outil de banc de test,
documente comme tel, expose sur des routes operateur distinctes du `/actions/execute`.

## Etapes

### Backend (Python)
- [x] S1 `recette/rag_store.py` : `KnowledgeBaseStore` baseline-backed.
      - `load_baseline()`, `list()`, `add(doc)`, `delete(doc_id)`, `reset()`.
      - `apply_scenario(name)` : charge `corpus/rag/scenarios/{name}.json` et injecte ses docs.
      - Validation : chaque doc {id, title, content, poisoned, tags} ; un doc poisonne porte
        `injected_action`/`injected_target_system`/`injected_expect`/`threat` (meme schema que
        knowledge_base.json). Refus d'un id duplique. Deterministe (pas d'horloge/random, I4).
- [x] S2 Schema `corpus/rag/scenarios/scenario.schema.json` + 2-3 scenarios nommes
      (`exfil-finance.json`, `invalid-command-ops.json`, `mixed.json`) reutilisant les docs
      poisonnes existants + nouveaux. jsonschema-valides.
- [x] S3 Brancher le lab handler `recette/lab/domains/knowledge_base.py` sur le store
      (au lieu de lire le fichier en dur) pour que `query_knowledge_base` reflete l'etat
      courant (baseline + scenario applique). Garder le fallback baseline si store non initialise.
- [x] S4 API `recette/api/routers/rag.py` (etend l'existant `GET /rag/scorecard`) :
      - `GET /rag/documents` -> liste (id, title, poisoned, tags).
      - `POST /rag/documents` -> insere un doc (operateur).
      - `DELETE /rag/documents/{id}` -> retire.
      - `POST /rag/reset` -> recharge baseline.
      - `GET /rag/scenarios` -> liste les scenarios nommes.
      - `POST /rag/scenario/{name}/apply` -> applique un scenario.
      - Enveloppe reponse coherente avec le reste (`{success, data}` si c'est la convention
        backend en place -- a verifier sur les routers existants AVANT d'ecrire).
- [x] S5 CLI parite `python -m recette rag-kb {list|add|del|reset|apply <scenario>}`
      (sous-commande dans `recette/__main__.py`, meme style que `rag`).

### Frontend (React/TS -- COHERENT avec l'existant)
Cible : `console/src/pages/rag/` existe deja (scorecard read-only, page du mainteneur P4).
Pattern confirme : pages en `console/src/pages/<name>/{index.tsx,.css,index.test.tsx,__fixtures__/}`,
client via `request<T>(path, opts)` dans `console/src/api/client.ts` (PAS fetchWithConfig --
c'est le helper `request<T>` qui est le standard ici), CRUD de reference = page `campaigns`
(list/create/delete deja implementes : `listCampaigns`/`createCampaign`/`deleteCampaign`).
- [x] S6 Etendre `console/src/api/client.ts` : `listKbDocuments`, `addKbDocument`,
      `deleteKbDocument`, `resetKb`, `listRagScenarios`, `applyRagScenario` -- mirror exact
      des signatures `listCampaigns`/`createCampaign`/`deleteCampaign` (memes types, meme
      unwrap d'enveloppe). Types dans `console/src/types/platform.ts`.
- [x] S7 Sous-onglet "Knowledge base" dans la page `rag` (ou nouvel onglet a cote du
      scorecard) : tableau des docs (colonnes id/title/tags + **badge poisoned** via Chip
      semantique `color="warning"`, borderRadius:1), bouton **Reset**, **selecteur de
      scenario** + bouton Apply, formulaire **Insert document** (modale, comme la creation de
      campagne). Style MUI identique aux pages `campaigns`/`flux`/`rag`. Loading =
      CircularProgress, erreur = `<Alert severity="error">`, vide = empty state -- memes
      composants que les autres pages (coherence transversale).
- [x] S8 R16 Contract Gate : fixture `__fixtures__/kb-documents.fixture.json` (payload reel
      capture via curl sur `GET /rag/documents`), `index.test.tsx` render-and-assert (au moins
      le tableau + un badge poisoned), service unwrap `.data`. HelpButton + contenu d'aide
      (table ui_help_content si c'est le mecanisme retenu cote console).

### Tests + garde-fous
- [x] S9 `tests/test_rag_store.py` : CRUD + reset deterministe (apply scenario puis reset ->
      etat == baseline byte-identique), apply_scenario injecte bien les docs poisonnes,
      refus d'id duplique, validation schema.
- [x] S10 `tests/test_rag_scenarios.py` : chaque scenario `corpus/rag/scenarios/*.json` est
      schema-valide ET chaque doc poisonne d'un scenario a une campagne correspondante
      (extension de la KB-guard de `tests/test_rag_poisoning.py`).
- [x] S11 Garde-fou anti-backdoor : un test asserte qu'il n'existe AUCUNE route permettant a
      un agent (chemin `/actions/execute`) de muter le KB sans verdict -- le CRUD est sur des
      routes operateur distinctes (I2). Le `test_coverage_guard` reste vert (12 domaines).
- [x] S12 Boucle e2e (script ou test) : reset -> apply exfil-finance -> run agent (ou
      run_role_matrix --dir campaigns/rag) -> verifier gateway deny/escalate, executed=False
      -> reset -> KB == baseline.

## Criteres de "done"

- Backend : `make gates` (ruff+mypy+bandit) vert sur les nouveaux .py ; `make test` vert ;
  CLI `python -m recette rag-kb list|reset|apply` fonctionne ; API repond aux 6 routes.
- Frontend : `vite build` 0 erreur TS ; R16 fixture+render-and-assert vert ; page importee
  par un parent (pas d'orphelin) ; Playwright smoke 0 Component Error ; coherence MUI avec
  campaigns/flux/rag.
- Gouvernance : `test_coverage_guard` + KB-guard verts ; test anti-backdoor vert ; reset
  deterministe (I4) prouve ; aucun chemin agent -> mutation KB sans gateway (I2).
- Boucle e2e reset->apply->run->reset demontree avec preuve (log gateway executed=False).

## A verifier AVANT d'implementer (le repo bouge)

1. Convention d'enveloppe reelle des routers existants (`{success,data}` ou JSON brut) --
   lire `recette/api/routers/rag.py` + un router CRUD existant a l'instant T.
2. Etat du menu/page console `rag` du mainteneur (peut avoir evolue au-dela de P4).
3. Mecanisme d'aide console (ui_help_content table ou autre) tel qu'en place.
4. Que `corpus/rag/knowledge_base.json` est toujours la baseline (le mainteneur a pu bouger).

## Risques

- Concurrence mainteneur : rebaser sur main au demarrage de l'implementation ; ne pas
  toucher aux fichiers en cours d'edition par le mainteneur (console WIP).
- Tentation backdoor : exposer ingest CRUD operateur ET garder ingest_document agent
  escalate -- bien separer les deux chemins, sinon viol I2.
- Determinisme : un store mutable mal reset casse I4 -- d'ou baseline-backed + test S9.
