# Recette Live Rule - Infrastructure Reference

> Detailed paths, VM setup, collector pipeline, and data formats.
> Referenced from SKILL.md v3.0. Do not duplicate workflow logic here.

---

## Paths (FIXED - DO NOT CHANGE)

### Windows

```powershell
# === REPOS ===
$RULES_ROOT    = "C:\Users\pizzif\Documents\GitHub\rules"              # IIS10, EXCHANGE
$ADDS_ROOT     = "C:\Users\pizzif\Documents\GitHub\lia-security-platform-v2\lia_rules\rule_analysis\ADDS"
$COLLECTS_ROOT = "C:\Users\pizzif\Documents\GitHub\collects"           # Collector scripts
$LAB_ROOT      = "C:\Users\pizzif\Documents\GitHub\ad_lab"             # Lab scripts + real data
$PLATFORM_ROOT = "C:\Users\pizzif\Documents\GitHub\lia-security-platform-v2"

# === GO ENGINE (compiled) ===
$LIA_TEST = "$PLATFORM_ROOT\lia-test.exe"   # lia-test --rule X.yml --events test_data.json --format txt
$LIA_SCAN = "$PLATFORM_ROOT\lia-scan.exe"   # lia-scan --multi --events data.xml --rules rules_dir/

# === COLLECTORS PER DOMAIN ===
$COLLECT_IIS      = "$COLLECTS_ROOT\iis\Collect-IIS.ps1"
$COLLECT_EXCHANGE = "$COLLECTS_ROOT\EXCHANGE\Collect-Exchange.ps1"
$COLLECT_ADDS_DIR = "C:\Share\collectors"    # On VM DC01-LAB (PowerShell Direct)

# === REAL DATA ===
$IIS_REAL_DATA      = "$COLLECTS_ROOT\iis\real_data\iis_cis_config.json"
$EXCHANGE_REAL_DATA = "$COLLECTS_ROOT\EXCHANGE\real_data\exchange_events.json"
$ADDS_REAL_DATA     = "$LAB_ROOT\collects\ADDS\real_data"  # XML collected from VM

# === VM LAB (PowerShell Direct) ===
$VM_NAME = "DC01-LAB"
$VM_CRED = Get-Credential -Message "AD Admin"  # or $cred if already loaded

# === VALIDATION SCRIPTS ===
$VALIDATE_RULES     = "$RULES_ROOT\validate_rules.ps1"
$GENERATE_TEST_DATA = "$RULES_ROOT\generate_test_data.ps1"
$DEPLOY_COLLECTORS  = "$LAB_ROOT\deploy_lia_collectors.ps1"

# === TRACEABILITY ===
$RECETTE_LOG = "$RULES_ROOT\RECETTE_LOG.jsonl"
$PLAN_DIR    = "$RULES_ROOT\_recette"
```

### Linux (VPS)

```bash
# === REPOS ===
PROJECT_ROOT="/home/mo0ogly/Bureau/vscode_lia_audit"
RULES_BASE="$PROJECT_ROOT/lia_rules/rule_analysis"
RECETTE_DIR="$PROJECT_ROOT/recette"

# === ENGINE ===
ENGINE="$PROJECT_ROOT/bin/lia_scan_engine"        # Compiled C/Go engine
LIA_TEST="$PROJECT_ROOT/bin/lia-test"             # If compiled from cmd/lia-test

# === REAL DATA ===
ADDS_REAL_DATA="$PROJECT_ROOT/collects/ADDS/real_data"

# === VALIDATION SCRIPTS (164 checks) ===
VALIDATE_ALL="$RECETTE_DIR/validate_rules_ALL.sh"
VALIDATE_RECIPE="$RECETTE_DIR/recette_rule_cli/validate_rules_recipe.sh"
VALIDATE_ULTIMATE="$RECETTE_DIR/validate_rules_ultimate.sh"
VALIDATE_COMPLETE="$RECETTE_DIR/validate_complete_rule.sh"

# === TRACEABILITY ===
TEMP_DIR="$PROJECT_ROOT/_alire/temp"              # NEVER /tmp/
```

---

## Lab AD (ad_lab/)

- **3 VMs** : DC01 (DC+CA+15 services), DC02 (RODC), DC-PARTNER (2nd forest)
- **90+ anomalies** injected by `populate/04a-04m`
- **60 collectors** : each finds at least one anomaly
- **Credentials** : `LAB\Administrator` / password in `config.ps1`
- **Share** : `\\192.168.0.10\Share` -> `C:\Share\` on VM
- **Excluded orchestrators** : `Run-LIAScan-Collectors.ps1`, `Discover-ADTargets.ps1`, `web_execution_wrapper.ps1`
- **Full collector-anomaly-source table** : see `ad_lab/README.md`

---

## Collector Pipeline (ADDS)

The collection infrastructure is ALREADY in place. Do not recreate it.

```
deploy_collectors.ps1    -> Deploys ~55 Collect-*.ps1 to C:\Share\collectors\ on VM
                            (Applies fix_collectors.ps1 automatically)
run_collectors.ps1       -> Orchestrator with menu (COMPLETE/AD/FAST)
                            Executes all C:\Share\collectors\*.ps1
                            Results in C:\Share\collectors_output\collect\AD01\YYYYMMDD\collect\
copy_collects.ps1        -> Retrieves DATA_*.xml from VM to ad_lab/collects/ADDS/real_data/
```

**Execution modes (run_collectors.ps1):**

| Mode | Description | Exclusions |
|------|-------------|------------|
| 1. COMPLETE | 60 collectors | None (production) |
| 2. AD ONLY | ~46 collectors | 9 remote (WMI/RPC) + ADCompleteTaxonomy |
| 3. FAST | ~45 collectors | + ADAcls (slow) |

### Collector Sources

**IMPORTANT: The zip ad.zip is OBSOLETE. The .ps1 files on the VM are the reference version.**

Two origins:
1. **60 Collect-*.ps1 deployed on VM** in `C:\Share\collectors\` (reference, already fixed)
2. **15 dedicated Collect-*.ps1** colocated with rules in `lia_rules/rule_analysis/ADDS/`
   Ex: `ADDS/SECU/A-Owner/Collect-Owner.ps1`, `ADDS/ARCH/A-ADUpdateBad/Collect-ADUpdateBad.ps1`

**Key collector: Collect-ADCompleteTaxonomy.ps1** -- produces standard files
(`*_DATA_Users.xml`, `*_DATA_Groups.xml`, `*_DATA_Computers.xml`, etc.)
matching `required_files.pattern` of most 405 ADDS rules.
Heaviest collector (10-15 min, full schema).

**To fix a collector: edit the source .ps1 DIRECTLY, NOT a wrapper.**

---

## Output Formats

Collectors produce two formats:

1. **CliXml UTF-16 LE** (`Export-Clixml`) -- Microsoft XML, parsable by lia-scan via ParseActiveDirectoryXML()
2. **JSON UTF-8 with BOM** (`ConvertTo-Json | Out-File`) -- Strip BOM before use with lia-test

```bash
# Detect and strip BOM on JSON
if [ "$(xxd -p -l 2 "$f")" = "efbb" ]; then
    tail -c +4 "$f" > "${f%.xml}.json"
fi
```

---

## data_source Principle

Each YAML rule contains a `data_source` block linking collector to expected file:

```yaml
data_source:
  type: collection
  collection_script: "Collect-PrivilegedGroupMembers.ps1"    # which .ps1 to execute
  script_location: "/conversion/.../Collect-PrivilegedGroupMembers.ps1"
  collection_type: "DEDICATED"                                # STANDARD or DEDICATED
  required_files:
    - pattern: "*_DATA_Groups.xml"                            # expected output file
      object_class: "privileged_members_count"                # ObjectClass to match
```

### File Naming

- YAML patterns use wildcard prefix: `*_DATA_Groups.xml`
- Collectors on VM produce in `C:\Share\collectors_output\collect\AD01\YYYYMMDD\collect\`
- Retrieved files are renamed `DATA_*.xml` (no prefix)
- For JSON+BOM: create a `.json` copy with BOM stripped for lia-test

### Rule-by-Rule Workflow (Real Data)

1. Read `data_source` from YAML -> identify `collection_script` and `pattern`
2. Check if matching file exists in `ad_lab/collects/ADDS/real_data/`
3. Match by **ObjectClass** (not filename): collector filenames do not match YAML patterns
4. If no file -> check if collector is deployed on VM -> execute -> retrieve
5. Test: `lia-test --rule X.yml --events REAL_FILE.json --format txt`
