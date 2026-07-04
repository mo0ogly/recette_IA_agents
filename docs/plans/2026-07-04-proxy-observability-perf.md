# Proxy Observability Perf Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (ou
> subagent-driven-development) pour implementer ce plan tache par tache.
> Design valide : `docs/plans/2026-07-04-proxy-observability-perf-design.md`.

**Goal:** Remplacer les rings memoire 512 par un store SQLite indexe (retention
50k, hash wire a l'insert), ajouter delta-poll + filtres serveur a l'API, et
rendre la console fluide (delta-merge, virtualisation, follow intelligent,
SessionsPanel coalesce).

**Architecture:** `SqliteProxyStore` (sqlite3 stdlib, WAL, un fichier
`.run/proxy_traces.db`) porte deux tables `proxy_traces`/`wire_flows` ; deux
facades `SqliteTraceRecorder`/`SqliteWireRecorder` implementent les protocoles
existants (`record`/`snapshot`/`clear`) PLUS `query`/`count`/`last_seq`, si bien
que les endpoints receipts/merkle/discovery-exchange continuent de marcher sans
changement. L'API gagne `since_seq` + filtres + enveloppe `{items, last_seq,
total, reset}` ; la console gagne `useDeltaFeed` + `VirtualList`.

**Tech Stack:** Python stdlib `sqlite3` (zero dep, R20), FastAPI existant,
React/TS existant (AUCUNE dep npm nouvelle).

**Regles projet a respecter dans CHAQUE tache:** commits Conventional Commits
SANS "Co-Authored-By: Claude" (R1), zero emoji (R10), commentaires source en
anglais (R12), pas de `time.time()`/`random` dans un chemin de decision (I4),
fail-safe jamais fail-open, gates avant chaque commit
(`python3 -m unittest discover -s tests` pour le Python,
`./recette.sh console-test` + `console-build` pour le TS).

---

## Phase 1 -- Backend store

### Task 1: SqliteProxyStore -- schema + record + snapshot (traces)

**Files:**
- Create: `recette/platform/proxy/store.py`
- Test: `tests/test_proxy_store.py`

Le store possede la connexion (`sqlite3.connect(path, check_same_thread=False)`
+ `threading.Lock`), `PRAGMA journal_mode=WAL`, et cree les deux tables:

```sql
CREATE TABLE IF NOT EXISTS proxy_traces (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL, timestamp TEXT NOT NULL, agent_id TEXT NOT NULL,
  target_system TEXT NOT NULL, target TEXT NOT NULL, action_type TEXT NOT NULL,
  resource TEXT NOT NULL, request_payload TEXT NOT NULL,
  ok INTEGER NOT NULL, status_code INTEGER NOT NULL,
  side_effect_hash TEXT, error TEXT, run_id TEXT, response TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_run ON proxy_traces(run_id);
CREATE INDEX IF NOT EXISTS idx_traces_agent ON proxy_traces(agent_id);
CREATE TABLE IF NOT EXISTS wire_flows (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  method TEXT NOT NULL, scheme TEXT NOT NULL, host TEXT NOT NULL,
  port INTEGER NOT NULL, path TEXT NOT NULL, status_code INTEGER NOT NULL,
  ok INTEGER NOT NULL, content_type TEXT NOT NULL,
  request_body TEXT NOT NULL, response_body TEXT NOT NULL,
  run_id TEXT, duration_ms REAL, side_effect_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_wire_run ON wire_flows(run_id);
CREATE INDEX IF NOT EXISTS idx_wire_host ON wire_flows(host);
```

`request_payload`/`response` stockes en JSON compact
(`json.dumps(..., sort_keys=True, separators=(",", ":"))` -- byte-stable, I4).
Constantes (R5): `DB_PATH_ENV = "INSPECT_IA_AGENTS_PROXY_DB"`,
`DEFAULT_DB_PATH = ".run/proxy_traces.db"`,
`MAX_ROWS_ENV = "INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS"`, `DEFAULT_MAX_ROWS = 50_000`.
`db_path_from_env()` et `max_rows_from_env()` (memes patterns que
`debug_enabled_from_env` dans `tracing.py:36-43`). Le chemin `":memory:"` est
supporte (tests). `mkdir(parents=True)` sur le repertoire parent.

**Step 1: Failing test** -- `tests/test_proxy_store.py`:
`SqliteTraceRecorder(store)` avec store `:memory:`; `record()` de 3
`PlatformActionEvent`/`ExecutionResult` (reutiliser les helpers de
`tests/test_proxy_tracing.py` -- lire ce fichier d'abord pour copier la
construction event/result), puis `snapshot()` rend 3 `ProxyTrace` ordonnees
seq 1,2,3 avec les memes champs qu'avant (compat champ a champ avec
`tracing.py:46-95`). Aucune horloge murale stockee.

**Step 2:** `python3 -m unittest tests.test_proxy_store -v` -> FAIL (module absent).

**Step 3:** Implementer `SqliteProxyStore` (conn+schema+lock) et
`SqliteTraceRecorder` avec `record(event, result, run_id=None)` (INSERT, jamais
raise: try/except -> `logging.getLogger("recette.proxy.store").error(...)` +
`self._store_error = str(exc)`), `snapshot() -> list[ProxyTrace]`
(`SELECT * ORDER BY seq`, reconstruit les dataclasses, `json.loads` des blobs),
`clear()` (`DELETE FROM proxy_traces` -- buffer de debug, PAS l'audit store,
I1 clarifie dans le docstring module), propriete `store_error`.

**Step 4:** Test PASS. **Step 5:** Commit
`feat(proxy): sqlite trace store -- schema, record, snapshot (traces)`.

### Task 2: SqliteWireRecorder -- record + hash a l'insert

**Files:**
- Modify: `recette/platform/proxy/store.py`
- Test: `tests/test_proxy_store.py`

**Step 1: Failing tests** -- `record(payload)` normalise via
`normalize_flow` (import depuis `wire.py`, reutilise tel quel -- DRY) et
retourne un `WireFlow`; `snapshot()` compatible. NOUVEAU: le
`side_effect_hash` est calcule a l'INSERT via
`wire_flow_side_effect_hash(flow.to_dict())` (import de `reconcile.py:101`) et
persiste en colonne; test: un payload governed-action (path `/github/execute`,
bodies JSON -- copier la fixture de `tests/test_api_wire_session_hash.py`)
stocke un hash non-null, un payload non-governed stocke NULL.
Ajouter une methode `snapshot_dicts()` qui rend les dicts AVEC
`side_effect_hash` inclus (ce que `GET /proxy/wire` enrichissait a la volee).

**Step 2:** FAIL. **Step 3:** Implementer. **Step 4:** PASS.
**Step 5:** Commit `feat(proxy): sqlite wire recorder -- hash computed at insert`.

### Task 3: query/count/last_seq + prune + replay deterministe

**Files:**
- Modify: `recette/platform/proxy/store.py`
- Test: `tests/test_proxy_store.py`

**Step 1: Failing tests**
- `query_traces(since_seq=None, run_id=None, agent_id=None, target=None,
  outcome=None, q=None, limit=None, tail=None) -> tuple[list[ProxyTrace], int, int]`
  (items, last_seq, total-apres-filtres). SQL WHERE indexe; `outcome` mappe
  `"ok" -> ok=1`, `"fail" -> ok=0`; `q` = LIKE sur
  action_type/resource/request_payload/response; `since_seq` -> `seq > ?`;
  `tail` (compat) -> les N derniers du resultat filtre.
- `query_wire(since_seq, run_id, host, method, status, q, limit, tail)` idem
  (q = LIKE sur path/request_body/response_body).
- `count_traces()`, `count_wire()` = `SELECT COUNT(*)`.
- `last_seq_traces()`, `last_seq_wire()` = `SELECT MAX(seq)` (0 si vide).
- Prune: avec `max_rows=5`, inserer 8 traces -> `count_traces() == 5`, les seq
  restantes sont 4..8 (les plus anciennes purgees). Prune a l'insert
  (`DELETE FROM t WHERE seq <= last - max_rows`), verif au modulo
  `_PRUNE_EVERY = 64` inserts pour l'amortir.
- **Replay deterministe (I4/R11):** deux stores `:memory:` recevant la MEME
  sequence de record() -> `json.dumps` des `snapshot_dicts()` byte-identiques.

**Step 2:** FAIL. **Step 3:** Implementer (SQL parametre, jamais de f-string
dans le WHERE -- bandit/`make gates` doit rester vert).
**Step 4:** PASS + `make gates`. **Step 5:** Commit
`feat(proxy): indexed queries, counts, prune cap, deterministic replay test`.

### Task 4: cablage app.py + retrait des rings

**Files:**
- Modify: `recette/api/app.py:280-303` (remplacer `RingTraceRecorder`/
  `WireFlowRecorder` par les recorders SQLite)
- Modify: `recette/platform/proxy/tracing.py` (supprimer `RingTraceRecorder`),
  `recette/platform/proxy/wire.py` (supprimer `WireFlowRecorder`)
- Test: `tests/test_proxy_tracing.py`, `tests/test_wire_proxy.py` (migrer vers
  les classes SQLite `:memory:`), plus tout test qui instancie les rings
  (`grep -rln "RingTraceRecorder\|WireFlowRecorder" tests/ recette/`)

**Step 1:** `grep` la liste exacte des usages. **Step 2:** `create_app` gagne
un parametre optionnel `proxy_db_path: str | None = None` (tests -> `:memory:`);
defaut = `db_path_from_env()`. Les deux `app.state.*_recorder` pointent sur les
recorders SQLite. `GET /proxy/debug` expose en plus
`"store_error": recorder.store_error`. **Step 3:** Migrer les tests un par un
(la construction change, les assertions restent -- le comportement observable
est le meme). Supprimer les classes ring + `rotate_dir` mort si plus reference
(`rotate.py` reste si d'autres usages -- verifier par grep).
**Step 4:** Suite complete `python3 -m unittest discover -s tests` verte.
**Step 5:** Commit `refactor(proxy): sqlite store replaces in-memory rings (app wiring + tests)`.

### Task 5: reconcile consomme le hash persiste

**Files:**
- Modify: `recette/platform/proxy/reconcile.py:131-165` (`reconcile_strict`)
- Modify: `recette/api/routers/proxy.py:305-328` (`list_wire_flows` n'enrichit
  plus a la volee: le dict du store porte deja `side_effect_hash`),
  `proxy.py:367-401` (`_build_run_allowlist` passe `snapshot_dicts()`)
- Test: `tests/test_reconcile.py` (ajout), `tests/test_api_wire_session_hash.py`
  (doit rester vert tel quel)

**Step 1: Failing test** -- `reconcile_strict` utilise
`flow.get("side_effect_hash")` quand la cle est PRESENTE (meme si None -- None
persiste = non-governed, benin), et ne recompute
`wire_flow_side_effect_hash` que si la cle est ABSENTE (compat anciens dicts).
Test golden: memes entrees avec hash precompute vs sans -> rapports identiques
byte a byte.
**Step 2:** FAIL. **Step 3:** Implementer (fonction reste pure, I4).
**Step 4:** PASS. **Step 5:** Commit
`perf(proxy): reconcile consumes persisted wire hash, no re-parse`.

## Phase 2 -- API delta + filtres

### Task 6: GET /proxy/traces -- since_seq + filtres + enveloppe

**Files:**
- Modify: `recette/api/routers/proxy.py:76-92`
- Test: `tests/test_api_proxy_traces.py` (etendre)

**Step 1: Failing tests** -- nouveaux params query `since_seq: int | None`,
`agent_id`, `target`, `outcome` (`ok|fail`), `q`, `limit: int | None`.
Reponse conserve `debug_enabled` + `traces` (compat) et AJOUTE `last_seq`,
`total`, `reset: bool`. Semantique reset: `since_seq > last_seq_traces()` ->
`reset: true` + renvoi full (depuis 0, borne par limit/tail). Cas a tester:
tail seul (compat inchangee), since_seq incremental (2 traces nouvelles sur 5),
filtre agent_id serveur, outcome=fail, reset apres clear.
**Step 2:** FAIL. **Step 3:** L'endpoint delegue a `query_traces` (plus AUCUN
snapshot+filtre Python). **Step 4:** PASS. **Step 5:** Commit
`feat(api): /proxy/traces delta-poll (since_seq) + server-side filters`.

### Task 7: GET /proxy/wire -- pareil + counts SELECT

**Files:**
- Modify: `recette/api/routers/proxy.py:305-328` (params `since_seq`, `host`,
  `method`, `status`, `q`, `limit` + enveloppe `last_seq/total/reset`),
  `proxy.py:46-53` (`trace_count` -> `count_traces()`),
  `proxy.py:227-241` (`flow_count` -> `count_wire()`)
- Test: `tests/test_api_wire.py` (etendre)

Memes 5 steps que Task 6. Commit:
`feat(api): /proxy/wire delta-poll + filters; COUNT-based badges`.

### Task 8: GET /proxy/sessions/delta (coalesce)

**Files:**
- Modify: `recette/api/routers/proxy.py` (nouvel endpoint)
- Test: `tests/test_api_proxy_sessions_delta.py` (nouveau)

**Step 1: Failing tests** -- `GET /proxy/sessions/delta?since_seq=&wire_since_seq=&run_id=&strict=`
rend en UNE reponse:
```json
{
  "debug_enabled": true,
  "traces": [...], "last_seq": 12, "reset": false,
  "wire_flows": [...], "wire_last_seq": 4, "wire_reset": false,
  "reconcile": {"ok": true, "bypass_flows": [...], "audited_run_ids": []}
}
```
traces/wire = delta depuis leurs since_seq respectifs (memes semantiques
reset). `reconcile` = le join complet courant (petit: verdict + bypass_flows).
Tester: premier appel (since absents -> full), appel incremental, run_id scope.
**Step 2-4:** TDD. **Step 5:** Commit
`feat(api): coalesced /proxy/sessions/delta (traces+wire+reconcile in one call)`.

## Phase 3 -- Console

### Task 9: client.ts + types -- enveloppes delta

**Files:**
- Modify: `console/src/api/client.ts` (getProxyTraces/getWireFlows: params
  objet `{tail?, runId?, sinceSeq?, agentId?, target?, outcome?, q?, limit?}`;
  nouveau `getProxySessionsDelta(params)`)
- Modify: `console/src/types/platform.ts` (`ProxyTraceResponse` +=
  `last_seq: number; total: number; reset: boolean`; idem `WireFlowResponse`;
  nouveau `SessionsDeltaResponse`)
- Test: les tests contract existants des panels doivent encore compiler
  (fixtures etendues Task 12)

TDD leger: `./recette.sh console-build` (tsc) est le failing gate. Commit
`feat(console): delta envelopes + sessions-delta client`.

### Task 10: useDeltaFeed + VirtualList (purs, testes)

**Files:**
- Create: `console/src/pages/proxy/useDeltaFeed.ts`
- Create: `console/src/components/VirtualList.tsx`
- Test: `console/src/pages/proxy/useDeltaFeed.test.ts`,
  `console/src/components/VirtualList.test.tsx`

`useDeltaFeed<T extends {seq: number}>`: etat `{items, lastSeq, error}`,
`applyDelta(delta: {items: T[], last_seq: number, reset: boolean})` -- reset ->
remplace; sinon append dedupe par seq, cap client `MAX_CLIENT_ITEMS = 2000`
(drop des plus anciens). La logique de merge est une FONCTION PURE exportee
`mergeDelta(prev, delta)` testee sans DOM (I4 cote client).
`VirtualList`: props `{items, rowHeight, height, renderRow}`; fenetrage par
scrollTop (spacers haut/bas), overscan 5; test jsdom: 1000 items -> < 50 noeuds
rendus; scroll -> la fenetre change.
Vitest d'abord (FAIL), impl, PASS, commit
`feat(console): useDeltaFeed merge hook + hand-rolled VirtualList`.

### Task 11: AppTracesPanel -- delta + filtres serveur + follow

**Files:**
- Modify: `console/src/pages/proxy/AppTracesPanel.tsx` (poll
  `POLL_INTERVAL_MS = 1000`; le tick fetch
  `getProxyTraces({sinceSeq: lastSeq, agentId, ...})` -> `mergeDelta`;
  changement de filtre -> reset du feed (refetch since 0 avec les params);
  liste rendue via `VirtualList`; follow: colle en bas si
  `scrollTop+clientHeight >= scrollHeight - rowHeight`, sinon bouton
  "N nouvelles traces" (`data-testid="proxy-new-traces"`))
- Modify: `console/src/pages/proxy/proxy.css` (`.proxy-new-badge`)
- Test: `console/src/pages/proxy/AppTracesPanel.contract.test.tsx` -- ce test
  n'existe pas encore sous ce nom: le creer (R16) avec la fixture Task 12;
  asserter: rendu avec enveloppe delta, filtre agent poste bien le param
  serveur (spy sur le mock), badge nouvelles-traces visible quand scrolle haut

Les selects de filtre (agentIds/targetSystems/runIds distincts) se peuplent
depuis les items merges (inchange). Commit
`feat(console): app traces panel -- 1s delta poll, server filters, smart follow`.

### Task 12: fixtures R16 + WirePanel + SessionsPanel

**Files:**
- Create/Modify: `console/src/pages/proxy/__fixtures__/*.fixture.json` --
  RE-CAPTURER les payloads REELS (plateforme up via `./recette.sh platform up`,
  `curl 127.0.0.1:8090/proxy/traces?limit=5` etc.) avec les nouveaux champs
  `last_seq/total/reset`; fixture nouvelle `sessions-delta.fixture.json`
- Modify: `console/src/pages/proxy/WirePanel.tsx` (meme bascule delta+virtual
  que Task 11), `console/src/pages/proxy/SessionsPanel.tsx:103-147` (le
  `refresh` devient UN appel `getProxySessionsDelta({sinceSeq, wireSinceSeq,
  runId})` + merge; `getRunEvents` reste separe et conditionne a `runParam`)
- Test: `WirePanel.contract.test.tsx`, `SessionsPanel.contract.test.tsx`
  (adapter aux nouvelles enveloppes/mocks), `useProxyCounts.test.ts` (inchange
  -- verifie)

R16 complet: fixture reelle + render-and-assert par panel modifie. Commit
`feat(console): wire+sessions panels on delta feeds; real fixtures refreshed (R16)`.

## Phase 4 -- Preuves de bout en bout

### Task 13: gates + smoke live

**Steps:**
1. `make gates` (ruff/mypy/bandit) vert.
2. `python3 -m unittest discover -s tests` vert.
3. `./recette.sh console-build` + `./recette.sh console-test` verts.
4. `./recette.sh platform up` + `./recette.sh console start`; verifier dans
   `scripts/smoke_console.py` la section proxy (grep "proxy" -- si elle asserte
   l'ancienne enveloppe, l'adapter) puis `./recette.sh smoke` vert.
5. Preuve delta live (R14): `curl "127.0.0.1:8090/proxy/traces"` -> noter
   last_seq; lancer un run depuis la console; `curl ".../proxy/traces?since_seq=<N>"`
   -> uniquement les nouvelles traces + `reset:false`. Capturer la sortie.
6. `./recette.sh platform down` + `console stop`.
7. Commit final `test(proxy): live smoke proof for delta feeds` (si le smoke a
   ete adapte).

### Task 14: docs + runbook

**Files:**
- Modify: `docs/runbooks/proxy-debug-console.md` (store SQLite, env
  `INSPECT_IA_AGENTS_PROXY_DB`/`_MAX_ROWS`, delta-poll, retention 50k,
  failure mode store_error)
- Docusaurus fr+en si la page proxy y decrit le buffer (grep
  `docs/site/ -r "512\|ring"` pour trouver les mentions a corriger)

Commit `docs(proxy): sqlite store + delta-poll runbook`.

---

## Ordre & dependances

1 -> 2 -> 3 -> 4 -> 5 (backend, sequentiel) ; 6 -> 7 -> 8 (API, apres 4) ;
9 -> 10 -> 11 -> 12 (console, apres 8) ; 13 -> 14.

## Ce qui ne change PAS (garde-fous)

- Les endpoints receipts/merkle/discovery-exchange continuent d'appeler
  `snapshot()`/`snapshot_dicts()` -- forensique a la demande, pas du polling.
- `DELETE /proxy/traces` / `DELETE /proxy/wire` gardent leur semantique.
- L'audit log (event store) n'est touche par RIEN ici (I1).
- Redaction `_redacted_view` inchangee, appliquee sur les dicts sortants.
- Aucune dep npm ni pip nouvelle (R20/R22).
