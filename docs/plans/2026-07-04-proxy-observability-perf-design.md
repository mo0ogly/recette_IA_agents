# Design -- Proxy observability : performance backend + UX console

Date : 2026-07-04
Statut : VALIDE (brainstorm operateur, approche A retenue)
Invariants concernes : I1 (le buffer de debug n'est PAS l'audit store), I4 (ordre seq,
pas d'horloge murale), I5 (l'observabilite ne bloque jamais l'execution proxy).

## Probleme (goulots verifies dans le code)

| # | Goulot | Preuve |
|---|--------|--------|
| 1 | `snapshot()` copie le ring entier a CHAQUE requete | `recette/platform/proxy/tracing.py:164-166` |
| 2 | Pas de pagination/filtre serveur (`run_id` filtre APRES la copie) | `recette/api/routers/proxy.py:84-92` |
| 3 | `reconcile_strict` re-parse le JSON et re-hashe tous les flows a chaque appel | `recette/platform/proxy/reconcile.py:131-165` |
| 4 | Rendu liste sans virtualisation (512 noeuds DOM hors ecran) | `console/src/pages/proxy/AppTracesPanel.tsx:322` |
| 5 | SessionsPanel tire 4 requetes paralleles toutes les 2 s, chacune = buffer entier | `console/src/pages/proxy/SessionsPanel.tsx:103-147` |
| 6 | Filtrage cote client seulement (l'API n'accepte que `run_id` + `tail`) | `console/src/pages/proxy/AppTracesPanel.tsx:171` |
| 7 | Ring fixe 512 : une longue campagne perd ses traces anciennes ; restart = tout perdu | `recette/platform/proxy/tracing.py` (capacity=512) |

Objectifs operateur (les 4 retenus) : reactivite UI (live feel), charge backend/reseau,
scale sessions longues, ergonomie du toolkit.

## Decisions de cadrage

- **Retention** : SQLite (`sqlite3` stdlib, zero dep -- R20). Rejete : spool JSONL
  (pas de requetes indexees), ring plus grand (pas de persistance).
- **Transport live** : delta-poll par `seq` (`?since_seq=N`). Rejete : SSE (canal par
  panel, reconnexion, plus de surface de test) ; SSE+fallback (double mecanisme).
- **Architecture** : approche A -- SQLite devient LE store, le ring meurt. Rejete :
  approche B ring+spool (double source de verite pour proteger un hot path qui n'est
  pas menace : les traces arrivent au rythme des actions d'agent, quelques par seconde).

## 1. Backend -- `SqliteTraceStore` (`recette/platform/proxy/store.py`)

Remplace `RingTraceRecorder` et `WireFlowRecorder`.

- Fichier : `.run/proxy_traces.db` (env `INSPECT_IA_AGENTS_PROXY_DB`, R5 config-first).
  `sqlite3` stdlib, `PRAGMA journal_mode=WAL`, connexion partagee
  `check_same_thread=False` + lock.
- Deux tables : `proxy_traces`, `wire_flows`. `seq INTEGER PRIMARY KEY AUTOINCREMENT`
  (ordre total monotone, remplace le compteur memoire). Index : `run_id`, `agent_id`
  (traces) ; `run_id`, `host` (wire).
- **`side_effect_hash` du wire flow calcule a l'INSERT** et persiste en colonne :
  `reconcile` devient un set-diff sur colonnes indexees, plus aucun re-parse JSON
  (goulot 3 elimine a la racine).
- Retention : cap `INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS` (defaut 50 000), prune du plus
  ancien par lot a l'insert. La retention traverse le restart.
- I4 : aucune horloge murale dans le store. `timestamp` reste un input capture porte
  par la trace ; rien n'est stampe a l'insert. Lectures ordonnees par `seq`.
- I1 (clarification) : ce store est un **buffer de debug d'observabilite**, PAS
  l'event store d'audit. `DELETE /proxy/traces` garde sa semantique de purge ;
  l'Audit Plane reste la source de verite de l'historique.
- **Failure mode (obligatoire, fail-safe)** : une erreur du store (disque plein, DB
  corrompue) est loggee structuree et avalee -- l'execution proxy (I5) ne bloque
  JAMAIS sur l'observabilite. `/proxy/debug` expose `store_error` pour l'operateur.

## 2. API -- delta + filtres serveur (`recette/api/routers/proxy.py`)

- `GET /proxy/traces` : nouveaux params `since_seq`, `agent_id`, `target`, `outcome`
  (`ok|error`), `q` (texte), `limit`. Enveloppe : `{traces, last_seq, total, reset}`.
  `tail` conserve (compat).
- `GET /proxy/wire` : memes ajouts (`since_seq`, `host`, `method`, `status`, `q`,
  `limit`), meme enveloppe.
- Semantique `reset` : si `since_seq` client > `last_seq` serveur (purge ou restart),
  la reponse porte `reset: true` et le client remplace son etat local (resync full).
- **Nouveau `GET /proxy/sessions/delta`** : traces + wire + reconcile en UNE reponse
  (remplace les 4 requetes paralleles de SessionsPanel).
- Badges (`trace_count`, `flow_count`) : `SELECT COUNT(*)` -- plus de snapshot O(n)
  pour un compteur.

## 3. Console -- delta-merge + virtualisation + follow

- **Hook partage `useDeltaFeed`** : fetch `since_seq=last`, append, dedupe par `seq`,
  cap client 2 000 lignes, gere `reset`. Poll ramene a **1 s** (un tick transporte
  0-5 traces au lieu de 512).
- **`VirtualList`** : fenetrage ecrit a la main (~60 lignes, spacers haut/bas,
  AUCUNE dep npm nouvelle) -- ~30 noeuds DOM rendus quel que soit le buffer.
- **Barre de filtres -> query params serveur** (agent/target/outcome/texte). Un
  changement de filtre reset le feed (refetch avec les nouveaux params).
- **Follow intelligent** : colle en bas seulement si deja en bas ; scroll manuel =
  bouton "N nouvelles traces" au lieu d'un saut force.
- SessionsPanel bascule sur `/proxy/sessions/delta`.
- R16 contract gate : nouvelles fixtures payload REELLES pour chaque enveloppe
  modifiee + render-and-assert par panel touche.

## 4. Tests (R20)

- unittest store : insert/query/filtres/`since_seq`/prune/clear ; hash-a-l'insert ;
  **test de replay deterministe** (memes inserts -> memes bytes en sortie de query) ;
  equivalence reconcile ancien vs nouveau (golden).
- API : nouveaux params, enveloppes, semantique `reset`.
- vitest : `useDeltaFeed` (merge/dedupe/reset), `VirtualList`, panels avec nouvelles
  fixtures.
- Smoke console versionne (`./recette.sh smoke`) : flux proxy live verifie.

## Gains attendus (mesurables)

| Goulot | Avant | Apres |
|--------|-------|-------|
| Payload par tick | buffer entier x4 requetes | delta seul, 1 requete sessions |
| Filtre agent | 512 traces chargees puis filtrees client | query indexee serveur |
| Reconcile | re-hash de 512 flows par appel | colonne persistee, set-diff |
| Noeuds DOM | 512 | ~30 (fenetre) |
| Retention | 512, perdue au restart | 50 000, persistee |
| Latence live percue | poll 2 s | poll 1 s (delta quasi gratuit) |
