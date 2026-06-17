# Design -- Mise en avant du concept "Control plane" (console + doc)

Date : 2026-06-17
Status : APPROVED (operateur : "tout" + "hybride" + "utilise apex swarm")

## Objectif

Rendre la notion **Control plane** (le coeur gouvernance : decision allow/deny/
escalate, risk, approval, deny-by-default, invariants I2/I6) visible et
"interessante" dans la console inspect_ia_agents -- aujourd'hui les pages
gouvernance (Catalog, Approvals, Audit, Proxy) existent mais aucune vue ne
montre le CONCEPT ni le flux de decision agrege.

## Perimetre (valide : "tout", donnees "hybride")

### 1. Backend -- `GET /control/summary`
Agrege le log d'audit append-only (I1, lecture seule) en un resume de
gouvernance, deterministe (pas d'horloge dans le calcul) :
```
{
  "total": int,                       # evenements consideres
  "verdicts": {"allow": n, "deny": n, "escalate": n},
  "approvals": {"none": n, "pending": n, "approved": n, "denied": n, "timeout": n},
  "executed": n, "denied_execution": n,
  "deny_by_default": true             # posture (constante du Control plane)
}
```
- Source : l'`EventStore` (events `ACTION_*`/`APPROVAL_*`), via le meme acces
  que `/audit/events`. Compte par `policy_decision.verdict` + `approval_state`.
- Read-only (I1), pur, unittest stdlib (fixture event log -> resume stable).
- Router `recette/api/routers/control.py`, enregistre dans `app.py`.

### 2. Console -- page `/control` (hybride)
- **Haut (pedagogique, toujours visible)** : diagramme mermaid des 3 plans
  (Control / Data / Audit) + le cycle de decision (Gateway -> Policy -> Risk ->
  Approval -> execute|block), reutilise le composant `Mermaid` existant.
- **Bas (preuve live)** : cartes de stats depuis `GET /control/summary` --
  verdicts (allow/deny/escalate), approbations (pending/approved/denied/timeout),
  posture deny-by-default, total. Service unwrap (R16), fixture reelle +
  render-and-assert, etat vide gere.
- Fichier `console/src/pages/control/index.tsx` (+ css), sous plafond .tsx 400.

### 3. Aide
- Topic `control` dans `helpTopics.tsx` (+ `HelpTopicKey`) : explique le Control
  plane, le cycle de decision, deny-by-default, I2 (mediation) / I6 (blocage
  approbation), avec le meme diagramme mermaid. Bouton `? Aide` sur `/control`.

### 4. Nav + reframing
- Separateur nav `Gouvernance (mock)` -> `Control plane`.
- `/control` ajoute EN TETE de ce groupe (avant Catalog).
- (Note concept : portee par l'aide modale, pas de bandeau intrusif par page.)

## Gates (done)
- Python : unittest `/control/summary` (resume stable sur fixture event log) ;
  ruff + mypy clean.
- Console : `tsc` clean ; vitest render-assert (R16) ; full suite vert ; vite build.
- Live : etendre `scripts/smoke_console.py` -- naviguer `/control`, asserter le
  diagramme + au moins une carte de stat, ouvrir l'aide.

## YAGNI (exclu)
- Pas de graphes temporels / time-series (juste des compteurs courants).
- Pas de filtres avances (l'audit a deja sa page filtrable).
- Pas de rename de l'identifiant `railgun-recette` (hors scope, decide avant).

## Invariants
- I1 : lecture seule sur le log (jamais d'ecriture). I2/I6 : le concept MONTRE
  la mediation + le blocage approbation, ne les modifie pas. Determinisme : le
  resume est une fonction pure du log (pas d'horloge dans l'agregation).
