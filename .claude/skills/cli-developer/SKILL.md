---
name: cli-developer
description: Build LIA-SEC CLI tools in Go (cobra/spf13) or Bash idiomatically -- adapted for the existing toolchain `lia_recette`, `lia_admin_pwreset`, `build_secure_lia.sh`, `cleanup_services.sh`, `deploy.sh`, `cc.sh`. Invoke when adding a new CLI binary under `cmd/`, a new flag/subcommand, a new bash script under root or `scripts/`, completion (bash/zsh), or refactoring a script for safety (set -euo pipefail, helper psql_lia, R8 secrets via env). Differe de `/devops-engineer` (deploy automation), `/golang-pro` (Go general), `/sql-pro` (SQL queries) -- focus UX terminal + arg parsing + completion + safety.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/cli-developer
  version: "2.0.0-lia"
  domain: devops
  triggers: nouveau CLI, cobra, spf13, lia_recette, lia_admin_pwreset, build_secure_lia, cleanup_services, deploy.sh, bash script, shell completion, --help, --version, subcommand, argument parsing, interactive prompt, progress bar, set -euo pipefail
  role: specialist
  scope: implementation
  output-format: code (Go cobra OR bash)
  related-skills: golang-pro, devops-engineer, sql-pro
  enforces-rules: R1, R6, R7, R8, R9, R10, R12
---

# CLI Developer (LIA-SEC adaptation)

> **Stack reel CLI LIA-SEC**
> - **Go** : `cobra` + `spf13/pflag` (deja utilise dans `cmd/lia_recette`, `cmd/lia_admin_pwreset`)
> - **Bash** : scripts root (`build_secure_lia.sh`, `cleanup_services.sh`, `deploy.sh`, `cc.sh`)
> - **Pas de** : Python click/typer (Python tres minoritaire), Node CLI (pas en prod)
>
> Ne PAS reinventer si un CLI existant peut etre etendu (cobra subcommand).

## 0. Inventaire CLI LIA-SEC existant

| CLI | Type | Path | Role |
|-----|------|------|------|
| `lia_recette` | Go cobra | `cmd/lia_recette/` | Validation regles YAML/JSON |
| `lia_admin_pwreset` | Go | `cmd/lia_admin_pwreset/` | Reset password admin (bcrypt) |
| `build_secure_lia.sh` | Bash | `cmd/sigma_web/build_secure_lia.sh` | Build whitelist Go (R16) |
| `cleanup_services.sh` | Bash | root | Gestion services (R9) |
| `deploy.sh` | Bash | root | Pipeline dev->VPS |
| `cc.sh` | Bash interactif | root | Menu interactif Claude Code |

## 1. Workflow agentique (5 phases)

```
[1] ANALYZE   : workflow ? subcommand existant a etendre ? maintainer-only ou diffusion ?
[2] DESIGN    : lister help text complet AVANT code, naming flags POSIX coherent, exit codes (0/1/2/3/130)
[3] IMPLEMENT : Go cobra+viper / Bash strict mode, secrets via env (R8), psql_lia helper
[4] POLISH    : help text, completion bash/zsh, progress IF TTY, SIGINT graceful
[5] TEST      : --help, --version, time < 50ms startup, doc user-guide
```

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Quand |
|-------|-----------|-------|
| Design patterns | `references/design-patterns.md` | Architecture subcommands, config layering |
| Go CLI | `references/go-cli.md` | **PRIORITAIRE** -- cobra/viper/bubbletea |
| UX patterns | `references/ux-patterns.md` | Progress bars, colors, help, errors |
| **NE PAS APPLIQUER** | `references/node-cli.md` | Pas de Node CLI prod |
| **NE PAS APPLIQUER** | `references/python-cli.md` | Python tres minoritaire LIA-SEC |

## 3. Templates LIA-SEC essentiels

### 3.1 Go cobra subcommand

```go
package cmd
import (
    "fmt"; "os"
    "github.com/spf13/cobra"
)

var flagDryRun, flagVerbose bool

var myActionCmd = &cobra.Command{
    Use:   "myaction <target>",
    Short: "One-line description",
    Long:  "Multi-line description with examples...",
    Args:  cobra.ExactArgs(1),
    RunE: func(cmd *cobra.Command, args []string) error {
        if err := validateTarget(args[0]); err != nil { return fmt.Errorf("invalid: %w", err) }
        n, err := doAction(args[0], flagDryRun, flagVerbose)
        if err != nil { return err }
        fmt.Fprintf(os.Stdout, "OK: processed %d items\n", n)
        return nil
    },
}

func init() {
    myActionCmd.Flags().BoolVar(&flagDryRun, "dry-run", false, "Show without doing")
    myActionCmd.Flags().BoolVarP(&flagVerbose, "verbose", "v", false, "Verbose output")
    rootCmd.AddCommand(myActionCmd)
}
```

### 3.2 Bash script strict (LIA-SEC)

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# R8 -- secrets via env
LIA_DB_PASS="${LIA_DB_PASS:-${PGPASSWORD:-}}"
LIA_DB_USER="${LIA_DB_USER:-lia_admin}"
LIA_DB_NAME="${LIA_DB_NAME:-lia_scan}"
LIA_DB_HOST="${LIA_DB_HOST:-localhost}"

log_info()  { printf '[INFO]  %s\n' "$*" >&2; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }
die()       { log_error "$@"; exit 1; }

psql_lia() {
    PGPASSWORD="$LIA_DB_PASS" psql -h "$LIA_DB_HOST" -U "$LIA_DB_USER" -d "$LIA_DB_NAME" "$@"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") <arg> [OPTIONS]
Options:
  --dry-run    Show without executing
  -h, --help   Show this help
EOF
}

DRY_RUN=0; ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -*) die "unknown option: $1" ;;
        *)  ARG="$1"; shift ;;
    esac
done
[ -z "$ARG" ] && { usage >&2; exit 2; }

trap 'log_error "interrupted"; exit 130' INT TERM

log_info "starting ARG=$ARG dry_run=$DRY_RUN"
# ... main work
log_info "done"
```

### 3.3 Confirm destructive action

```go
func confirmDestructive(action string, yes bool) error {
    if yes { return nil }
    fmt.Fprintf(os.Stderr, "About to %s. Continue? [y/N] ", action)
    var resp string
    fmt.Fscanln(os.Stdin, &resp)
    if resp != "y" && resp != "Y" { return fmt.Errorf("aborted") }
    return nil
}
```

```bash
confirm_destructive() {
    [ "${YES:-0}" = "1" ] && return 0
    printf "About to %s. Continue? [y/N] " "$1" >&2
    read -r resp
    case "$resp" in y|Y) return 0 ;; *) die "aborted" ;; esac
}
```

### 3.4 Output format Go (table / json)

```go
switch flagOutput {
case "json": json.NewEncoder(os.Stdout).Encode(items)
default:
    w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
    defer w.Flush()
    fmt.Fprintln(w, "ID\tNAME\tSTATUS")
    for _, it := range items { fmt.Fprintf(w, "%s\t%s\t%s\n", it.ID, it.Name, it.Status) }
}
```

### 3.5 Completion bash (cobra)

```bash
lia_recette completion bash | sudo tee /etc/bash_completion.d/lia_recette > /dev/null
source /etc/bash_completion.d/lia_recette
```

## 4. Anti-patterns interdits

| INTERDIT | A la place |
|----------|-----------|
| Secret en argv (`--password "xxx"`) | env var (R8) |
| `bash` sans `set -euo pipefail` | strict mode toujours |
| Couleurs ANSI sans test TTY | `[ -t 1 ]` ou `isatty.IsTerminal` |
| Pas de `--help` ni `--version` | obligatoire (cobra le fait gratis) |
| Hardcode chemins absolus | env var / flag / `$(dirname "$0")` |
| `rm -rf $VAR` sans validation | `[ -n "$VAR" ] && [ -d "$VAR" ]` AVANT |
| `eval "$user_input"` | jamais |
| Destructive sans confirm + `--yes` flag | toujours confirmer interactif |
| Emojis (R10) | `[OK]` / `[FAIL]` / `[INFO]` |
| `kill -9` orphan | `cleanup_services.sh kill` (R9) |
| `go build .` direct | `build_secure_lia.sh` (R16) |
| Pas de `LogSystemEvent` actions critiques | logger DB events si tracable requis |

## 5. Output template

```markdown
# CLI Change : <tool>/<command> -- YYYY-MM-DD
## Contexte
- Outil : `lia_recette` (etendre) | nouveau `lia_xxx`
- Commande / use case

## Design
- Args / Flags / Exit codes / Output (table+json)

## Implementation
- Fichiers : `cmd/<tool>/cmd/<sub>.go` ou `scripts/<tool>.sh`

## Polish
- Completion bash/zsh genere
- `<tool> --help` rendu OK
- Doc : `_alire/01_DOCUMENTATION/user-guides/<tool>_user_en.md`

## Test
- `time <tool> --version` < 50ms
- Cas erreur : invalid arg => exit 2 + message clair
```

## 6. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 | 8/10 | Workflow 5 phases respecte |
| C2 | 9/10 | Help text complet AVANT code ; reuse cobra existant si possible |
| C3 | 7/10 | Si UX confused -> revoir naming flags |
| C4 | 8/10 | bash strict mode + isatty AVANT couleurs |
| C5 | 8/10 | Doc user-guide + completion + plan + RETEX |
