# Design -- Phase 2 : admission passeport dans la gateway runtime

Date : 2026-07-05
Statut : VALIDE (brainstorm operateur)
Suite de : `docs/plans/2026-07-05-agent-passport-design.md` (phase 1, livree).
Invariants : I3 (liaison d'identite renforcee -- l'agent est lie a une attestation
signee avant d'agir), I4 (verdict deterministe, horloge injectee, replay), I1
(admission auditee, append-only), fail-safe (jamais fail-open).

## Objet

La phase 1 a livre le passeport signe (Contrat 3) + son inspection STATIQUE (crate
exportable `agent-passport`, oracle Python `attest_passport`, corpus). La phase 2
branche la verification dans le chemin RUNTIME : un agent runtime est ADMIS a agir
seulement si son passeport est digne de confiance -- deny-by-default en mode enforce.

## Decisions de cadrage (validees)

- **Enforcement configurable, defaut `observe`** (env `INSPECT_IA_AGENTS_PASSPORT_ENFORCE`,
  valeurs `observe|enforce`, defaut `observe` -- R5). Le verdict est TOUJOURS calcule et
  audite ; il ne BLOQUE qu'en `enforce`. Rejete : deny-by-default strict d'emblee (briquerait
  tous les agents runtime actuels, dont la demo -- aucun n'a de passeport). Migration douce.
- **Passeport runtime dans `data/agent_passports/<agent_id>.json`** (gitignore comme les
  secrets, R18 ; decouple du champ config editable par l'operateur). Rejete : bloc inline
  dans la config (un edit invaliderait la signature), `passport_ref` (indirection).
- **Deux gardes (defense en profondeur)** : pre-lancement (endpoint) + middleware par action
  (gateway). Le middleware attrape l'expiration EN COURS de run (seul cas ou re-verifier a
  chaque action apporte quelque chose).

## Composants

### 1. Primitive d'admission -- `recette/platform/admission.py`

Pure, reutilise l'oracle `attest_passport` (deja equivalence-teste vs Rust -- PAS de
subprocess dans le chemin chaud) :

```
AdmissionVerdict { status: str, reasons: list[dict], admitted: bool, mode: str }
admit_agent(passport: dict | None, declared: list[str] | None, trust: dict[str,str],
            now: str, enforce: bool) -> AdmissionVerdict
```

- `status`/`reasons` viennent de `attest_passport(passport, trust, now, declared)`.
- `admitted = (status == "trusted") or (not enforce)`.
- `declared` = le `capability_scope` de l'agent (croise le scope signe, comme le corpus).
- Un loader `load_agent_passport(agent_id, dir)` lit `data/agent_passports/<id>.json`
  (absent -> None -> status `unsigned`) ; env `INSPECT_IA_AGENTS_PASSPORT_DIR` pour le
  repertoire (R5, defaut `data/agent_passports`).
- `enforce_mode_from_env()` -> bool (`INSPECT_IA_AGENTS_PASSPORT_ENFORCE == "enforce"`).
- `now` est un INPUT (I4). Fail-safe : oracle/crypto absent ou trust vide -> non-trusted,
  jamais trusted.

### 2. Garde pre-lancement -- `recette/api/routers/runs.py`

Dans `launch`, avant `mgr.start` (apres la validation des champs) :
- capture un timestamp au boundary (INPUT, cf. `actions.py::_capture_timestamp`),
- `verdict = admit_agent(load_agent_passport(id), capability_scope, trust, now, enforce)`,
- **audite TOUJOURS** un event `AGENT_ADMISSION` (I1) portant `{agent_id, status, reasons,
  mode, admitted}`,
- si `enforce` ET `status != "trusted"` -> **HTTP 403** (l'event porte `admitted:false`),
- sinon le run demarre ; la reponse `/runs` porte le `admission` verdict (lisibilite).

### 3. Middleware par action -- `recette/platform/gateway.py`

`PassportAdmissionMiddleware` branchee au point middleware existant (`run_before`, ligne
~144, qui peut deny jamais allow) :
- re-atteste le passeport de l'agent avec le **timestamp capture de l'action** comme `now`
  (deterministe I4 ; attrape l'expiration en cours de run),
- `enforce` + non-trusted -> retourne une raison de veto -> la gateway enregistre
  `ACTION_DENIED` avec `reason = "untrusted_passport: <reasons>"`,
- `observe` -> pas de veto (le run continue, la deny policy normale s'applique).
- La middleware charge le trust keyring + le passeport une fois (cache par agent_id),
  fail-safe non-trusted sur erreur.

### 4. Modele d'evenement (I1)

Nouveau `EventKind.AGENT_ADMISSION` (ajout ADDITIF a l'enum versionnee -- pas de migration
destructive). Payload `{agent_id, status, reasons, mode, admitted}`. Le deni par action
reutilise `ACTION_DENIED` (pas de nouveau kind pour ce chemin).

### 5. Emission des passeports runtime

Reutilise `discoveryprobe-inventory passport issue ... --out data/agent_passports/<id>.json`
(le flag `--out` existe deja -- phase 1). Emettre pour >=1 agent de
`config/inspect_ia_agents.config.json` (trusted), en laisser sans (cas unsigned). Cle de
test du corpus (`corpus/keys/test-authority.trust.json`, key_id `test-authority-1`).

### 6. Recette + lisibilite (legibility-first)

- unittest : `observe` audite sans bloquer (agent sans passeport tourne) ; `enforce` deny
  un agent untrusted/absent (403 a l'endpoint, `ACTION_DENIED` au middleware) ; un agent
  trusted passe les deux gardes ; expiration mid-run attrapee par le middleware (timestamp
  injecte apres exp) ; **replay deterministe** (memes inputs -> meme verdict/events).
- Determinisme I4 : replay test sur le chemin d'admission (pas de `now()` interne).
- Coverage guard : le nouveau chemin entre dans les dimensions si applicable.
- **Console** (lisibilite) : la reponse `/runs` porte `admission` ; le dashboard/onglet
  agents affiche un badge admission (status + mode observe/enforce). R16 : fixture reelle +
  render-and-assert si ca rend une API.
- Runbook `docs/runbooks/passport-admission.md` (fr) + twin EN + aide UI.

## Failure modes (fail-safe, jamais fail-open)

- Oracle/`cryptography` absent -> non-trusted (en `enforce`, deny ; en `observe`, audit).
- Trust keyring absent/illisible -> non-trusted.
- Passeport absent -> `unsigned` -> non-trusted (deny en enforce).
- Erreur d'admission inattendue -> deny (jamais laisser passer sur exception).

## Criteres de done

- En `enforce`, un agent sans passeport (ou untrusted) ne peut ni se lancer (403) ni agir
  (ACTION_DENIED) ; un agent trusted le peut. En `observe`, tout tourne mais chaque
  admission est auditee avec son vrai status.
- Reutilise `attest_passport` (zero divergence avec la phase 1). Deux gardes testees.
- I1 (AGENT_ADMISSION audite), I3 (lien signe avant action), I4 (replay), fail-safe verts.
- Gates completes (unittest, make gates, console-test, smoke live montrant l'admission).
