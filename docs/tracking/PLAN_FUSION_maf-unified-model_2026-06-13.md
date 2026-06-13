# Plan : Fusion du modele git + MAF en un modele unifie
Date : 2026-06-13
Status : TERMINE (P1-P4 livres + gates verts ; P5 contrat API livre, frontend separe)
Invariants concernes : I1 (event store immuable, non touche), I3 (identite), I4 (replay deterministe), I6 (approbation)

## Objectif
Fusionner le modele d'agent git (corpus/agents, manifest enum github|gitlab) et le
modele standard MAF (agent-spec) en UN modele unifie. Adapter le backend (judge,
harness, scorecard, report, API) et l'UX (console) pour gerer les deux familles via
un seul chemin.

## Constat de cout (mesure 2026-06-13)
- platform/ (catalog, policy, eventstore, proxy, events) est DEJA string-based : aucun
  enum git-only dans le chemin de decision. 13 domaines en data. -> pas de migration
  de schema event-store (I1) requise.
- Git-specifique reel : agent-manifest.schema.json (enums), events.ActionType/TargetSystem,
  ReferenceIdentificationAdapter (resource globs, ESCALATE_ACTIONS, principal).
- 10 agents git corpus + 5 sujets MAF a faire converger.

## Phases
- [x] P1 Schema unifie : agent-manifest.schema.json superset (identite git OU maf via
      anyOf ; capability oneOf git|invoke_tool|handoff ; target_systems string libre).
      10 agents git intacts + 5 sujets MAF migres. agent-spec.schema.json supprime.
- [x] P2 Judge unifie : recette/judge.py judge_subject dispatch git/maf sur le kind.
      maf_harness route via judge_subject. Contrat IdentificationResult identique.
- [x] P3 Report unifie : report.FullReport agrege identification + maf + discovery ;
      recette report montre les 2 familles en un verdict.
- [x] P4 Backend interfaces : recette/api/routers/subjects.py expose GET /subjects
      (corpus unifie 15 sujets) + GET /subjects/scorecard (verdict agrege). Verifie live.
- [~] P5 UX : contrat API livre + verifie (TestClient 3/3). La console Vite est un repo
      frontend separe (absent ici) -> les .tsx se branchent sur /subjects quand dispo.

## Gate par phase
build (python import) + ruff + mypy + `python3 -m unittest discover -s tests` (630 baseline)
+ `recette validate` + `recette maf`/`run`. Zero regression toleree.

## Decisions prises
- Fusion validee par l'utilisateur malgre le cout (2 confirmations).
- Pas de migration event-store : le coeur platform est deja string-based (mesure).

## Ecarts et replanification
- (a remplir au fil des phases)

## Resultat
- (a remplir)
