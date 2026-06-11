---
name: improve-hook
description: >
  Ameliore le hook pre-commit LIA-SEC (.claude/hooks/security_check.sh) pour detecter
  les hardcodings (localhost, URLs en dur, fmt.Println, console.log, print) dans le CODE et dans
  les COMMENTAIRES des fichiers .go, .ts, .tsx, .py modifies. Utiliser quand le hook doit etre
  etendu, quand un nouveau pattern interdit est identifie en RETEX, ou pour valider
  manuellement qu'un fichier ne contient aucun hardcoding avant commit.
---

# improve-hook

Etend `security_check.sh` pour detecter les hardcodings dans code ET commentaires.
Ne remplace pas gosec/semgrep — s'ajoute apres eux.

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_IMPROVE_HOOK_{PATTERN}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Ressources

- **Script** : `.claude/skills/improve-hook/scripts/check_hardcodings.sh <file>` — exit 0=OK, 1=violations, 2=usage error
- **Langages supportes** : `.go`, `.ts`, `.tsx`, `.js`, `.jsx`, `.py`
- **Patterns** : `references/patterns.md` — tableaux complets + exclusions + snippets d'integration

## Utilisation directe (validation manuelle)

```bash
.claude/skills/improve-hook/scripts/check_hardcodings.sh cmd/sigma_web/mon_fichier.go
.claude/skills/improve-hook/scripts/check_hardcodings.sh scripts/my_script.py
```

## Integrer dans security_check.sh

Lire `references/patterns.md` section "Integration hardcoding check". Inserer le bloc **dans chaque case**
`*.go`, `*.ts|*.tsx` et `*.py`, apres les blocs gosec/semgrep, avant le `;;`.

## Ajouter un nouveau pattern

1. Identifier : pattern grep + logique (code vs commentaire, Go vs TS vs Python)
2. Ajouter dans `scripts/check_hardcodings.sh` dans la section appropriee
3. Mettre a jour `references/patterns.md`
4. Tester les deux cas : violation (exit 1) et fichier propre (exit 0)

## Exit codes du hook (security_check.sh)

| Situation | Exit code | Comportement |
|---|---|---|
| Gosec/semgrep findings | `0` + `systemMessage` | Non-bloquant, avertissement |
| Hardcoding violations | `0` + `systemMessage` | Non-bloquant, avertissement |
| Tests Go validator FAIL | `2` | **BLOQUANT** — corrige les tests avant de continuer |
| Tout OK | `0` | Silencieux |

## Test-runner Go (automatique)

Le hook execute `go test` quand certains packages Go sont modifies :

| Package modifie | Test lance |
|---|---|
| `pkg/validator/recipe/...` ou `cmd/lia_recette/...` | `go test ./pkg/validator/recipe/` |
| `pkg/validator/ultimate/...` | `go test ./pkg/validator/ultimate/` |
| `pkg/validator/reportrule/...` | `go test ./pkg/validator/reportrule/` |

Exit 2 bloque le Write/Edit si les tests echouent. Voir `references/patterns.md` section "Test-runner Go".

## Regles critiques

- Hardcoding/security checks : toujours `exit 0` + `systemMessage` — jamais bloquant
- Test-runner Go : `exit 2` si tests echouent — **bloquant intentionnel**
- Ne pas signaler imports Go/Python ni URLs officielles (nvd.nist.gov, cisa.gov, attack.mitre.org)
- Tag `COMMENT` pour commentaires (`//` ou `#`), tag `HARDCODE` pour le code — meme pattern, message different
- Pas de double-detection : si localhost deja detecte, ne pas re-signaler via pattern http
