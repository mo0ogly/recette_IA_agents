# LIA-SEC Constraints -- Spec-Builder Reference

## Context Files to Read

Before generating any spec, READ these project context files:

```
Read: /opt/lia-sec/dev/.claude/rules/project-structure.md
Read: /opt/lia-sec/dev/.claude/rules/api-reference.md
Read: /opt/lia-sec/dev/.claude/rules/anti-patterns.md
```

## Technical Constraints (Steering)

| Parametre | Valeur |
|-----------|--------|
| Backend | Go 1.25.1, Gorilla Mux, 560+ routes |
| Frontend | React 19, TypeScript 4.9, MUI v7 |
| Database | PostgreSQL 17 (268 tables, `lia_scan`) |
| Auth | JWT deny-by-default (`fetchWithConfig`) |
| Logging | `LogSystemEvent()` Go / `customLogger` React |
| Grid | MUI v7 : `size={{ xs: 12, md: 8 }}` (JAMAIS `item xs=`) |
| URLs | `ConfigurationService` / `fetchWithConfig` (JAMAIS hardcode) |
| Emoji | INTERDIT partout |
| Tests | `/recette/` pour validation |
| Migrations | `cmd/sigma_web/migrations/NNN_feature.sql` |
| Build | Ajouter tout `.go` dans `build_secure_lia.sh` |
