# No Hardcoded Secrets -- credentials via env / secret store

## REGLE ABSOLUE : jamais de mot de passe, token, cle API ou secret en dur dans le code

Les credentials des external systems sont detenus UNIQUEMENT par les proxies (I5) et charges
depuis l'environnement ou un secret store, jamais ecrits dans le code ou committes.

### Patterns INTERDITS

```rust
// Rust
let api_key = "sk-proj-abc123...";                       // INTERDIT
let dsn = "postgres://user:password@localhost/db";       // INTERDIT
let token = "eyJhbGciOiJIUzI1NiIs...";                   // INTERDIT
const NATS_CREDS: &str = "SUAB...";                      // INTERDIT
```

```toml
# Cargo / config committe
api_key = "sk-proj-abc123"                               # INTERDIT
```

```typescript
// Frontend
const API_TOKEN = "eyJ...";                              // INTERDIT
```

### Patterns CORRECTS

```rust
// Rust : env, avec erreur explicite si absent (fail-safe, pas de fallback secret)
let api_key = std::env::var("INSPECT_IA_AGENTS_EXTERNAL_API_KEY")
    .map_err(|_| ConfigError::MissingSecret("INSPECT_IA_AGENTS_EXTERNAL_API_KEY"))?;

// Ou via la couche config (figment/config) qui lit env + secret store
let db_url = config.database_url();   // resolu depuis env / secret manager
```

### Variables d'environnement inspect_ia_agents (convention)

| Variable | Usage |
|----------|-------|
| `INSPECT_IA_AGENTS_DATABASE_URL` | DSN PostgreSQL (event store / read-models) |
| `INSPECT_IA_AGENTS_NATS_URL` | URL du cluster NATS |
| `INSPECT_IA_AGENTS_NATS_CREDS` | chemin vers le fichier de creds NATS (pas le secret inline) |
| `INSPECT_IA_AGENTS_TEMPORAL_ADDRESS` | adresse du frontend Temporal |
| `INSPECT_IA_AGENTS_JWT_SIGNING_KEY` | cle de signature des tokens (I3) |
| `INSPECT_IA_AGENTS_EXTERNAL_*` | credentials des external systems (detenus par les proxies) |

### Fichiers exclus du git (.gitignore)

- `.env` (env local) -- committer un `.env.example` SANS valeurs.
- `*.creds`, `*.key`, `*.pem`.
- `.claude/settings.local.json`.

### Detection

Le hook `secret-scanner.cjs` (PreToolUse Bash) bloque les patterns de secrets evidents.
Avant tout commit : `git diff --cached` et verifier qu'aucun secret n'apparait.
