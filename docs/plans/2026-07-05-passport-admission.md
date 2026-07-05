# Passport Admission (Phase 2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (ou
> subagent-driven-development) pour implementer ce plan tache par tache.
> Design valide : `docs/plans/2026-07-05-passport-admission-design.md`.

**Goal:** Un agent runtime n'est ADMIS a agir que si son passeport signe est trusted --
garde pre-lancement (403) + middleware par action (ACTION_DENIED), mode configurable
observe (defaut) / enforce, admission auditee (I1).

**Architecture:** Une primitive pure `admit_agent` reutilise l'oracle `attest_passport`
(deja equivalence-teste vs Rust, phase 1). Deux points de garde : l'endpoint
`POST /runs` (fail-fast) et une `PassportAdmissionMiddleware` dans la pipeline gateway
existante (re-verifie a chaque action avec le timestamp CAPTURE de l'action -> attrape
l'expiration mid-run). Le passeport d'un agent runtime vit dans
`data/agent_passports/<id>.json` (gitignore). En `observe` on audite sans bloquer.

**Tech Stack:** Python (recette platform + FastAPI), l'oracle `recette/adapters.py`
`attest_passport`, le crate CLI `discoveryprobe-inventory passport issue --out` (emission),
console React/TS. `cryptography` (extra `[bundle]`, deja utilise).

**Regles projet (CHAQUE tache) :** commits Conventional SANS "Co-Authored-By: Claude"
(R1) ; zero emoji (R10) ; commentaires source en anglais (R12) ; determinisme I4 (`now`
INJECTE partout -- jamais `datetime.now()` dans un chemin de decision/admission ; le
middleware doit rester deterministe, cf. `middleware.py` docstring) ; fail-safe jamais
fail-open ; secrets/keyring via config (R5/R8) ; gates avant commit (`make gates`,
`python3 -m unittest discover -s tests`, console si touche).

---

## Phase 1 -- La primitive d'admission (pure)

### Task 1: `admit_agent` + AdmissionVerdict + config env

**Files:**
- Create: `recette/platform/admission.py`
- Test: `tests/test_admission.py`

La primitive reutilise l'oracle. AUCUN I/O dans `admit_agent` (le passeport + le trust +
le now sont des inputs) ; un loader separe fait l'I/O.

Constantes (R5) : `ENFORCE_ENV = "INSPECT_IA_AGENTS_PASSPORT_ENFORCE"`,
`PASSPORT_DIR_ENV = "INSPECT_IA_AGENTS_PASSPORT_DIR"`,
`DEFAULT_PASSPORT_DIR = "data/agent_passports"`.

```python
@dataclass(frozen=True)
class AdmissionVerdict:
    status: str            # trusted | untrusted | unsigned | malformed
    reasons: list[dict]    # kind-tagged, from attest_passport
    admitted: bool         # (status == "trusted") or (not enforce)
    mode: str              # "observe" | "enforce"

def admit_agent(passport, declared, trust, now, enforce) -> AdmissionVerdict: ...
def enforce_from_env() -> bool:  # ENFORCE_ENV.strip().lower() == "enforce"
def load_agent_passport(agent_id, base_dir) -> dict | None:  # reads <dir>/<id>.json, None if absent
def load_trust(path) -> dict[str, str]:  # reads the keyring json; {} on missing (fail-safe)
```

**Step 1: Failing tests** (`tests/test_admission.py`) :
- `admit_agent(None, [...], trust, now, enforce=False)` -> status `unsigned`, admitted
  True (observe admits everything, but the status is still the real one).
- `admit_agent(None, [...], trust, now, enforce=True)` -> status `unsigned`, admitted False.
- A trusted passport (reuse a corpus one: read
  `corpus/repos/gh-pr-bot/repo/.inspect_ia_agents/passport.json` + the corpus trust
  `corpus/keys/test-authority.trust.json` + a `now` before its exp + declared = its scope)
  -> status `trusted`, admitted True in BOTH modes.
- An expired passport (`corpus/repos/gh-passport-expired/...`) -> status `untrusted`
  reasons `[{"kind":"expired"}]`, admitted False in enforce, True in observe.
- `enforce_from_env`: env unset -> False; "enforce" -> True; "observe"/"garbage" -> False.
- `load_agent_passport`: absent file -> None; present -> the dict. `load_trust`: missing
  path -> `{}` (fail-safe, no raise).
- Replay determinism: same inputs -> identical AdmissionVerdict (dataclass eq), 2 calls.

**Step 2:** `python3 -m unittest tests.test_admission -v` -> FAIL (module absent).
**Step 3:** Implement. `admit_agent` calls
`attest_passport(passport, trust, now, declared)`, wraps the tuple. Fail-safe: wrap the
oracle call in try/except -> on ANY exception return status `untrusted` reasons
`[{"kind":"oracle_error"}]` admitted=(not enforce) (never trusted, never fail-open).
**Step 4:** PASS + `make gates` (ruff/mypy/bandit) on the new file.
**Step 5:** Commit `feat(admission): admit_agent primitive reusing the attestation oracle`.

## Phase 2 -- Modele d'evenement

### Task 2: EventKind.AGENT_ADMISSION (additif)

**Files:**
- Modify: `recette/platform/events.py:22-31` (ajouter le variant)
- Test: `tests/test_events.py` (ou le test qui couvre EventKind ; grep
  `AGENT_ADMISSION\|EventKind` tests/)

**Step 1: Failing test** -- `EventKind.AGENT_ADMISSION == "agent_admission"` ; il
serialise/round-trip comme les autres ; il n'entre PAS dans les kinds d'action existants
(pas de regression sur la logique action_requested/executed/denied).
**Step 2:** FAIL. **Step 3:** Ajouter `AGENT_ADMISSION = "agent_admission"  # runtime
admission verdict (I1/I3), audited at launch`. **Step 4:** PASS + suite complete verte
(l'ajout est additif). **Step 5:** Commit
`feat(events): AGENT_ADMISSION event kind (additive)`.

## Phase 3 -- Garde pre-lancement

### Task 3: admission a l'endpoint POST /runs

**Files:**
- Modify: `recette/api/routers/runs.py:19-97` (dans `launch`, apres la validation des
  champs requis, avant la construction du llm/`mgr.start`)
- Modify: `recette/api/app.py` (exposer le trust keyring + le passport dir + le mode sur
  `app.state` si besoin -- OU la primitive les charge via env ; prefer app.state pour la
  testabilite : `app.state.passport_trust`, `app.state.passport_dir`,
  `app.state.passport_enforce`, initialises depuis env dans create_app)
- Test: `tests/test_api_runs_admission.py` (nouveau ; suit le style de
  `tests/test_api_*` -- construit l'app via create_app, TestClient ; run avec le venv
  `[api]` `/home/fpizzi/recette_agent/.venv/bin/python`)

Logique dans `launch` (lane_b), APRES le bloc `missing` (ligne ~41), AVANT
`from ...llm import LlmBackend` :
```python
# I3 admission gate: verify the agent's signed passport before it can run.
# Always audited (I1); blocks only in enforce mode (fail-safe deny).
from ...platform.admission import admit_agent, load_agent_passport
from ...platform.events import EventKind
now = _capture_timestamp()  # captured INPUT (I4), mirror actions.py
passport = load_agent_passport(agent_cfg["id"], request.app.state.passport_dir)
verdict = admit_agent(
    passport, agent_cfg.get("capability_scope"),
    request.app.state.passport_trust, now, request.app.state.passport_enforce,
)
store_event(  # append AGENT_ADMISSION to the event store (I1)
    request.app.state.event_store, agent_id=agent_cfg["id"], verdict=verdict, now=now,
)
if request.app.state.passport_enforce and verdict.status != "trusted":
    raise HTTPException(status_code=403,
        detail=f"agent {agent_cfg['id']!r} admission denied: {verdict.status} {verdict.reasons}")
```
`_capture_timestamp` : reutiliser celui de `recette/api/routers/actions.py` (importer ou
factoriser dans un util partage -- DRY ; s'il est prive, factoriser
`recette/api/_timestamp.py`). Le helper `store_event` append un StoredEvent kind
AGENT_ADMISSION avec payload `{agent_id, status, reasons, mode, admitted}` via
`request.app.state.event_store.append(...)` + un event_id (RestartSafeIdGenerator, comme
les autres appends). La reponse `/runs` gagne `"admission": {status, mode, admitted}`.

**Step 1: Failing tests** :
- observe (defaut) + agent sans passeport -> 201, run demarre, la reponse porte
  `admission.status == "unsigned"` `admitted True`, ET un event AGENT_ADMISSION est dans
  le store.
- enforce + agent sans passeport -> 403, AUCUN run demarre, event AGENT_ADMISSION
  `admitted False` present.
- enforce + agent avec passeport trusted (emettre un passeport de test dans un tmp
  passport_dir + trust matching -> voir Task 5 pour l'emission ; pour CE test, ecrire un
  passeport trusted a la main via le crate ou une fixture) -> 201, admission trusted.
- L'event AGENT_ADMISSION porte le bon payload (status/mode/admitted/reasons).
- Determinisme : `now` capture au boundary, pas d'horloge interne au chemin d'admission.

**Step 2-4:** TDD (venv [api]). Full suite verte.
**Step 5:** Commit `feat(api): passport admission gate on POST /runs (audited, enforce-gated 403)`.

## Phase 4 -- Middleware par action

### Task 4: PassportAdmissionMiddleware dans la gateway

**Files:**
- Create: `recette/platform/passport_middleware.py` (ou ajouter a `middleware.py` si
  cohesif -- prefer un fichier dedie)
- Modify: `recette/api/app.py:339` (construire la `MiddlewarePipeline` avec la nouvelle
  middleware et la passer a `Gateway(..., middleware=...)`)
- Test: `tests/test_passport_middleware.py` + un test d'integration gateway
  (`tests/test_gateway_admission.py` ou etendre `tests/test_gateway*.py`)

La middleware implemente le protocol `Middleware` (`recette/platform/middleware.py` :
`before(request) -> str | None`, `after(request, outcome) -> None`). Elle reste
DETERMINISTE (pas d'horloge : elle lit `request.timestamp`, un input capture -- I4).

```python
class PassportAdmissionMiddleware:
    def __init__(self, *, trust, passport_dir, enforce, declared_for):
        # declared_for(agent_id) -> capability_scope (from the config store)
        ...
    def before(self, request) -> str | None:
        if not self._enforce:
            return None  # observe: never veto here (the launch gate already audited)
        passport = load_agent_passport(request.agent_id, self._passport_dir)
        declared = self._declared_for(request.agent_id)
        v = admit_agent(passport, declared, self._trust, request.timestamp, enforce=True)
        if v.status != "trusted":
            return f"untrusted_passport: {v.status} {v.reasons}"
        return None
    def after(self, request, outcome): return None
```
Cache par `agent_id` autorise (le passeport ne change pas pendant un run) MAIS le
verdict depend de `request.timestamp` (expiry) -> cache le PASSEPORT (I/O) pas le verdict.

**Step 1: Failing tests** :
- enforce + agent untrusted -> `before` retourne une raison -> la gateway `submit`
  produit ACTION_DENIED avec `reason` contenant `untrusted_passport` (test d'integration :
  construire une Gateway avec la middleware + un agent sans/avec passeport).
- observe -> `before` retourne None (pas de veto ; la policy normale decide).
- **Expiration mid-run** : un passeport dont l'exp est APRES le now du launch mais AVANT
  le timestamp d'une action ulterieure -> la 1re action passe (si trusted au launch), une
  action avec `request.timestamp > exp` -> ACTION_DENIED expired. (Prouve la valeur du
  2e garde.)
- trusted + timestamp avant exp -> pas de veto.
- fail-safe : la middleware qui leve est deja geree par la pipeline (deny) -- verifier
  qu'une erreur interne ne fail-open pas (elle retourne une raison ou laisse la pipeline
  denier).

**Step 2-4:** TDD. Full suite verte (la Gateway sans middleware garde son comportement --
`app.py` la branche ; les tests gateway existants sans middleware restent verts).
**Step 5:** Commit `feat(gateway): PassportAdmissionMiddleware -- per-action re-attestation (catches mid-run expiry)`.

## Phase 5 -- Passeports runtime + recette

### Task 5: emettre des passeports runtime + gitignore

**Files:**
- Modify: `.gitignore` (ajouter `data/agent_passports/` -- gitignore, R18/R8)
- Create: `data/agent_passports/<id>.json` pour >=1 agent de
  `config/inspect_ia_agents.config.json` (via le crate) -- MAIS gitignore, donc PAS
  committe. A la place : un script/procedure reproductible + une fixture de TEST committee
  sous `tests/fixtures/agent_passports/` pour les tests (un passeport trusted + un
  untrusted, emis avec la cle de test du corpus).
- Create: `tests/fixtures/agent_passports/{trusted-agent,expired-agent}.json` (fixtures de
  test, emis via `discoveryprobe-inventory passport issue ... --out`).
- Modify: `docs/runbooks/passport-admission.md` (Task 7) documente l'emission runtime.

**Step 1:** Build le binaire (`cd discoveryprobe && cargo build --release`). Emettre 2
passeports de test via `passport issue --out tests/fixtures/agent_passports/<name>.json`
(un avec exp future = trusted, un avec exp passee = expired). Verifier chacun avec
`passport verify --trust corpus/keys/test-authority.trust.json --now <ref>`.
**Step 2:** Les tests des Tasks 3/4 pointent leur `passport_dir`/fixture sur ce repertoire
committe (les tests ne dependent pas de `data/` gitignore).
**Step 3:** `.gitignore` : `data/agent_passports/` (le repertoire RUNTIME est local, jamais
committe -- comme `data/backend_secrets.json`). Verifier `git check-ignore
data/agent_passports/x.json`.
**Step 5:** Commit `feat(corpus): runtime agent passport test fixtures + gitignore data/agent_passports`.

### Task 6: recette d'admission (observe/enforce/expiry/replay) + coverage

**Files:**
- Create/Modify: `tests/test_admission_recette.py` (un scenario de bout en bout de
  l'admission) ou consolider dans les tests des Tasks 3/4.
- Modify: le coverage guard si l'admission est une dimension a couvrir (grep
  `test_coverage_guard`)

**Step 1: Failing tests** -- le tableau de verite complet :
| mode | passeport | attendu launch | attendu action |
|------|-----------|----------------|----------------|
| observe | absent | 201 + audit unsigned | pas de veto |
| observe | untrusted | 201 + audit untrusted | pas de veto |
| enforce | absent | 403 | (jamais lance) |
| enforce | untrusted | 403 | (jamais lance) |
| enforce | trusted, exp future | 201 | actions passent |
| enforce | trusted au launch, exp < action ts | 201 | ACTION_DENIED expired |
+ **replay deterministe** : rejouer le meme stream d'admission -> memes events
(I4). **Step 2-4:** TDD. **Step 5:** Commit
`test(admission): observe/enforce/mid-run-expiry truth table + replay`.

## Phase 6 -- Console (lisibilite) + docs

### Task 7: badge admission console (R16) + reponse /runs

**Files:**
- Modify: `console/src/api/client.ts` (le type de la reponse `/runs` gagne
  `admission?: { status, mode, admitted }`), `console/src/types/*`
- Modify: le composant qui lance/affiche un run (grep `launch`, `runs`, dashboard/agents --
  `console/src/pages/dashboard/index.tsx` ou `console/src/pages/agents/index.tsx`) : un
  badge admission (status trusted/untrusted/unsigned/malformed + mode observe/enforce)
- Create/Modify: fixture reelle `__fixtures__/*.fixture.json` (capturer la reponse `/runs`
  reelle avec le champ admission) + render-and-assert (R16)
- Test: le `*.test.tsx` du composant touche

TDD vitest : le badge keye sur `admission.status` + montre le mode ; couvre les etats.
`./recette.sh console-build` + `console-test`. **Step 5:** Commit
`feat(console): admission badge on run launch (R16)`.

### Task 8: runbook + docs fr/en

**Files:**
- Create: `docs/runbooks/passport-admission.md` (fr) -- le mode observe/enforce, les deux
  gardes, l'emission runtime, l'event AGENT_ADMISSION, les failure modes, l'env
  `INSPECT_IA_AGENTS_PASSPORT_ENFORCE`/`_DIR`. R13 : verifier chaque flag/env/path.
- Modify: `docs/runbooks/passport-recette.md` (lien vers l'admission -- phase 2)
- Create: le twin EN sous `docs-site/i18n/en/.../runbooks/passport-admission.md`

**Step 5:** Commit `docs(admission): passport-admission runbook + link (fr/en)`.

## Phase 7 -- Gates finales

### Task 9: gates + preuve live

**Steps:**
1. `python3 -m unittest discover -s tests` + `/home/fpizzi/recette_agent/.venv/bin/python
   -m unittest discover -s tests` (venv [api]) verts.
2. `make gates` (ruff/mypy/bandit) + coverage guard verts.
3. `./recette.sh console-build` + `console-test` verts.
4. Preuve live (R14) : `./recette.sh platform up`, emettre un passeport runtime pour un
   agent config, `INSPECT_IA_AGENTS_PASSPORT_ENFORCE=enforce` (via l'env du service --
   ATTENTION R19 : le service se lance par recette.sh ; pour la preuve, documenter comment
   l'operateur passe l'env, ou un test live cible). Lancer l'agent depuis la console :
   trusted -> demarre + badge trusted ; un agent sans passeport en enforce -> 403 visible.
   Capturer (flux + DOM + screenshot). En observe (defaut) tout tourne, badge montre le
   status. Adapter `scripts/smoke_console.py` si un flux d'admission est verifiable.
5. Verifier R13 : chaque commande/env du runbook existe.

---

## Ordre & dependances

1 -> 2 (primitive + event) ; 3 (launch gate, apres 1+2) ; 4 (middleware, apres 1) ;
5 (fixtures, avant/pendant 3+4 pour les tests trusted) ; 6 (recette, apres 3+4+5) ;
7 -> 8 (console+docs) ; 9 (gates).

## Ce qui ne change PAS (garde-fous)

- L'oracle `attest_passport` est REUTILISE tel quel (zero divergence phase 1).
- La Gateway sans middleware garde son comportement (les tests gateway existants restent
  verts) ; la middleware est branchee dans `app.py`.
- Mode `observe` par defaut : aucun agent runtime existant n'est brique.
- I1 (AGENT_ADMISSION additif, pas de migration destructive), I4 (`now` injecte partout),
  fail-safe (exception -> deny, jamais fail-open), R8 (`data/agent_passports/` gitignore).
