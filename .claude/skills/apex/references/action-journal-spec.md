# Action Journal Specification — APEX v4.0

Per-step structured logging for full auditability of APEX sessions.
Complements `decision_log.jsonl` (decisions only) with granular action tracking.

## Table of Contents

1. Journal Format
2. When to Log
3. Staging Protocol
4. Manifeste JSONL
5. FILE_TRACKER v2 Enhancements

---

## 1. Journal Format

After every significant action within an APEX step, append to the session journal:

```
_alire/temp/apex/{task-id}/action_journal.jsonl
```

One JSON line per action:

```json
{
  "timestamp": "2026-04-02T14:30:00Z",
  "session": "apex-20260402-remediation-export",
  "phase": "EXECUTE",
  "step": 3,
  "agent_role": "EXECUTOR",
  "action": "EDIT_FILE",
  "tool": "Edit",
  "input": "crates/gateway/src/remediation_tracking.rs:245",
  "output": "Added exportToCSV handler (32 LOC)",
  "autonomy": "AUTONOMOUS",
  "approval": "N/A",
  "security": "CLEAR",
  "status": "success",
  "file": "crates/gateway/src/remediation_tracking.rs"
}
```

### Field Definitions

| Field | Type | Values |
|-------|------|--------|
| timestamp | ISO 8601 UTC | Auto-generated |
| session | string | `apex-{YYYYMMDD}-{task-slug}` |
| phase | enum | INIT, PREFLIGHT, ANALYZE, PLAN, EXECUTE, VALIDATE, EXAMINE, RESOLVE, TESTS, FINISH |
| step | int | Step number within phase (1-based) |
| agent_role | enum | ORCHESTRATOR, COLLECTOR, ANALYST, PLANNER, EXECUTOR, MEMORY, LIBRARIAN |
| action | string | Verb describing the action (EDIT_FILE, CREATE_FILE, RUN_BUILD, RUN_TEST, DELEGATE_AGENT, READ_FILE, SEARCH_CODE, LOG_DECISION, REPLAN) |
| tool | string | Claude Code tool used (Read, Edit, Write, Bash, Grep, Glob, Agent, or "manual") |
| input | string | Summary of input (file:line, command, query) |
| output | string | Summary of result (what changed, what was found) |
| autonomy | enum | AUTONOMOUS, SUPERVISED |
| approval | string | User approval ID or "N/A" |
| security | string | CLEAR or ALERT:{description} |
| status | enum | success, partial, failure |
| file | string | Primary file affected, or null |

### Bash Helper

```bash
log_apex_action() {
  local JOURNAL="_alire/temp/apex/${APEX_SESSION}/action_journal.jsonl"
  echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"session\":\"${APEX_SESSION}\",\"phase\":\"$1\",\"step\":$2,\"agent_role\":\"$3\",\"action\":\"$4\",\"tool\":\"$5\",\"input\":\"$6\",\"output\":\"$7\",\"autonomy\":\"$8\",\"approval\":\"N/A\",\"security\":\"CLEAR\",\"status\":\"$9\",\"file\":\"${10}\"}" >> "$JOURNAL"
}
```

---

## 2. When to Log

### ALWAYS log (every phase)

- File creation, modification, or deletion
- Build/test execution and result
- Agent delegation and response
- Gate pass/fail
- Replanification trigger

### NEVER log (noise reduction)

- File reads during exploration (ANALYZE phase reads dozens of files)
- Grep/Glob searches that return no results
- Internal reasoning steps
- Formatting decisions

### Threshold Rule

If unsure: log if the action changes state (file, build, plan) or triggers a decision. Skip if the action is pure observation.

---

## 3. Staging Protocol

All APEX intermediate artifacts go through staging before archival.

### Staging Directory

```
_alire/temp/apex/{task-id}/
```

### File Naming Convention

```
{PHASE}_{ITEM}_{STATUS}.{ext}
```

Where:
- PHASE: 00-init, 01-analyze, 02-plan, 03-execute, 04-validate, 05-examine, 06-resolve, 07-tests, 08-run-tests, 09-finish
- ITEM: descriptive name (health-scan, dependency-map, plan, diff-review, etc.)
- STATUS: RAW (first draft), DRAFT (reviewed), FINAL (gate passed), REJECTED (failed gate)

### Examples

```
_alire/temp/apex/remediation-export/
  00-init_context_FINAL.md
  01-analyze_dependency-map_FINAL.md
  01-analyze_health-scan_FINAL.md
  02-plan_implementation_DRAFT.md
  02-plan_implementation_FINAL.md        # After user approval
  03-execute_changes_RAW.md
  04-validate_diff-review_FINAL.md
  05-examine_adversarial_FINAL.md
  09-finish_retex_FINAL.md
  action_journal.jsonl
  FILE_TRACKER.json
```

### Promotion Rules

- RAW -> DRAFT: After self-review (VALIDATE phase)
- DRAFT -> FINAL: After gate passes or user approval
- Any -> REJECTED: After gate failure (keep for RETEX analysis)
- NEVER delete REJECTED files — they inform future replanification

---

## 4. Manifeste JSONL

Track all files produced during an APEX session in a machine-readable manifeste:

```
_alire/temp/apex/{task-id}/manifeste.jsonl
```

One line per file:

```json
{"timestamp":"2026-04-02T14:30:00Z","file":"crates/gateway/src/remediation_export.rs","action":"CREATED","phase":"EXECUTE","loc":145,"status":"FINAL","gate":"build_pass"}
{"timestamp":"2026-04-02T14:35:00Z","file":"crates/gateway/tests/remediation_export.rs","action":"CREATED","phase":"TESTS","loc":89,"status":"FINAL","gate":"test_pass"}
{"timestamp":"2026-04-02T14:40:00Z","file":"crates/gateway/Cargo.toml","action":"MODIFIED","phase":"EXECUTE","loc":1,"status":"FINAL","gate":"build_pass"}
```

### Fields

| Field | Description |
|-------|-------------|
| timestamp | When the file action occurred |
| file | Relative path from project root |
| action | CREATED, MODIFIED, DELETED, DISABLED |
| phase | APEX phase that produced this change |
| loc | Lines of code added/modified |
| status | FINAL, DRAFT, REJECTED |
| gate | Gate that validated this change (build_pass, test_pass, manual_review) |

### Usage

The manifeste enables:
- Post-session audit: exactly what changed, when, validated by what gate
- RETEX analysis: correlate failures with specific files/phases
- Rollback: identify all files from a specific phase for selective revert

---

## 5. FILE_TRACKER v2 Enhancements

Existing FILE_TRACKER.json (from audit-pdca) is enhanced with agent metadata:

### New Fields

```json
{
  "session": {
    "id": "apex-20260402-remediation-export",
    "skill_version": "4.0",
    "status": "IN_PROGRESS",
    "agent_architecture": "multi-role",
    "autonomy_mode": "SUPERVISED"
  },
  "roles_activated": ["COLLECTOR", "ANALYST", "PLANNER", "EXECUTOR", "LIBRARIAN"],
  "delegation_count": 3,
  "delegations": [
    {
      "step": 1,
      "agent_type": "Explore",
      "role": "COLLECTOR",
      "status": "SUCCESS",
      "anomalies": "NONE"
    }
  ],
  "quality_hooks": {
    "QH-A1_integrity_checks": 5,
    "QH-A2_naming_validations": 12,
    "QH-A3_output_format_checks": 3,
    "QH-A4_supervised_approvals": 2,
    "QH-A5_context_offloads": 0
  },
  "security_alerts": [],
  "recovery": {
    "next_step": "EXECUTE",
    "last_gate_passed": "PLAN",
    "replan_count": 0
  },
  "stats": {
    "files_created": 2,
    "files_modified": 5,
    "files_deleted": 0,
    "gates_passed": 4,
    "gates_failed": 1,
    "total_actions_logged": 23
  }
}
```

### Update Rules

- Update `recovery` after each phase completion
- Increment `quality_hooks` counters as hooks fire
- Append to `delegations[]` when Agent tool is used
- Append to `security_alerts[]` on any ALERT
- Recalculate `stats` at FINISH phase
