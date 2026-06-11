# Rust / Axum Conventions -- AgentRail

> Avant d'ecrire du Rust non trivial, consulter le skill `rust-best-practices` et
> `error-handling-patterns`. Pour un serveur MCP : `rust-mcp-server-generator`.

## Toolchain & gates (avant tout commit)

```bash
cargo fmt --all                       # format
cargo clippy --all-targets -- -D warnings   # lint, warnings = erreurs
cargo test --all                      # tests
cargo test --all --release            # (chemins de decision : valider en release aussi)
```

Verifier la derniere version stable de la toolchain et des crates avant ajout (voir
`vuln-fix-latest-version.md`). `cargo build` doit etre propre, zero warning.

## Gestion d'erreur (R7)

- Frontiere applicative / handlers : `anyhow::Result` ou type d'erreur dedie.
- Bibliotheque / domaine : types d'erreur explicites avec `thiserror`.
- INTERDIT en chemin de production : `.unwrap()`, `.expect()`, `panic!`, `todo!()`,
  `unimplemented!()`. Autorise uniquement dans `tests/`, `build.rs`, et setup d'init
  ou un panic au demarrage est le comportement voulu (et documente).
- Les erreurs du chemin de decision sont auditables (evenement d'echec, pas un log perdu).

```rust
// INTERDIT
let agent = identity.resolve(id).unwrap();
// CORRECT
let agent = identity.resolve(id).map_err(|e| {
    tracing::warn!(error = %e, %id, "identity resolution failed");
    GatewayError::Unauthenticated
})?;
```

## Logging (R6)

- `tracing` uniquement. Spans pour les operations, fields structures.
- Correler par `event_id` et `agent_id` : `tracing::info!(%event_id, %agent_id, "...")`.
- JAMAIS `println!`/`eprintln!`/`dbg!` de debug livre.

## Async & concurrence

- Runtime : `tokio`. Pas de blocage du runtime (`std::thread::sleep`, I/O bloquant) sur un
  thread async -> `tokio::task::spawn_blocking` si necessaire.
- Le chemin de decision est synchrone et pur (I4) ; l'I/O (proxies, store) est async et hors decision.
- Pas de `.await` qui introduit du non-determinisme dans `decide` (voir `determinism-replay.md`).

## Frontieres & traits

- Toute dependance externe (event store, proxy, bus, policy source) est derriere un **trait**,
  mockable en test. Cela rend le replay et les tests deterministes possibles.
- Exemple : `EventStore`, `ExternalSystemProxy`, `PolicySource`, `IdentityResolver`.

## Structure & taille

- Modules par plan/responsabilite (`control/`, `data/`, `audit/`), pas un mega-fichier.
- Eviter les fichiers monolithes ; preferer des modules cohesifs SRP.

## Config (R5)

- Config via env + fichier versionne (`figment`/`config`), jamais de valeur magique en dur
  (URL, sujet NATS, seuil de risque, credentials). Secrets : voir `no-hardcoded-secrets.md`.

## Securite

- Avant tout handler d'auth / endpoint manipulant des credentials ou input externe :
  consulter le skill `secure-code-guardian`.
- Validation des inputs aux frontieres (la Gateway valide avant normalisation).
