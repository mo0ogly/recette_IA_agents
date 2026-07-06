# Runbook -- Admission passeport runtime (Phase 2, la garde I3)

Comment la gateway **admet** un agent a s'executer et a agir : un agent n'est
admis QUE si son passeport signe est de confiance -- **deny-by-default en mode
enforce**. C'est la garde runtime de l'invariant I3 (liaison d'identite),
distincte de l'inspection STATIQUE de phase 1 (`docs/runbooks/passport-recette.md`,
qui inspecte des agents NON executes : elle cree l'artefact, l'inspecteur et
l'oracle). La phase 2 fait verifier ce meme passeport, par la gateway, au moment
ou un agent runtime demande a se lancer et a chaque action qu'il tente.

> Concept fondateur (source de verite) :
> `docs/plans/2026-07-05-passport-admission-design.md`. L'admission REUTILISE
> l'oracle d'attestation de phase 1 (`recette/adapters.py::attest_passport`,
> equivalence-teste contre le crate Rust `agent-passport`) : la decision est la
> meme, seul le point d'application change (inspection hors ligne -> garde
> runtime).

## Ce qu'est l'admission

L'admission plie l'attestation dans une **decision de garde** a l'enregistrement
d'un agent runtime. La primitive est
`recette/platform/admission.py::admit_agent(passport, declared, trust, now,
enforce) -> AdmissionVerdict`. Le verdict porte quatre champs :

| Champ | Sens |
|-------|------|
| `status` | statut d'attestation de l'oracle : `trusted` / `untrusted` / `unsigned` / `malformed` |
| `reasons` | tuple immuable des raisons typees (le POURQUOI ; `{"kind": ...}` + `extra`/`field` eventuels) |
| `mode` | `observe` ou `enforce` (le mode sous lequel la decision a ete prise) |
| `admitted` | `(status == "trusted") or (not enforce)` -- un agent de confiance est TOUJOURS admis ; un agent non-trusted n'est admis QU'en observe |

La decision est une fonction pure de ses arguments : meme passeport + meme
keyring + meme horloge => meme verdict (I4, verdict rejouable). Toute erreur de
l'oracle (crypto absente, exception) retombe en fail-safe sur
`status="untrusted"`, `reasons=({"kind": "oracle_error"},)` -- jamais `trusted`.

## Les deux gardes

L'admission s'applique en DEUX points, tous deux dans le Control Plane (I2/I3) :

### 1. Garde pre-lancement -- `POST /runs` (lane_b)

A l'enregistrement d'un run `lane_b` (`recette/api/routers/runs.py`), la gateway :

1. capture l'horloge au bord (`now = capture_timestamp()` -- I4 : un INPUT
   ISO-8601 UTC, lu une seule fois a la frontiere, jamais dans le chemin de
   decision) ;
2. charge le passeport runtime de l'agent
   (`load_agent_passport(agent_id, passport_dir)`) ;
3. calcule `admit_agent(passport, capability_scope, trust, now, enforce)` ;
4. **audite TOUJOURS** un evenement `AGENT_ADMISSION` (I1), meme quand la suite
   sera un refus ;
5. en mode enforce, si `status != "trusted"` -> **HTTP 403** (le refus est deja
   sur le log a l'etape 4) ;
6. en cas d'admission, la reponse porte
   `admission: {status, mode, admitted}`.

### 2. Garde par action -- `PassportAdmissionMiddleware`

`recette/platform/passport_middleware.py` re-atteste le passeport de l'agent
actant sur CHAQUE action soumise a la gateway. Son `before(request)` utilise
`request.timestamp` -- **l'horloge capturee de l'action** (un INPUT, I4) -- comme
`now`. C'est ce qui lui permet d'attraper un passeport qui **expire en cours de
run** : la garde de lancement a vu un passeport valide, mais une action tardive
est evaluee contre son propre timestamp, plus recent, et devient
`untrusted`/`expired`.

- En observe, le middleware ne veto JAMAIS (la garde de lancement a deja audite ;
  le run continue et la policy deny normale s'applique).
- En enforce, un verdict non-trusted renvoie une raison de veto
  (`untrusted_passport: <status> <kinds>`) ; la gateway enregistre alors un
  evenement `ACTION_DENIED` (l'action n'est jamais executee) portant
  `deny_reason` = cette raison.

Le middleware est cable dans la gateway par `recette/api/app.py`, a partir des
memes valeurs `app.state.passport_*` que la garde de lancement -- il partage donc
le MEME toggle enforce, le MEME repertoire de passeports et le MEME keyring.

## Les deux modes

| Mode | Env `INSPECT_IA_AGENTS_PASSPORT_ENFORCE` | Comportement |
|------|-------------------------------------------|--------------|
| **observe** (defaut) | non defini ou toute valeur != `enforce` | audite + avertit, ne bloque JAMAIS. Le verdict est calcule et sur le log ; l'agent tourne meme sans passeport. |
| **enforce** | `enforce` (compare apres `strip().lower()`) | deny-by-default : 403 au lancement + `ACTION_DENIED` par action pour tout agent non-trusted. |

`enforce_from_env()` (admission.py) renvoie `True` ssi l'env vaut `enforce`
(insensible a la casse, espaces retires) ; toute autre valeur -- ou l'absence --
est le defaut fail-safe observe.

### Posture de migration

Deployer d'abord en **observe** : le verdict est calcule et audite pour chaque
agent runtime, sans jamais casser un run. Basculer en **enforce** SEULEMENT quand
chaque agent runtime porte un passeport de confiance (sinon enforce briquerait
tous les agents actuels, dont la demo -- aucun n'a de passeport a l'origine). La
migration douce est un choix de cadrage explicite du design : le deny-by-default
strict d'emblee a ete rejete.

## Ou vit un passeport runtime

- **Passeport runtime** : `data/agent_passports/<agent_id>.json`. Le repertoire
  est **gitignore** (`.gitignore` : `data/agent_passports/`) -- seules les
  fixtures de test sous `tests/fixtures/agent_passports/` sont versionnees
  (`trusted-agent.json`, `expired-agent.json`). Surcharge du repertoire par l'env
  `INSPECT_IA_AGENTS_PASSPORT_DIR` (defaut `data/agent_passports`).
- **Keyring de confiance** : `corpus/keys/test-authority.trust.json` (l'objet
  `{ "<key_id>": "<pubkey_hex>" }` charge dans le `TrustStore`). Surcharge par
  l'env `INSPECT_IA_AGENTS_PASSPORT_TRUST` ; ce defaut fait admettre les
  passeports du corpus sans configuration.

### Emettre un passeport runtime

Le passeport signe est produit par la sous-commande `passport issue` du binaire
`discoveryprobe-inventory` (detail complet + graine de signature :
`docs/runbooks/passport-recette.md`). Ecrire la sortie a l'emplacement runtime
via `--out` :

```
discoveryprobe-inventory passport issue <tree> --agent-id <id> --tenant <t> --scope <a,b,c> --delegation <x,human:alice> --exp <rfc3339> --key-id <k> [--spiffe-id <spiffe://...>] --out data/agent_passports/<id>.json
```

## L'audit (I1)

Chaque lancement `lane_b` ajoute (append-only, immuable) un evenement
`AGENT_ADMISSION` (`EventKind.AGENT_ADMISSION = "agent_admission"`) portant
`{agent_id, status, reasons, mode, admitted}`. **Meme un 403 est audite
d'abord** : le refus lui-meme est sur le log avant que la reponse HTTP ne parte.

Un refus par action est un evenement `ACTION_DENIED`
(`EventKind.ACTION_DENIED = "action_denied"`) dont le `deny_reason` commence par
`untrusted_passport` (suivi du statut et des `kind` des raisons). L'action n'est
jamais executee.

## La console

- La reponse `POST /runs` porte le bloc `admission`. Le dashboard rend un
  **badge d'admission** (`console/src/pages/dashboard/AdmissionBadge.tsx`) keye
  sur `status` (les quatre etats `trusted` / `untrusted` / `unsigned` /
  `malformed`), affichant aussi le `mode` (observe/enforce) et `admitted`. Un run
  observe mais non-trusted lit ainsi comme un WARN (le run a eu lieu, le
  passeport n'est pas de confiance).
- Un refus enforce (403) ne passe pas par le badge : il n'y a pas de run. Le
  refus est surface au site d'appel (banniere d'erreur du dashboard) sous la
  forme lisible `Admission refusee (enforce): <detail>` -- le POURQUOI du refus,
  pas une enveloppe `403` brute.

## Modes fail-safe (jamais fail-open)

En cas de doute, l'admission se ferme (non-trusted -> deny en enforce), jamais
`trusted` :

- **Oracle/crypto absent** -> `oracle_error` -> non-trusted.
- **Keyring de confiance absent** -> passeport non verifiable -> non-trusted
  (`unknown_key_id`).
- **Passeport absent** -> `unsigned` -> non-trusted.
- **Erreur** (exception dans le chemin) -> `untrusted`, admission deny en
  enforce.

Aucun de ces chemins n'admet un agent en enforce ; en observe ils sont audites
et le run continue (le WARN est visible).

## Determinisme (I4)

- La garde de lancement capture l'horloge une seule fois au bord
  (`capture_timestamp()`, un INPUT) ; la decision est une fonction pure de
  `(passport, declared, trust, now, enforce)`.
- Le middleware par action utilise l'horloge CAPTUREE de l'action
  (`request.timestamp`), jamais `datetime.now()`. Deux rejeux du meme flux
  d'evenements contre le meme keyring produisent le meme verdict, byte-stable.

## Notes

- I3 : l'admission lie l'execution d'un agent a une identite attestee (chaine de
  mandat jusqu'a un humain, portee par le passeport signe).
- I2 : l'admission est dans le Control Plane -- aucun agent ne s'execute ni
  n'agit sans passer par la garde.
- R8 : les raisons de veto ne listent que des `kind` de raison, jamais de
  materiau de cle ou de signature.
- Le passeport est fige entre delivrance et expiration : une correction est un
  nouveau passeport, jamais une mutation (coherent avec I1).
