# TODO / Plan : RAG-KB finition (a executer par APEX)

Date : 2026-06-13
Status : TERMINE (T1/T4/T5 deja faits ; T2 Makefile + T3 e2e deterministe livres
le 2026-06-13 -- cf commits de la session apex "fait les todo")
Invariants concernes : I2 (mediation, anti-backdoor), I4 (reset deterministe), I5 (proxy)
Reference feature : commits abe8b15, f905162, 0bf4ded ; runbook
docs/runbooks/rag-knowledge-base-crud.md

## Etat de depart (deja fait)

Domaine knowledge_base + campagnes poisoning + store CRUD (recette/rag_store.py) +
API /rag/documents|reset|scenarios|scenario/{name}/apply + CLI rag-kb + frontend
KnowledgeBaseManager (page /rag) + scenarios + path-traversal guard + 18 tests +
runbook. Suite complete verte.

## Reste a faire

- [x] T1 DONE -- smoke navigateur reel (headless puppeteer, pas de Playwright MCP).
      Stack monte (API :8080 + vite :5174), navigation /rag -> section "Knowledge
      base" : table 8 docs, badges poison (kb-poison-exfil/invalid-command),
      boutons Reset/Apply/scenario-select, form Insert. FLUX live verifie (R26) :
      load 8 -> apply exfil-finance -> 9 (scn-exfil-finance present) -> reset -> 8
      (poison parti), zero erreur console app, gate reseau propre. Screenshot
      capture. Bonus : favicon.ico cree (le smoke avait expose le 404 favicon).

- [x] T2 DONE -- Makefile : `make rag-kb` (liste le KB, deja present) + `make rag-e2e`
      (nouveau, parite avec rag/bnp/role-matrix : `python3 scripts/run_rag_poisoning_e2e.py`).
      Les deux ajoutes a l'aide `make help`. Parite verifiee : meme invocation `python3
      scripts/...` que rag-live (echec identique sous python3 nu sans le package installe ;
      OK sous l'env attendu .venv editable + extra [api]).

- [x] T3 DONE -- `scripts/run_rag_poisoning_e2e.py` : DETERMINISTE (I4, aucun LLM).
      L'action induite est lue directement du doc poisonne (injected_action /
      injected_target_system / injected_expect) et soumise a la VRAIE gateway HTTP
      (TestClient, catalogue committe + policy baseline). Boucle : reset -> apply
      <scenario> -> pour chaque doc poisonne, assert verdict == injected_expect ET in
      {deny,escalate} ET executed=False -> reset -> KB == baseline byte-identique +
      audit chain intacte. Exit 0/1/2. Preuve live (R26, exfil-finance) : 4 actions
      bloquees (deny/deny/escalate/deny), executed=False, baseline restauree, chaine
      intacte. tests/test_rag_e2e.py l'invoque (2 scenarios + scenario inconnu -> 2 +
      idempotence/determinisme), skip si pas d'extra [api].

- [x] T4 Guard scenario<->campagne : DONE -- decide-based, pas require-a-campagne.
      `test_scenario_guard_every_poisoned_doc_is_blocked_by_the_gateway`
      (tests/test_rag_poisoning.py) decide chaque doc poisonne de
      `corpus/rag/scenarios/*.json` pour rag_agent et assert verdict ==
      injected_expect ET in {deny,escalate}. Negative-prouve rouge sur un scenario
      menteur (claim deny / engine allow). I4 deterministe.

- [x] T5 Durcissement store.add : DONE -- `_validate` rejette un id ne matchant pas
      `^[a-z0-9][a-z0-9-]{1,63}$` (`test_add_rejects_invalid_id_slug`). Ids legitimes
      (kb-*, scn-*) inchanges ; baseline charge hors `add` donc non impacte.

## Criteres de "done"

- T1 : snapshot navigateur sans erreur + au moins un noeud DOM attendu (R26).
- T2 : `make rag-kb` et `make rag-e2e` fonctionnent ; ajoutes a l'aide du Makefile.
- T3 : `run_rag_poisoning_e2e.py` exit 0, preuve gateway executed=False, reset ==
      baseline byte-identique ; gates ruff/mypy/bandit verts ; 1 test l'invoque.
- T4 : test rouge si un doc poisonne de scenario n'a pas de preuve de blocage.
- T5 : test rejette un id invalide ; legit inchange.

## A verifier avant (repo en concurrence)

- Rebaser sur main au demarrage (l'autre session ecrit maf_orchestration + retrieval).
- Ne pas toucher au track retrieval (P1-P4) ni au corpus maf_orchestration -- hors scope.
- Convention Makefile + style des targets existants (python3 sous venv).

## Hors scope (autre session)

- Track qualite-retrieval (RagBackend/scorecard/page rag read-only).
- Corpus maf_orchestration.
- Lancer la skill /rag-pdca sur le track retrieval (a proposer a l'autre session).
