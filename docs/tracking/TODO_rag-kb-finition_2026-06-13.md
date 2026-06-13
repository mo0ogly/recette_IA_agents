# TODO / Plan : RAG-KB finition (a executer par APEX)

Date : 2026-06-13
Status : TODO (la feature RAG-KB CRUD est livree, securisee, testee, documentee --
ceci est le reliquat de finition/polish)
Invariants concernes : I2 (mediation, anti-backdoor), I4 (reset deterministe), I5 (proxy)
Reference feature : commits abe8b15, f905162, 0bf4ded ; runbook
docs/runbooks/rag-knowledge-base-crud.md

## Etat de depart (deja fait)

Domaine knowledge_base + campagnes poisoning + store CRUD (recette/rag_store.py) +
API /rag/documents|reset|scenarios|scenario/{name}/apply + CLI rag-kb + frontend
KnowledgeBaseManager (page /rag) + scenarios + path-traversal guard + 18 tests +
runbook. Suite complete verte.

## Reste a faire

- [ ] T1 (BLOQUANT) Verif visuelle frontend -- jamais smoke-teste en navigateur
      (R26 : livre, non verifie). Avec Playwright MCP : naviguer localhost:5173 ->
      onglet RAG -> section "Knowledge base", verifier zero Component Error, table
      des docs visible, badge poison, boutons Reset / Apply scenario / Insert.
      Capture ARIA snapshot. Si pas de Playwright : laisser a l'utilisateur.

- [ ] T2 Wiring Makefile : `make rag-kb` (liste le KB), `make rag-e2e` (cf T3).
      Cible : parite avec les targets existants (rag, bnp, role-matrix, coverage-guard).

- [ ] T3 Demo e2e en 1 commande : `scripts/run_rag_poisoning_e2e.py` qui enchaine
      reset -> apply <scenario> -> run agent (ou run_role_matrix --dir campaigns/rag)
      -> assert gateway deny/escalate, executed=False -> reset -> KB == baseline.
      Deterministe (I4) ; sert de preuve vivante de la boucle de recette.

- [ ] T4 Guard scenario<->campagne : etendre la KB-guard pour que chaque doc
      poisonne d'un `corpus/rag/scenarios/*.json` ait soit une campagne, soit un
      assert explicite que son `injected_action`/`injected_expect` est bloque par la
      gateway (decide-based, comme test_rag_poisoning). Empeche un scenario poisonne
      sans preuve de blocage.

- [ ] T5 Durcissement store.add : valider l'id d'un document insere contre le meme
      slug `^[a-z0-9][a-z0-9-]{1,63}$` que le nom de scenario (defense en profondeur,
      coherence avec le schema). Mineur : l'id ne touche aucun chemin fichier.

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
