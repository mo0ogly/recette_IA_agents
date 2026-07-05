# Agent Passport Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (ou
> subagent-driven-development) pour implementer ce plan tache par tache.
> Design valide : `docs/plans/2026-07-05-agent-passport-design.md`.

**Goal:** Un crate Rust EXPORTABLE `agent-passport` (lib pure : emission + verification
Ed25519 d'un passeport d'agent signe, Contrat 3 de la spec pare-feu), branche dans le
scanner `discoveryprobe-inventory` comme un AXE `attestation` distinct
(trusted/untrusted/unsigned/absent), avec corpus signe, oracle Python equivalence-teste,
console et runbook.

**Architecture:** Le credential signe est un artefact SEPARE
`.inspect_ia_agents/passport.json` (le manifest reste un artefact distinct ; l'etat
`passport.kind = present|absent|invalid` du manifest est INCHANGE). Le credential porte
son PROPRE axe `attestation` sur `AgentRecord`. La verite crypto vit dans un crate pur
sans I/O (`agent-passport` : ni fichier, ni env, ni horloge -- tout en input) pour etre
embarquable dans un environnement d'agents reels ; les consommateurs
(`discoveryprobe-inventory`, plus tard la gateway) apportent l'I/O.

**Tech Stack:** Rust (nouveau crate workspace), `ed25519-dalek` 2.2, `thiserror` 2.0,
`serde`/`serde_json` 1 (versions verifiees crates.io 2026-07-05, R17). Oracle : Python
`cryptography` (lazy, extra `[bundle]`). Console React/TS. Zero mock, zero hardcoding.

**RAFFINEMENT vs design doc :** le design disait "passport_status gagne untrusted" ; on
retient l'axe SEPARE `attestation` (valide operateur 2026-07-05) pour ne pas conflater
"manifest JSON valide" et "credential crypto de confiance". Le champ ground-truth
s'appelle `attestation_status`, pas une extension de `passport_status`.

**Regles projet (CHAQUE tache) :** commits Conventional SANS "Co-Authored-By: Claude"
(R1) ; zero emoji (R10) ; commentaires/doc source en anglais (R12) ; Rust :
`cargo fmt` + `cargo clippy --all-targets -- -D warnings`, ZERO `unwrap`/`expect` hors
tests (R7), doc-comments `///` sur toute l'API publique + `#![deny(missing_docs)]` sur
la lib, pas de `SystemTime::now()`/`rand` dans un chemin de verdict (I4). Python :
unittest stdlib, determinisme I4, coverage guard. Cle jamais en dur (R8). Fail-safe
jamais fail-open.

---

## Phase 1 -- Le crate `agent-passport` (lib pure, exportable)

### Task 1: Scaffold du crate + types Passport/Claims (parse only)

**Files:**
- Create: `discoveryprobe/agent-passport/Cargo.toml`
- Create: `discoveryprobe/agent-passport/src/lib.rs`
- Modify: `discoveryprobe/Cargo.toml` (ajouter `"agent-passport"` aux `members`)
- Test: `discoveryprobe/agent-passport/src/lib.rs` (mod tests inline) puis
  `discoveryprobe/agent-passport/tests/` a partir de Task 3

**Cargo.toml** : `name = "agent-passport"`, `edition = "2021"`, license MIT OR
Apache-2.0, description exportable. Deps : `serde = { version = "1", features =
["derive"] }`, `serde_json = "1"`, `ed25519-dalek = "2.2"`, `thiserror = "2"`. AUCUNE
dep vers `discoveryprobe-*`. `[lib]` avec `#![deny(missing_docs)]` en tete de lib.rs.

**Step 1: Failing test** -- `Passport::from_json` parse le tuple Contrat 3
(`id, tenant, delegation[], scope[], exp, spiffe_id?, signature, key_id`) depuis des
bytes ; un JSON manquant un champ requis -> `PassportError::Malformed`. Champs inconnus
rejetes (`#[serde(deny_unknown_fields)]` -- attestation figee).

**Step 2:** `cargo test -p agent-passport` -> FAIL (types absents).

**Step 3:** Definir `struct Passport` (serde, `deny_unknown_fields`), `struct Claims`
(le tuple SANS signature/key_id -- ce qui est signe), `enum PassportError` (thiserror :
`Malformed(String)`, `Json(#[from] serde_json::Error)`), `Passport::from_json(&[u8])`.
`exp` typé comme string RFC3339 conserve tel quel a ce stade (comparaison en Task 4).

**Step 4:** PASS + `cargo clippy -p agent-passport --all-targets -- -D warnings` + `cargo fmt --check`.

**Step 5:** Commit `feat(passport): agent-passport crate scaffold + Contrat 3 parse`.

### Task 2: Canonicalisation + issue (signature)

**Files:**
- Modify: `discoveryprobe/agent-passport/src/lib.rs` (ou `src/canonical.rs` + `src/issue.rs`)
- Test: inline

**Step 1: Failing tests**
- `canonical_bytes(&Claims) -> Vec<u8>` : serialisation JSON avec cles TRIEES,
  deterministe (I4) -- deux appels sur les memes claims = bytes identiques ; l'ordre
  des cles d'entree n'affecte pas la sortie. (Implementer via `serde_json::Value` ->
  tri recursif, ou `BTreeMap`. Documenter le choix.)
- `issue(claims: Claims, key: &SigningKey) -> Result<Passport, PassportError>` : signe
  `canonical_bytes(claims)` en Ed25519, retourne un `Passport` avec `signature` (hex) +
  `key_id` derive de... NON : `key_id` est un INPUT (fourni dans les claims ou un param
  `key_id: &str`) -- l'autorite choisit son key_id, la lib ne l'invente pas. Signature =
  hex minuscule des 64 bytes.
- Round-trip : `issue` puis `verify` (Task 4) avec la cle publique correspondante ->
  signature valide. A ce stade, tester juste que la signature verifie via
  `VerifyingKey::verify` directement.

**Step 2:** FAIL. **Step 3:** Implementer (vraie cle `SigningKey` de `ed25519-dalek` en
test via `SigningKey::from_bytes(&[u8;32])` avec un seed de test explicite -- pas de
`rand` dans la lib ; si generation aleatoire necessaire en test, contenue au test).
**Step 4:** PASS + clippy + fmt. **Step 5:** Commit
`feat(passport): canonical signing bytes + Ed25519 issue`.

### Task 3: TrustStore + verify (Verdict typee) -- coeur fail-safe

**Files:**
- Modify: `discoveryprobe/agent-passport/src/lib.rs` (+ `src/verify.rs`, `src/trust.rs`)
- Test: `discoveryprobe/agent-passport/tests/verify.rs` (integration, vraies cles)

**Step 1: Failing tests** (chaque verdict, un test) :
- `TrustStore` = map `key_id -> VerifyingKey`, construit par l'appelant
  (`TrustStore::from_entries(Vec<(String, VerifyingKey)>)`). Une pubkey se parse depuis
  hex (`TrustStore::add_hex(key_id, &str) -> Result<..>`).
- `Timestamp` = wrapper sur un instant RFC3339 fourni en INPUT
  (`Timestamp::parse(&str) -> Result<Timestamp, PassportError>`). JAMAIS
  `SystemTime::now()` dans la lib.
- `verify(passport, trust, now, declared: Option<&DeclaredScope>) -> Verdict` :
  - `Verdict::Trusted` quand signature ok + non expire + delegation non vide terminant
    sur un humain + (si `declared`) scope >= actions declarees + key_id connu.
  - `Verdict::Untrusted { reasons: Vec<UntrustReason> }` sinon, avec TOUTES les raisons
    applicables cumulees (pas seulement la premiere) : `BadSignature`, `Expired`,
    `EmptyDelegation`, `NoHumanPrincipal`, `ScopeOverreach { extra: Vec<String> }`,
    `UnknownKeyId`, `MalformedField(String)`.
  - `DeclaredScope` = les familles d'actions que le manifest declare (input fourni par
    le consommateur ; la lib ne lit pas le manifest). `ScopeOverreach` = actions
    declarees HORS du scope signe.
  - "termine sur un humain" : convention documentee -- le dernier element de
    `delegation` matche un pattern principal humain (ex : contient `@`, ou prefixe
    `human:`). Choisir UNE regle explicite et la documenter ; la rendre testable.
- Fail-safe : `key_id` absent du trust -> `Untrusted{UnknownKeyId}` (jamais un panic,
  jamais Trusted). Signature hex malformee -> `Untrusted{BadSignature}` (pas d'erreur
  qui remonte : verify ne rend QUE un Verdict, il ne faillit pas).

**Step 2:** FAIL. **Step 3:** Implementer. `verify` retourne un `Verdict`, jamais un
`Result` (un passeport pourri = Untrusted, pas une erreur -- c'est le point fail-safe).
Le PARSE (`from_json`) peut faillir ; le VERIFY ne faillit jamais.
**Step 4:** PASS (tous les verdicts) + clippy -D warnings + fmt.
**Step 5:** Commit `feat(passport): TrustStore + fail-safe verify with typed Verdict`.

### Task 4: Serde du Verdict + replay determinisme

**Files:**
- Modify: `discoveryprobe/agent-passport/src/verify.rs`
- Test: `discoveryprobe/agent-passport/tests/verify.rs`

**Step 1: Failing tests**
- `Verdict` et `UntrustReason` serialisent en JSON tagge (`#[serde(tag="kind")]` sur le
  verdict : `{"kind":"trusted"}` / `{"kind":"untrusted","reasons":[...]}`) -- le
  consommateur Python/console dispatche sur `kind`, jamais par forme.
- Replay I4 : meme passeport + meme trust + meme `now` -> meme JSON de verdict byte pour
  byte, sur 2 appels. Raisons TRIEES (ordre stable) pour la stabilite.

**Step 2:** FAIL. **Step 3:** Implementer serde + tri des raisons.
**Step 4:** PASS. **Step 5:** Commit `feat(passport): kind-tagged Verdict serde + replay-stable ordering`.

## Phase 2 -- Branchement dans discoveryprobe-inventory (couche I/O)

### Task 5: Sous-commande `passport issue` (I/O : env, fichier)

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/Cargo.toml` (dep
  `agent-passport = { path = "../agent-passport" }`)
- Modify: `discoveryprobe/discoveryprobe-inventory/src/main.rs` (nouvelle sous-commande)
- Test: `discoveryprobe/discoveryprobe-inventory/tests/cli.rs` (etendre)

**Step 1: Failing test** -- `discoveryprobe-inventory passport issue <tree>
--agent-id X --tenant T --scope a,b --delegation human:alice --exp <rfc3339>
--key-id k1` lit le seed via env `INSPECT_IA_AGENTS_PASSPORT_KEY` (hex 32 bytes, R8),
signe, ecrit `<tree>/.inspect_ia_agents/passport.json`. Sans l'env -> erreur explicite
code 2, AUCUN fichier ecrit (jamais un passeport non signe). Le fichier ecrit reparse et
verifie Trusted avec la pubkey correspondante.

**Step 2:** FAIL. **Step 3:** Implementer : parse args, lire env (c'est ICI, hors lib),
construire `Claims`, `issue`, serialiser, ecrire. Erreurs mappees sur les codes de
sortie existants (0/2/1 -- voir `CliError` dans main.rs).
**Step 4:** PASS + clippy + fmt. **Step 5:** Commit
`feat(inventory): passport issue subcommand (env key, writes signed passport.json)`.

### Task 6: Sous-commande `passport verify` (I/O : trust file, --now)

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/main.rs`
- Test: `discoveryprobe/discoveryprobe-inventory/tests/cli.rs`

**Step 1: Failing test** -- `passport verify <tree> --trust <pubkeys.json> --now
<rfc3339>` charge le trousseau (fichier `{key_id: pubkey_hex}`) + l'horloge en INPUT,
lit `<tree>/.inspect_ia_agents/passport.json`, imprime le verdict JSON tagge sur stdout.
Passeport absent -> verdict `{"kind":"untrusted","reasons":[{"kind":"absent"}]}` (ou un
statut d'attestation `absent` dedie -- voir Task 7 pour l'etat d'inventaire). `--now`
apres `exp` -> `Expired`. Trust vide -> `UnknownKeyId`. Determinisme : deux runs =
sortie identique.

**Step 2:** FAIL. **Step 3:** Implementer (charge trust, `Timestamp::parse(--now)`,
lit fichier, `verify`, imprime). **Step 4:** PASS + clippy + fmt.
**Step 5:** Commit `feat(inventory): passport verify subcommand (trust file + injected clock)`.

### Task 7: Axe `attestation` sur AgentRecord + scan

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/model.rs` (nouveau champ
  `attestation` sur `AgentRecord`), `src/scan.rs` (detecter `passport.json`),
  `src/correlate.rs` (peupler l'attestation)
- Test: `discoveryprobe/discoveryprobe-inventory/tests/` (nouveau ou etendre)

**Step 1: Failing tests** -- `AgentInventory` sortant : chaque `AgentRecord` porte
`attestation` = enum kind-tagge :
- `unsigned` : pas de `passport.json` dans l'arbre (le manifest peut exister -- c'est
  l'axe SEPARE ; `passport.kind` du manifest reste ce qu'il est).
- `trusted` / `untrusted{reasons}` : `passport.json` present, verifie via le crate.
- CAVEAT : le scan est STATIQUE et n'a ni trousseau ni horloge cablés par defaut. Deux
  options, choisir et documenter : (a) `scan` ne fait PAS la crypto (rend `unsigned` vs
  `present-unverified`) et la verification vit dans `passport verify` ; (b) `scan`
  accepte `--trust` + `--now` optionnels et, fournis, rend trusted/untrusted. RETENU :
  (b) -- `scan` gagne `--trust <file>` + `--now <rfc3339>` optionnels ; ABSENTS -> le
  passeport present reste `untrusted{UnknownKeyId}` (fail-safe : sans trousseau on ne
  fait JAMAIS confiance) et `passport.json` absent -> `unsigned`. Documenter que
  l'inventaire live cable le trousseau du corpus.
- `InventorySummary` gagne des compteurs `attested_trusted`, `attested_untrusted`,
  `unsigned`.

**Step 2:** FAIL. **Step 3:** Implementer. Le `now` du scan : input CLI (I4), jamais
`SystemTime::now()`. **Step 4:** PASS + clippy + fmt + `cargo test` workspace.
**Step 5:** Commit `feat(inventory): attestation axis (trusted/untrusted/unsigned) from signed passport.json`.

## Phase 3 -- Schema, corpus, trousseau de test

### Task 8: Schema Contrat 3 + ground-truth attestation_status

**Files:**
- Create: `corpus/schemas/agent-passport.schema.json`
- Modify: `corpus/schemas/discovery-ground-truth.schema.json` (ajouter optionnel
  `attestation_status` enum `["trusted","untrusted","unsigned","absent"]`)
- Test: `tests/test_schemas_valid.py` ou l'equivalent (grep le test qui valide les
  schemas ; suivre son style)

**Step 1:** Ecrire le schema draft 2020-12 (champs Task 1, `additionalProperties:
false`). **Step 2:** Test : un passeport exemple valide, un passeport sans `signature`
invalide. **Step 3-4:** PASS. **Step 5:** Commit
`feat(corpus): agent-passport schema + attestation_status ground-truth field`.

### Task 9: Trousseau de test + passeports valides pour les sujets existants

**Files:**
- Create: `corpus/keys/test-authority.pub` (pubkey hex, committee -- PUBLIQUE)
- Create: `corpus/keys/README.md` (explique : cle de TEST publiquement connue, jamais
  reelle ; comment regenerer)
- Modify: `.env.example` (ajouter `INSPECT_IA_AGENTS_PASSPORT_KEY=<seed hex de test>`
  documente comme cle de test connue, R8 -- le vrai `.env` reste gitignore)
- Create: `corpus/repos/<subject>/repo/.inspect_ia_agents/passport.json` pour les sujets
  positifs existants (gh-pr-bot, gh-readonly-reporter, ...) via `passport issue`
- Modify: les `discovery-ground-truth.json` de ces sujets (`attestation_status:
  "trusted"`)
- Test: le coverage guard / la recette discovery reste verte

**Step 1:** Generer le seed de test (documenter la commande openssl/rust qui l'a
produit) ; deriver + committer la pubkey. **Step 2:** Emettre les passeports via le
binaire (build d'abord : `./recette.sh discovery-build`). **Step 3:** `passport verify`
sur chacun avec le trousseau -> Trusted. **Step 4:** ground-truth mis a jour.
**Step 5:** Commit `feat(corpus): test authority keyring + signed passports for existing subjects`.

### Task 10: Trois sujets negatifs mono-axe

**Files:**
- Create: `corpus/repos/gh-passport-expired/` (passeport signe valide mais `exp` passee)
- Create: `corpus/repos/gh-passport-tampered/` (champ modifie apres signature)
- Create: `corpus/repos/gh-passport-scope-overreach/` (scope signe < capabilities du
  manifest)
- Modify: `corpus/agent_links.json` (enregistrer les sujets, twin-less si besoin --
  suivre le pattern des sujets shadow/invalid ajoutes precedemment)
- Test: coverage guard + `test_each_negative_breaks_exactly_one_dimension` equivalent
  cote discovery ; equivalence oracle (Task 11)

**Chaque sujet** : un vrai repo minimal (README + `.inspect_ia_agents/{manifest.json,
passport.json}`) ; ground-truth `attestation_status: "untrusted"` + la raison attendue.
MONO-AXE : les 3 autres axes (manifest present/valide, etc.) restent conformes.

**Step 5:** Commit `feat(corpus): three mono-axis untrusted-passport discovery subjects`.

## Phase 4 -- Oracle Python + equivalence

### Task 11: Oracle attestation dans ReferenceSourceScanAdapter + equivalence

**Files:**
- Modify: `recette/adapters.py` (`DiscoveryRisk.attestation_status` +
  `ReferenceSourceScanAdapter._analyze` lit `passport.json`, verifie via `cryptography`
  lazy-import)
- Modify: `pyproject.toml` si `cryptography` n'est pas deja dans `[bundle]` (verifier ;
  `receipt_export.py` l'utilise deja -> probablement present)
- Test: `tests/test_passport_equivalence.py` (nouveau)

**Step 1: Failing tests**
- `_analyze` peuple `attestation_status` par sujet : trusted/untrusted/unsigned depuis
  `passport.json` + le trousseau `corpus/keys/test-authority.pub` + une horloge FIXE
  injectee (I4 : pas de `datetime.now()` dans le verdict -- passer un `now` de reference,
  ex un `LogicalClock` ou un param). `cryptography` absent (pas d'extra) -> skip
  explicite documente, jamais un faux trusted.
- **Test d'equivalence** : pour CHAQUE sujet du corpus, le `passport verify` Rust (via
  subprocess sur le binaire build, ou une fixture de verdict committee) et l'oracle
  Python rendent le MEME `attestation_status` + memes raisons. Si le binaire n'est pas
  build, skip explicite (comme le test live inventory existant).

**Step 2:** FAIL. **Step 3:** Implementer l'oracle (mirror exact de la regle Rust :
signature Ed25519 sur les memes canonical bytes, exp vs now injecte, delegation humaine,
scope >= declare). **Step 4:** PASS + `make gates` (ruff/mypy/bandit) + coverage guard.
**Step 5:** Commit `feat(recette): python attestation oracle + Rust/Python equivalence test`.

## Phase 5 -- Console + docs

### Task 12: Badge attestation dans InventoryPanel (R16)

**Files:**
- Modify: `console/src/pages/probe/InventoryPanel.tsx` (badge attestation a cote du
  badge passport manifest), `console/src/api/client.ts` +
  `console/src/types/*` (type `attestation` sur l'inventaire), `probe.css` (tokens)
- Modify/Create: `console/src/pages/probe/__fixtures__/*.fixture.json` (payload REEL avec
  le champ attestation : capturer via l'endpoint apres build, R16)
- Test: `console/src/pages/probe/InventoryPanel.test.tsx` (render-and-assert : les 4
  etats trusted/untrusted/unsigned/absent + les raisons untrusted)

TDD vitest : badge keye sur `attestation.kind` seul (jamais deduit d'autre chose) ;
couvrir les 4 variantes + l'affichage des raisons. **Step 5:** Commit
`feat(console): attestation badge on inventory panel (R16 fixtures + 4 states)`.

### Task 13: Endpoint /probe/inventory expose l'attestation + smoke

**Files:**
- Modify: `recette/api/routers/probe.py` (le live scan passe `--trust
  corpus/keys/test-authority.pub` + un `--now` de reference ; l'attestation remonte dans
  la reponse), `recette/inventory_bridge.py` (parse le champ attestation)
- Modify: `scripts/smoke_console.py` (assertion : le panneau inventory montre au moins un
  badge attestation trusted ET un untrusted sur le corpus)
- Test: `tests/test_api_probe_inventory.py` (etendre : attestation dans la reponse)

TDD Python + smoke live. **Step 5:** Commit
`feat(api): inventory endpoint surfaces attestation; smoke asserts trusted+untrusted badges`.

### Task 14: Runbook + docs fr/en

**Files:**
- Create: `docs/runbooks/passport-recette.md` (emission, trousseau, verdicts, mapping
  Contrat 3, caveat crypto en Rust vs oracle Python, l'axe attestation vs manifest)
- Modify: `docs/runbooks/inventory-recette.md` (mentionner le nouvel axe attestation)
- Docs-site fr+en si la page inventory y decrit les etats

**Step 5:** Commit `docs(passport): passport-recette runbook + inventory attestation axis (fr/en)`.

## Phase 6 -- Gates finales

### Task 15: Toutes les gates + preuve live

**Steps:**
1. `cargo test` workspace (`cd discoveryprobe && cargo test`) + `cargo clippy
   --all-targets -- -D warnings` + `cargo fmt --check` -- crate agent-passport ET
   inventory verts.
2. `cargo test -p agent-passport` SEUL (prouve l'exportabilite : le crate se teste isole).
3. `./recette.sh discovery-build` (le binaire compile avec la nouvelle dep).
4. `python3 -m unittest discover -s tests` + `make gates` + coverage guard verts.
5. `./recette.sh console-build` + `console-test` verts.
6. `./recette.sh smoke --console` : le panneau inventory montre les badges attestation
   live (preuve R14 : flux + assertion DOM + screenshot).
7. Verifier R13 : chaque commande de runbook existe (grep source).

---

## Ordre & dependances

1->2->3->4 (crate, sequentiel) ; 5->6->7 (inventory, apres 4) ; 8->9->10 (schema+corpus,
apres 7 pour emettre via le binaire) ; 11 (oracle, apres 10) ; 12->13 (console/api,
apres 11) ; 14 (docs) ; 15 (gates).

## Ce qui ne change PAS (garde-fous)

- L'axe manifest `passport.kind = present|absent|invalid` est INCHANGE (dimension
  distincte). L'attestation est un NOUVEL axe orthogonal.
- La lib `agent-passport` ne fait AUCUN I/O (ni fichier, ni env, ni horloge) -- exportable.
- `verify` ne faillit jamais (rend un Verdict) ; seul `from_json` peut faillir.
- Determinisme I4 : horloge et trousseau en INPUT partout ; verdict byte-stable.
- Aucune cle reelle committee ; le seed de test est publiquement documente comme tel (R8).
