# R17 Vuln Fix -- toujours la derniere version, jamais iterer a l'aveugle

## Pourquoi

Quand `cargo audit` / `cargo deny` / `npm audit` signale une vuln "corrigee en X.Y.Z ou
plus recent", `X.Y.Z` est le MINIMUM qui corrige CETTE CVE. Il existe souvent des CVE plus
recentes deja patchees au-dela. Iterer version par version brule du temps et des cycles.

## La regle

1. **Ne PAS choisir la version minimale.** Recuperer la DERNIERE version stable depuis la
   source canonique :
   - Crate Rust : `cargo search <crate>` ou `cargo info <crate>` ou page crates.io.
   - Toolchain Rust : `https://forge.rust-lang.org/` / `rustup check`.
   - Package npm : `npm show <pkg> version`.
   - Module/binaire : page de releases officielle.

2. **Appliquer la derniere version d'un coup**, puis relancer le scanner UNE fois pour confirmer.

3. **Ne jamais iterer par essai-erreur.** Si le premier upgrade ne nettoie pas, investiguer
   (mauvais crate, dependance transitive, cache de build) plutot que rebumper.

## Anti-pattern

```
cargo audit: fixed in 0.4.2 -> bump 0.4.2 -> rerun
cargo audit: fixed in 0.5.0 -> bump 0.5.0 -> rerun
cargo audit: fixed in 0.5.3 -> bump 0.5.3 -> rerun
```
3 iterations inutiles.

## Pattern correct

```
cargo audit: fixed in 0.4.2
  -> cargo search <crate> -> latest stable = 0.6.1
  -> bump 0.6.1 dans Cargo.toml
  -> cargo update -p <crate> && cargo audit  (une fois)
```

## Outils recommandes

- Ajouter `cargo audit` (RustSec) et/ou `cargo deny` au pipeline qualite.
- `cargo update` pour les dependances transitives ; `cargo upgrade` (cargo-edit) pour bumper Cargo.toml.

Integre avec R13 (verifier les faits) : ne pas deviner une version, la chercher.
