# Design -- agent-passport : passeport d'agent signe (Contrat 3) + inspection statique

Date : 2026-07-05
Statut : VALIDE (brainstorm operateur)
Source : `/home/fpizzi/Downloads/spec_mise_en_oeuvre_pare_feu_agents.docx` (spec pare-feu
de gouvernance des agents, vocabulaire NIST SP 800-207) -- Contrat 3 "le passeport".
Invariants concernes : I3 (liaison d'identite), I4 (verdict deterministe, horloge en
input), R8 (cle jamais en dur), fail-safe (jamais fail-open).

## Contexte et posture (decisions de cadrage)

- La spec pare-feu mappe presque 1:1 sur l'architecture inspect_ia_agents (PEP = gateway +
  proxy I5, PDP = policy engine deny-by-default, plan d'audit I1, risk engine = plan
  d'enrichissement). Posture retenue : **les deux, en phases**.
  - **Phase 1 (CE design)** : recette du pare-feu + inspection passeport statique des
    agents NON executes. Les agents actuels n'ont AUCUN passeport : la phase 1 cree
    l'artefact (emission), le corpus (positifs + negatifs), l'inspecteur, l'oracle.
  - **Phase 2 (esquissee, hors scope)** : la gateway verifie le passeport a
    l'enregistrement d'un agent runtime (I3 renforce), `passport_ref` dans l'enveloppe
    d'action, deny-by-default si untrusted/absent. Reutilise le MEME crate.
- **Le code est en Rust** (langage de la plateforme et du discovery tool).
- **Artefact separe** : `.inspect_ia_agents/passport.json` a cote du manifest. Manifest =
  ce que l'agent DECLARE ; passeport = ce que l'AUTORITE atteste (tuple signe, FIGE entre
  delivrance et expiration, conformement a la spec). Rejete : bloc dans le manifest
  (melange declaration/attestation), JWS detache sur le manifest entier (atteste trop).
- **Module exportable** : le crate doit etre embarquable dans un autre environnement
  d'agents reels -- codage strict (rust-conventions.md + skill rust-best-practices),
  zero mock, zero hardcoding.

## 1. Schema (contrat de donnees)

`corpus/schemas/agent-passport.schema.json` -- JSON Schema draft 2020-12, Contrat 3 :

| Champ | Type | Sens |
|-------|------|------|
| `id` | string | identifiant d'agent |
| `tenant` | string | tenant proprietaire |
| `delegation` | array[string] | chaine de mandat, remonte jusqu'a un HUMAIN responsable |
| `scope` | array[string] | familles d'actions permises |
| `exp` | string date-time | expiration (RFC 3339 UTC) |
| `spiffe_id` | string (optionnel) | `^spiffe://` |
| `signature` | string | Ed25519 hex sur le hash canonique du tuple |
| `key_id` | string | version de cle de l'autorite (verif post-rotation) |

`additionalProperties: false` -- un passeport est une attestation figee, jamais un
porteur d'attributs dynamiques.

## 2. Crate Rust `agent-passport` (lib-first, exportable)

Nouveau crate du workspace : `discoveryprobe/agent-passport/`. Nom NEUTRE, AUCUNE
dependance aux crates `discoveryprobe-*`. Deps minimales : `serde`, `serde_json`,
`ed25519-dalek` v2, `thiserror` (versions courantes verifiees sur crates.io au moment
du plan -- R17/R13).

**Lib pure -- I/O aux frontieres.** La lib ne touche NI fichier, NI env, NI horloge :

```rust
Passport::from_json(&[u8]) -> Result<Passport, PassportError>
issue(claims: Claims, key: &SigningKey) -> Result<Passport, PassportError>
verify(passport: &Passport, trust: &TrustStore, now: Timestamp,
       declared: Option<&DeclaredScope>) -> Verdict
```

- Canonicalisation JSON triee byte-stable pour le hash signe (I4 : deux emissions des
  memes claims avec la meme cle = memes bytes signes).
- `Timestamp` = INPUT capture par l'appelant -- jamais `SystemTime::now()` dans la lib
  (I4). Comparaison d'expiration sur timestamps UTC normalises.
- `TrustStore` = struct injectee (`key_id -> VerifyingKey`), chargee par l'appelant.
- `Verdict` = enum typee : `Trusted` | `Untrusted { reasons: Vec<UntrustReason> }` avec
  raisons typees : `BadSignature`, `Expired`, `EmptyDelegation`,
  `NoHumanPrincipal`, `ScopeOverreach { extra }`, `UnknownKeyId`, `MalformedField`.
  Jamais un booleen nu.
- Verifications de `verify` : signature Ed25519 sur le hash canonique ; `exp` non
  depasse vs `now` ; `delegation` non vide et terminant sur un principal humain ;
  coherence `scope` >= actions declarees du manifest (quand `declared` fourni) ;
  `key_id` present dans le trousseau.
- Qualite (rust-conventions.md) : erreurs `thiserror`, ZERO `unwrap`/`expect` hors
  tests, doc-comments `///` sur toute l'API publique, `#![deny(missing_docs)]`,
  `cargo fmt` + `cargo clippy --all-targets -- -D warnings` en gate, zero mock --
  les tests utilisent de vraies cles generees en test + fixtures corpus reelles.

**Failure modes (fail-safe, jamais fail-open)** : trousseau vide ou `key_id` inconnu ->
`Untrusted { UnknownKeyId }` ; champ malforme -> `Untrusted { MalformedField }` ou
`PassportError` au parse ; cle absente a l'EMISSION -> erreur explicite, jamais un
passeport non signe.

## 3. Consommateurs (couche I/O, hors lib)

- **`discoveryprobe-inventory`** depend du crate et ajoute :
  - `passport issue <tree> --agent-id --tenant --scope ... [--exp] ` -- lit la cle seed
    via env `INSPECT_IA_AGENTS_PASSPORT_KEY` (hex 32, R8) + `--key-id`, ecrit
    `.inspect_ia_agents/passport.json`.
  - `passport verify <tree> --trust <pubkeys-file> --now <rfc3339>` -- charge le
    trousseau + l'horloge en INPUT, imprime le verdict JSON.
  - `scan` : chaque agent gagne un 4e etat `passport.kind = "untrusted"` (present mais
    signature ko / expire / delegation cassee / scope incoherent -- avec `reasons`),
    a cote de `present` / `absent` / `invalid` (invalid = echec schema, untrusted =
    echec crypto/semantique ; les deux etats restent distincts).
- **Phase 2** : la gateway Axum reutilisera le meme crate (but de l'exportabilite).

## 4. Corpus -- les agents actuels recoivent leur passeport

- Emission de passeports VALIDES pour les sujets `corpus/repos/*` existants.
- Cle de TEST : seed privee documentee dans `.env.example` comme cle de test PUBLIQUEMENT
  connue (jamais une cle reelle) ; cle publique committee `corpus/keys/test-authority.pub`
  (le trousseau du corpus). Les passeports commites restent verifiables par quiconque.
- Sujets negatifs MONO-AXE (R20), 1 axe casse chacun :
  - `gh-passport-expired` -- `exp` passee, signature valide.
  - `gh-passport-tampered` -- champ modifie apres signature (signature ko).
  - `gh-passport-scope-overreach` -- scope signe < capabilities declarees du manifest.
  - `gh-shadow-agent` (existant) reste le cas `absent`.
- `corpus/schemas/discovery-ground-truth.schema.json` : `passport_status` gagne
  `untrusted`.

## 5. Recette (oracle + harnais)

- Oracle Python `ReferenceSourceScanAdapter` : calcule le MEME statut. Crypto via
  lazy-import `cryptography` (extra `[bundle]`, pattern `recette/receipt_export.py`) ;
  sans l'extra, skip EXPLICITE documente -- jamais un faux `present`.
- **Test d'equivalence** : `passport verify` (Rust) et l'oracle Python rendent le meme
  statut sur CHAQUE sujet du corpus -- le corpus est la gate d'equivalence des deux
  implementations.
- Replay test I4 : meme tree + meme `--now` -> JSON byte-identique (Rust) ; oracle pur
  cote Python.
- Coverage guard : les nouveaux sujets/statuts entrent dans les dimensions du guard
  (un trou de recette = test rouge).

## 6. Console + docs

- Panneau `/probe` inventory : badge `UNTRUSTED` (tokens ambre/rouge existants) +
  raisons ; fixtures payload reelles + render-and-assert (R16).
- Runbook `docs/runbooks/passport-recette.md` (emission, trousseau, verdicts, mapping
  Contrat 3) + aide UI ; docs fr+en.

## Gains / criteres de done

- Un tiers peut, sans executer un agent, savoir si son passeport est present, valide,
  DIGNE DE CONFIANCE (signature/exp/delegation/scope) -- et pourquoi pas.
- Le crate `agent-passport` se compile et se teste seul (`cargo test -p agent-passport`),
  embarquable dans l'environnement d'agents reels sans modification.
- Corpus : 1 positif signe par sujet existant + 3 negatifs mono-axe ; equivalence
  Rust/Python verte ; gates completes (cargo clippy -D warnings, unittest, coverage
  guard, console-test, smoke).
