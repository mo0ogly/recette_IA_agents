# Plan : RAG-KB finition T4+T5 + doc mermaid + coherence

Date : 2026-06-13
Status : TERMINE
Invariants concernes : I2 (mediation, anti-backdoor), I4 (decide deterministe), I5 (proxy)
Reference : docs/tracking/TODO_rag-kb-finition_2026-06-13.md (T4, T5) ; runbook
docs/runbooks/rag-knowledge-base-crud.md

## Objectif

Fermer le reliquat RAG-KB : T4 (guard scenario poisonne <-> preuve de blocage
decide-based), T5 (durcir l'id d'un doc insere au slug), puis doc mermaid pour
l'equipe de recette + verifier la coherence de la feature avec rules / campagnes /
maf (autre session).

## Etapes

- [ ] S1 (T4) Guard decide-based sur corpus/rag/scenarios/*.json : chaque doc
      poisonne decide a son injected_expect (rag_agent) et expect in {deny,escalate}.
      Test rouge si un scenario poisonne n'a pas de preuve de blocage. (tests/)
- [ ] S2 (T5) Durcir KnowledgeBaseStore._validate : id contre slug
      ^[a-z0-9][a-z0-9-]{1,63}$ (defense en profondeur, coherence schema). Test
      rejette un id invalide ; ids legitimes (kb-*, scn-*) inchanges.
- [ ] S3 Doc mermaid : docs/runbooks/rag-knowledge-base-crud.md enrichi de
      diagrammes (flux CRUD operateur hors chemin agent, sequence poisoning ->
      gateway deny, frontiere I2) pour l'equipe de recette.
- [ ] S4 Coherence : verifier la feature RAG-KB vs rules (.claude/rules), campagnes
      (campaigns/rag), et l'integration maf (autre session) sans la casser.
- [ ] S5 RECETTE : python-recette/gates + suite complete + system-recette verts.

## Decisions prises

- T4 decide-based plutot que require-a-campaign -> prouve le blocage directement,
  pas de couplage scenario<->campagne, I4 deterministe.
- Scope strict RAG : ne pas toucher maf_orchestration (autre session, fichiers A
  non commit) -- R28 flag-not-sweep.

## Ecarts et replanification

(a remplir)

## Resultat

(a remplir)
