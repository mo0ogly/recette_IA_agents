---
allowed-tools: Read, Glob, Grep, Bash
argument-hint: [chemin/fichier.rs ou chemin/crate/]
description: Valide la qualite, la securite et la conformite du code Rust inspect_ia_agents (clippy + cargo-audit + cargo-deny + cargo-geiger + conventions backend + OWASP + invariants I1-I6 + Contract Gate R17)
---

# Rust Recette -- Validation Backend Rust inspect_ia_agents (Railgun)

Tu es un auditeur Rust specialise dans la plateforme inspect_ia_agents (gateway Axum, event bus NATS,
approvals Temporal, event store). Effectue une analyse exhaustive du fichier ou repertoire
fourni : `$ARGUMENTS`

Si aucun argument n'est fourni, analyse le fichier dont il est question dans la conversation.

C'est l'equivalent Rust de `/go-recette` (qui orchestrait gosec + govulncheck). Mapping outils :

| Go (/go-recette) | Rust (ici) | Role |
|------------------|------------|------|
| `go vet` | `cargo clippy -D warnings` | correction statique + lints |
| `gofmt` | `cargo fmt --check` | formatage |
| `gosec` | `cargo clippy` (lints securite) + `cargo geiger` (surface unsafe) | SAST |
| `govulncheck` | `cargo audit` (RustSec advisory DB) | deps vulnerables |
| (n/a) | `cargo deny check` | supply-chain (advisories + bans + licenses + sources) |
| `go test` | `cargo test` / `cargo nextest run` | tests |

---

## Outils prerequis

| Outil | Installation | Role |
|-------|--------------|------|
| cargo / rustc | `scripts/install_rust_audit.sh` | toolchain |
| cargo clippy | `rustup component add clippy` | lints (500+) |
| rustfmt | `rustup component add rustfmt` | format |
| cargo-audit | `cargo install cargo-audit` | RustSec advisories (deps) |
| cargo-deny | `cargo install cargo-deny` | policy supply-chain |
| cargo-geiger | `cargo install cargo-geiger` | surface `unsafe` |
| cargo-nextest | `cargo install cargo-nextest` | test runner rapide |
| cargo-llvm-cov | `cargo install cargo-llvm-cov` | couverture |

**Si un outil manque** : marquer le bloc correspondant `N/A (tool missing)` -- ne JAMAIS inventer
un resultat (R18). Lancer `scripts/install_rust_audit.sh --check` pour l'etat exact, puis
`scripts/install_rust_audit.sh` pour installer.

Prerequis supply-chain (best practice 2026) : **`Cargo.lock` DOIT etre committe**, sinon
`cargo audit` ne peut pas matcher les versions exactes (check A9).

Scorer automatise (equivalent du `lia_recette` Go) :
- `cmd/inspect_ia_agents_recette/` -- binaire Rust qui automatise les blocs A/B/C/F (scan de patterns)
  + orchestre le bloc D (clippy/audit/deny/geiger/fmt), produit un score /44 (texte ou JSON)
  et un exit code CI. Build : `cargo build --release -p inspect_ia_agents_recette` (ou depuis le dossier).
  Usage :
  ```bash
  cmd/inspect_ia_agents_recette/target/release/inspect_ia_agents_recette <fichier|crate>            # rapport texte
  inspect_ia_agents_recette --format json <crate>                                           # JSON pour apex/pdca
  inspect_ia_agents_recette --skip-tools <crate>                                            # blocs A/B/C/F seuls (rapide)
  inspect_ia_agents_recette --min-score 39 <crate>; echo $?                                 # exit 0 si gate OK
  ```
  Les blocs E (R17) et plusieurs checks semantiques restent `N/A` (revue manuelle) -- le binaire
  ne devine pas, il les exclut du score (renormalisation). Utiliser ce binaire pour le score
  chiffre reproductible ; ce document (LLM) pour les blocs manuels E + A7/A8/B4/B7/B8/C2-C9/F2/F3/F5.

Configuration projet livree :
- `deny.toml` (racine) -- policy cargo-deny (advisories deny-by-default, licenses permissives only, wildcards deny, sources crates.io only). Utilisee par D4.
- `.githooks/pre-commit` -- gate Rust au commit (fmt + clippy + audit sur les `.rs` stages). Activer : `git config core.hooksPath .githooks`. Bypass : `RUST_RECETTE_PRECOMMIT_SKIP=1`.

---

## Processus d'analyse

### Etape 1 - Lecture du code

Lis le ou les fichiers cibles (Read, Glob).
Si c'est un repertoire : `find {dir} -name "*.rs" -not -path "*/target/*"`.
Determine le workspace root (dossier contenant `Cargo.toml` avec `[workspace]` ou le plus proche).

### Etape 2 - Verification des blocs

Pour chaque point : PASS, FAIL (avec ligne et extrait), ou N/A. Les commandes cargo se lancent
au workspace root (ou avec `-p <crate>` pour cibler un crate).

---

## BLOC A -- Conventions inspect_ia_agents Backend (10 points)

### A1 -- tracing only, pas de println (CRITIQUE)
- INTERDIT : `println!`, `eprintln!`, `print!`, `dbg!` pour du logging applicatif
- OBLIGATOIRE : `tracing::info!/warn!/error!(...)` avec champs structures, ou `#[instrument]`
- Exception toleree : `main()` avant init du subscriber, examples, build scripts
- Verifier : `grep -nE 'println!|eprintln!|dbg!' {file}` (hors `#[cfg(test)]`)

### A2 -- Error handling type, pas de panic sur chemin faillible (CRITIQUE)
- INTERDIT : `.unwrap()`, `.expect(...)`, `panic!`, `unreachable!` sur un chemin faillible (I/O, parse, reseau, lock)
- OBLIGATOIRE : `?` + erreurs typees (`thiserror` en lib, `anyhow` en binaire), voir skill `error-handling-patterns`
- Tolere : `.expect()` DANS un `#[cfg(test)]` (le message EST l'assertion), `.unwrap()` sur un invariant prouve avec `// SAFETY:`/`// INVARIANT:`
- Verifier : `grep -nE '\.unwrap\(\)|\.expect\(|panic!|unreachable!' {file}` (hors tests)

### A3 -- Pas de secret / URL / sujet NATS hardcode (CRITIQUE)
- INTERDIT : cle API, mot de passe, token, URL d'infra, sujet NATS, DSN en dur dans le code
- OBLIGATOIRE : `std::env::var(...)` (sans fallback sensible) ou config typee (`config`/`figment`) chargee au boot
- Verifier : `grep -nE '"(gsk_|sk-|eyJ|postgres://|nats://|amqp://)|api_key\s*=\s*"|password\s*=\s*"' {file}`

### A4 -- rustfmt clean
- OBLIGATOIRE : `cargo fmt --all -- --check` retourne 0 diff
- Verifier : `cargo fmt -- --check {file} 2>&1` (vide = PASS)

### A5 -- Comments en anglais (R12)
- INTERDIT : commentaires inline / docstrings en francais dans les `.rs`
- OBLIGATOIRE : tout commentaire et doc-comment (`///`, `//!`) en anglais
- Verifier : `grep -nE '//.*\b(le|la|les|une|des|avec|pour|donnee|fichier)\b' {file}`

### A6 -- No open-source attribution (R13)
- INTERDIT : nom d'un outil OSS source d'inspiration dans commentaires/noms/fichiers
- OBLIGATOIRE : citer la doc vendor/RFC officielle si attribution necessaire

### A7 -- Public API documented
- OBLIGATOIRE : tout `pub fn`/`pub struct`/`pub enum`/`pub trait` exporte a un doc-comment `///`
- Recommande : `#![warn(missing_docs)]` au crate root
- Verifier : items `pub` sans `///` au-dessus

### A8 -- RAII / pas de leak de ressource
- OBLIGATOIRE : ressources (locks, fichiers, connexions, guards) liberees par `Drop`/scope, pas de `mem::forget` injustifie
- INTERDIT : `MutexGuard` tenu a travers un `.await` (deadlock async) -- utiliser `tokio::sync::Mutex` si garde a travers await
- Verifier : `std::sync::Mutex` lock garde a travers `.await`

### A9 -- Cargo.lock committe (supply chain)
- OBLIGATOIRE : `Cargo.lock` present et versionne (prerequis pour cargo-audit deterministe)
- Verifier : `test -f Cargo.lock && git ls-files --error-unmatch Cargo.lock`

### A10 -- Fail-safe par defaut (failure-modes inspect_ia_agents)
- OBLIGATOIRE : chemin d'erreur -> deny/freeze, JAMAIS fail-open (policy engine down -> DENY)
- INTERDIT : `unwrap_or(true)` / `.unwrap_or_default()` qui ouvre un acces sur erreur de decision
- Reference : `.claude/rules/failure-modes.md`

---

## BLOC B -- Securite OWASP Rust (10 points)

### B1 -- SQL Injection (OWASP A03 - CRITIQUE)
- INTERDIT : `format!("SELECT ... {} ...", user_input)` injecte dans une query
- OBLIGATOIRE : requetes parametrees `sqlx::query!("... WHERE col = $1", value)` / bind diesel
- Verifier : `grep -nE 'format!.*(SELECT|INSERT|UPDATE|DELETE)|query\(&format!' {file}`

### B2 -- Command Injection (OWASP A03 - CRITIQUE)
- INTERDIT : `Command::new("sh").arg("-c").arg(format!("... {}", input))`
- OBLIGATOIRE : `Command::new("bin").arg(validated_arg)` avec args separes + validation
- Verifier : `grep -nE 'Command::new\("(sh|bash)"\)|\.arg\("-c"\)' {file}`

### B3 -- Hardcoded Secrets (OWASP A02 - CRITIQUE)
- Voir A3. Verifier aussi les valeurs par defaut sensibles dans `Default` impls et `const`/`static`

### B4 -- AuthN/AuthZ + identity binding (OWASP A01, I3 - CRITIQUE)
- Toute route protegee DOIT passer par le middleware/layer auth (Axum `from_fn`/`require_auth`)
- Si route publique : whitelistee explicitement avec justification
- I3 : toute action liee cryptographiquement a un `agent_id` (pas d'action anonyme/non signee)
- Verifier : nouvelles routes -> couvertes par le layer auth ? identite verifiee ?

### B5 -- Path Traversal (OWASP A01)
- INTERDIT : `File::open(user_path)` / `fs::read(user_path)` sans canonicalisation + check prefixe
- OBLIGATOIRE : `Path::canonicalize()` + `starts_with(allowed_root)`
- Verifier : `grep -nE 'File::open\(|fs::read|fs::write' {file}`

### B6 -- Error Disclosure (OWASP A09)
- INTERDIT : renvoyer `format!("{:?}", err)` / `err.to_string()` interne au client (leak chemins/SQL/stack)
- OBLIGATOIRE : message generique cote client + `tracing::error!` pour le detail interne
- Verifier : erreurs internes propagees dans le body de reponse HTTP

### B7 -- Security Logging (R10)
- Toute tentative d'attaque detectee DOIT etre loggee :
  `tracing::warn!(target: "security", agent_id = %id, "blocked: invalid column {col}")`

### B8 -- Input Validation (typed boundary)
- OBLIGATOIRE : extractors typed (`Path<Uuid>`, `Json<T>` avec `#[validate]`/`serde` strict)
- INTERDIT : `Path<String>` puis usage direct sans `Uuid::parse_str()` + check
- Validation au boundary (longueur, format, range)

### B9 -- TLS Verification (OWASP A07)
- INTERDIT : `danger_accept_invalid_certs(true)` / `danger_accept_invalid_hostnames(true)` (reqwest/rustls) sans justification
- OBLIGATOIRE : verifier les certificats sur les appels sortants
- Verifier : `grep -nE 'danger_accept_invalid|InsecureSkipVerify|set_verify\(SslVerifyMode::NONE\)' {file}`

### B10 -- unsafe justifie (// SAFETY:)
- Tout bloc `unsafe` DOIT avoir un commentaire `// SAFETY:` justifiant l'invariant
- INTERDIT : `unsafe` sans justification ; preferer le safe Rust
- Verifier : `grep -n 'unsafe' {file}` puis check `// SAFETY:` adjacent + corrobore par `cargo geiger` (Bloc D5)

---

## BLOC C -- Architecture & Performance (10 points)

### C1 -- Pas de stub (R3)
- INTERDIT : `todo!()`, `unimplemented!()`, handler renvoyant `StatusCode::NOT_IMPLEMENTED` dans du code actif
- Verifier : `grep -nE 'todo!\(\)|unimplemented!\(\)|NOT_IMPLEMENTED' {file}`

### C2 -- No mock data (R4)
- INTERDIT : valeurs litterales inventees dans des reponses (`Stats { total: 100, .. }`)
- OBLIGATOIRE : valeurs calculees depuis donnees reelles (event store, DB)

### C3 -- Async task cleanup
- INTERDIT : `tokio::spawn(...)` detache sans `JoinHandle` conserve / sans `CancellationToken`
- Verifier : risque de leak de task ; tasks longues annulables via `select!` + token

### C4 -- Error wrapping / context
- OBLIGATOIRE : `anyhow::Context::context(...)` ou `thiserror` `#[from]` pour preserver la chaine
- INTERDIT : `.map_err(|_| MyError::Generic)` qui efface l'erreur source

### C5 -- Borrow vs clone (perf, rust-best-practices ch3)
- INTERDIT : `.clone()` systematique pour contourner le borrow checker
- OBLIGATOIRE : `&T` quand l'ownership n'est pas requis ; `Cow`/`Arc` si partage
- Verifier : clones redondants dans des boucles / hot paths

### C6 -- Pool / client reuse
- INTERDIT : creer un `PgPool`/`reqwest::Client`/connexion NATS par requete
- OBLIGATOIRE : client/pool partage (`Arc`) initialise au boot, injecte via state Axum

### C7 -- serde pour JSON
- OBLIGATOIRE : `serde_json` / `Json<T>` derive
- INTERDIT : construction manuelle de JSON via `format!(r#"{{"k":"{}"}}"#, v)` (escaping/XSS)

### C8 -- IDs typed (Uuid/Ulid)
- OBLIGATOIRE : `Uuid::parse_str(...)` / `Ulid::from_string(...)` au boundary avant usage
- Logger les formats invalides (`tracing::warn!`)

### C9 -- Pagination sur les list endpoints
- Si l'endpoint retourne une liste : `LIMIT`/`OFFSET` ou cursor obligatoire
- INTERDIT : charger toute une table/stream sans borne

### C10 -- Tests presents (#[cfg(test)] / tests/)
- Tout nouveau module/handler DOIT avoir un `#[cfg(test)] mod tests` ou un fichier `tests/*.rs`
- Couvrir : cas nominal, cas erreur, cas limite (rust-best-practices ch5)
- Reference : skill `/test-first`

---

## BLOC D -- Static Analysis (toolchain cargo -- equivalent gosec/govulncheck)

Lancer au workspace root. C'est le coeur de l'equivalence avec le Bloc D de /go-recette.

### D1 -- cargo clippy (go vet + lints securite)
```bash
cargo clippy --all-targets --all-features -- -D warnings 2>&1 | tee /tmp/rust-recette-clippy.txt
# Compter par categorie
grep -cE '^warning|^error' /tmp/rust-recette-clippy.txt
```
- 0 warning/error = PASS. Toute sortie `-D warnings` non vide = FAIL.

### D2 -- cargo audit (RustSec -- equivalent govulncheck)
```bash
cargo audit 2>&1 | tee /tmp/rust-recette-audit.txt
# JSON pour automation
cargo audit --json > /tmp/rust-recette-audit.json 2>/dev/null
# Compter HIGH/CRITICAL
grep -cE 'Severity: (high|critical)' /tmp/rust-recette-audit.txt
```
- Toute advisory HIGH/CRITICAL non patchee = FAIL bloquant.
- Advisory `unmaintained`/`yanked` = warning majeur.

### D3 -- cargo fmt
```bash
cargo fmt --all -- --check 2>&1
```
- Sortie non vide = FAIL.

### D4 -- cargo deny (supply chain policy)
```bash
cargo deny check advisories bans licenses sources 2>&1 | tee /tmp/rust-recette-deny.txt
```
- `error` sur advisories/bans/licenses/sources = FAIL.
- Si `deny.toml` absent : generer un defaut (`cargo deny init`) ou marquer N/A si non desire.

### D5 -- cargo geiger (surface unsafe -- complement gosec)
```bash
cargo geiger --output-format Ascii 2>&1 | tail -30
```
- Tout `unsafe` dans le code du projet (pas les deps) sans `// SAFETY:` = FAIL (corrobore B10).
- `N/A (tool missing)` si non installe.

### Ajouter au rapport :
```
BLOC D -- STATIC ANALYSIS
--------------------------
D1 cargo clippy   : [warnings=X errors=Y] -> [PASS/FAIL]
D2 cargo audit    : [HIGH=X CRIT=Y unmaint=Z] -> [PASS/FAIL]
D3 cargo fmt      : [PASS/FAIL]
D4 cargo deny     : [advisories/bans/licenses/sources errors=X] -> [PASS/FAIL/N/A]
D5 cargo geiger   : [unsafe sans SAFETY=X] -> [PASS/FAIL/N/A]
```

**Helper** : `.claude/scripts/rust-recette-deep-scan.sh {file_or_crate}` execute D1-D5 et produit
`/tmp/rust-recette-deep/report.md`.

---

## BLOC E -- R17 Contract Gate (Axum handler -- BLOQUANT)

S'applique UNIQUEMENT si le fichier definit un handler HTTP Axum (`async fn` route, `Router::route`,
`.route("/api/...")`). Sinon : N/A.

### E1 -- Test file avec invocation du handler reel
- OBLIGATOIRE : un test qui construit le `Router` et envoie une requete via `tower::ServiceExt::oneshot`
- DOIT contenir : assertion sur le `StatusCode` + assertion sur le body JSON (cle/type attendu)
- Verifier : `grep -rnE 'oneshot|TestServer|Request::builder' {crate}/tests/ {file}`

### E2 -- Test execution
```bash
cargo test {handler_test_name} 2>&1   # ou cargo nextest run -E 'test(handler)'
```
- DOIT PASS (exit 0). INTERDIT : `#[ignore]` sans justification.

### E3 -- Live smoke (curl reel sur la gateway qui tourne)
```bash
curl -s -o /tmp/r.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
     http://localhost:8081/api/{endpoint}
jq . /tmp/r.json
```
- DOIT retourner le code attendu + JSON valide. Preuve dans RETEX ou decision_log.

### E4 -- Response envelope coherence
- Si le handler renvoie une enveloppe `{success, data}` : le service frontend consommateur DOIT unwrap `.data`
- Verifier : `grep -rn "{endpoint}" sigma-react-frontend/src/services/`

### Verdict R17 (BLOQUANT)
- Handler HTTP + 1 seul FAIL E1-E4 -> "R17 Contract Gate FAILED. Fournir test + smoke avant integration." (bloquant quel que soit le score)

---

## BLOC F -- Invariants inspect_ia_agents (I1-I6, 6 points -- remplace le Bloc G migration de Go)

Applicable a tout code touchant le chemin de decision, l'event store, ou les effets de bord.
Reference : `.claude/rules/invariants.md`.

### F1 -- Immutabilite event store (I1)
- INTERDIT : `UPDATE`/`DELETE` sur le log d'evenements ; correction = evenement compensatoire
- Verifier : `grep -nE '(UPDATE|DELETE).*event' {file}`

### F2 -- Mediation Control Plane (I2)
- INTERDIT : chemin direct agent -> systeme externe contournant la Gateway/policy
- OBLIGATOIRE : toute action externe passe par l'evaluation Control Plane

### F3 -- Side-effects mediats (I5)
- INTERDIT : appel reseau/disque direct depuis la logique metier
- OBLIGATOIRE : passer par les interfaces proxy controlees

### F4 -- Replay deterministe (I4)
- INTERDIT dans le chemin de decision : `SystemTime::now()`, `Instant::now()`, `rand::*`, I/O non capturee
- OBLIGATOIRE : source de temps/random injectee et capturee dans l'evenement
- Verifier : `grep -nE 'SystemTime::now|Instant::now|rand::|thread_rng' {file}`

### F5 -- Blocage sur approbation (I6)
- INTERDIT : execution optimiste "en attendant" l'approbation
- OBLIGATOIRE : action requerant approbation BLOQUE jusqu'a resolution ou timeout

### Ajouter au rapport :
```
BLOC F -- INVARIANTS INSPECT_IA_AGENTS
-------------------------------
F1 Immutabilite (I1)      : [PASS / FAIL / N/A]
F2 Mediation CP (I2)      : [PASS / FAIL / N/A]
F3 Side-effects (I5)      : [PASS / FAIL / N/A]
F4 Replay determinist (I4): [PASS / FAIL / N/A]
F5 Approval block (I6)    : [PASS / FAIL / N/A]
```

---

## Format du rapport

```
RAPPORT RUST RECETTE - {fichier ou crate}
Date : {date}
==========================================

BLOC A - CONVENTIONS INSPECT_IA_AGENTS
-------------------------------
A1  tracing only             : [PASS / FAIL ligne X / N/A]
A2  No panic on fallible     : [PASS / FAIL ligne X]
A3  No hardcoded secret/URL  : [PASS / FAIL ligne X]
A4  rustfmt clean            : [PASS / FAIL]
A5  Comments en anglais      : [PASS / FAIL ligne X]
A6  No source attribution    : [PASS / FAIL ligne X]
A7  Public API documented    : [PASS / FAIL ligne X]
A8  RAII / no leak           : [PASS / FAIL ligne X]
A9  Cargo.lock committed     : [PASS / FAIL]
A10 Fail-safe default        : [PASS / FAIL ligne X]

BLOC B - SECURITE OWASP RUST
-----------------------------
B1  SQL Injection            : [PASS / FAIL ligne X]
B2  Command Injection        : [PASS / FAIL ligne X]
B3  Hardcoded Secrets        : [PASS / FAIL ligne X]
B4  AuthN/Z + identity (I3)  : [PASS / FAIL]
B5  Path Traversal           : [PASS / FAIL ligne X]
B6  Error Disclosure         : [PASS / FAIL ligne X]
B7  Security Logging         : [PASS / FAIL ligne X]
B8  Input Validation         : [PASS / FAIL ligne X]
B9  TLS Verification         : [PASS / FAIL ligne X]
B10 unsafe justifie          : [PASS / FAIL ligne X]

BLOC C - ARCHITECTURE & PERFORMANCE
------------------------------------
C1  No stub                  : [PASS / FAIL]
C2  No mock data             : [PASS / FAIL ligne X]
C3  Async task cleanup       : [PASS / FAIL ligne X]
C4  Error wrapping           : [PASS / FAIL ligne X]
C5  Borrow vs clone          : [PASS / FAIL ligne X]
C6  Pool/client reuse        : [PASS / FAIL]
C7  serde JSON               : [PASS / FAIL ligne X]
C8  IDs typed (Uuid/Ulid)    : [PASS / FAIL ligne X]
C9  Pagination               : [PASS / FAIL]
C10 Tests present            : [PASS / FAIL]

BLOC D - STATIC ANALYSIS
-------------------------
D1 cargo clippy              : warnings=X errors=Y [PASS/FAIL]
D2 cargo audit               : HIGH=X CRIT=Y [PASS/FAIL]
D3 cargo fmt                 : [PASS/FAIL]
D4 cargo deny                : errors=X [PASS/FAIL/N/A]
D5 cargo geiger              : unsafe_no_safety=X [PASS/FAIL/N/A]

BLOC E - R17 CONTRACT GATE
---------------------------
E1 Test file present         : [PASS / FAIL / N/A]
E2 Test execution PASS       : [PASS / FAIL / N/A]
E3 Live smoke curl           : [PASS / FAIL / N/A]
E4 Response envelope         : [PASS / FAIL / N/A]

BLOC F - INVARIANTS INSPECT_IA_AGENTS
------------------------------
F1 Immutabilite (I1)         : [PASS / FAIL / N/A]
F2 Mediation CP (I2)         : [PASS / FAIL / N/A]
F3 Side-effects (I5)         : [PASS / FAIL / N/A]
F4 Replay deterministe (I4)  : [PASS / FAIL / N/A]
F5 Approval block (I6)       : [PASS / FAIL / N/A]

==========================================
SCORE A+B+C : XX/30
SCORE D     : XX/5
SCORE E     : XX/4 (ou N/A si pas un handler HTTP)
SCORE F     : XX/5 (ou N/A si hors chemin decision/event/side-effect)
SCORE GLOBAL: XX/44 (ou /40 si E N/A, ou /39 si F N/A, ou /35 si E+F N/A)
SECURITY DOMAIN /20 (pour PDCA) : voir build-pipeline-rust.md (20 - penalites D2/D1/B10/D4)
CRITIQUES (FAIL A1-A3, B1-B4, D1, D2 HIGH) : X
==========================================

DETAILS DES FAILS
-----------------
[Pour chaque FAIL : point, ligne, extrait, correction recommandee]
```

---

## Niveaux de severite

- **CRITIQUE** (bloque le merge) :
  - A1 (tracing), A2 (no panic fallible), A3 (secrets)
  - B1 (SQL inj), B2 (cmd inj), B3 (secrets), B4 (auth/identity)
  - D1 clippy `-D warnings`, D2 cargo audit HIGH/CRITICAL
  - un seul FAIL Bloc E (R17) si handler HTTP
  - tout FAIL Bloc F (invariant I1-I6 viole)
- **MAJEUR** (a corriger avant merge) :
  - A4-A10, B5-B10, C1-C5, D3 fmt, D4 deny, D5 geiger
- **MINEUR** (corriger avant prod) :
  - C6-C10

## Verdicts

- Score >= 39/44 ET 0 critique en FAIL : **"Pret pour integration."**
- Score 30-38/44 OU >= 1 majeur en FAIL : **"Corrections requises avant integration."**
- Score < 30/44 OU >= 1 critique en FAIL : **"NE PAS INTEGRER. Refonte necessaire."**

Si Bloc E (R17) en FAIL OU un invariant Bloc F viole : verdict bloquant quel que soit le score.
