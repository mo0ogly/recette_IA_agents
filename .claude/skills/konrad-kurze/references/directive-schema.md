# Konrad Directive (KD) -- Schema

A KD directive is a structured JSON file written under
`_alire/02_LOGS/Journals/meta/directives/KD-{YYYYMMDD-HHMMSS}.json`.

It is consumed by /apex (Phase THINK 2d critique) and /audit-pdca (Phase P.1 learning).

## Table of contents

1. Required fields
2. Optional fields
3. Approval matrix
4. Risk-level rules
5. Lifespan rules
6. Validation expectations
7. Lifecycle (PENDING / APPROVED / APPLIED / REJECTED / EXPIRED)

---

## 1. Required fields

```json
{
  "directive_id": "KD-{YYYYMMDD-HHMMSS}",
  "issued_at": "ISO-8601",
  "primary_target": "Malcador | LemanRuss | both",
  "scope": {
    "module": "string -- e.g. iso27005, smsi",
    "cycle_ref": "string -- e.g. cycle_003 or apex-session-id",
    "subtask_or_wave": "string or null"
  },
  "classification": ["CONVENTION_CONFLICT", "..."],
  "confidence": 0.0,
  "risk_level": "LOW | MEDIUM | HIGH",
  "requires_approval": true,
  "injection": {
    "operation": "ADD | MODIFY | REMOVE | BYPASS_TEMPORARILY",
    "lifespan": "once | limited:{cycles} | permanent",
    "payload": "string or structured object that the target consumes"
  },
  "expected_impact": {
    "score_delta": "+N | unknown",
    "domains_affected": ["security", "code_hygiene", "..."],
    "confidence": 0.0
  },
  "failure_cluster": {
    "cluster_id": "FS-{sha256[:8]}",
    "occurrences": 0,
    "first_seen": "ISO-8601",
    "last_seen": "ISO-8601"
  },
  "circuit_breaker": {
    "demote_after_failures": 3,
    "fallback": "observer_mode"
  },
  "evidence_refs": [
    "file:line | log:timestamp | scorecard:check_id"
  ]
}
```

## 2. Optional fields

```json
{
  "evidence_gaps": ["missing PLAN_*.md", "..."],
  "alternatives_rejected": [
    {"option": "...", "reason": "..."}
  ],
  "supersedes": "KD-... -- previous directive replaced",
  "verdict_override": "OBSERVER_MODE_ONLY -- only when QK aggregate < 0.4",
  "user_note_required": "string -- operator must read before approving"
}
```

## 3. Approval matrix

| Operation | risk_level | requires_approval | Rationale |
|-----------|------------|-------------------|-----------|
| ADD       | LOW        | false             | Adding a check / log / probe is reversible |
| ADD       | MEDIUM     | true              | Adds a constraint that may slow cycles |
| ADD       | HIGH       | true              | Adds a permanent rule; verify with user |
| MODIFY    | any        | true (always)     | Mutates an existing skill / hook |
| REMOVE    | any        | true (always)     | Reversible only via git, costly |
| BYPASS    | any        | true (always)     | Lifespan must be limited, not permanent |

A directive with `risk_level: LOW` AND `operation: ADD` is the only autonomous path.
All others are emitted with `requires_approval: true` regardless of confidence.

## 4. Risk-level rules

Compute the base risk:

| Signal | Effect |
|--------|--------|
| `expected_impact.domains_affected` includes `security` | risk_level = at least MEDIUM |
| `injection.operation` is REMOVE or BYPASS | risk_level = at least MEDIUM |
| `injection.lifespan = permanent` and operation != ADD-LOW | risk_level = HIGH |
| Classification includes LEMANRUSS_TAINT | risk_level = at least MEDIUM |
| QK-02 (testability) failed | upgrade one step |
| QK-03 (non-regression) failed | upgrade one step (and force approval) |

Final risk_level = max(base, upgrades).

## 5. Lifespan rules

- `once`: applies to the next single cycle of the target only.
- `limited:N`: applies for the next N cycles, decremented at each cycle boundary.
- `permanent`: applies until explicitly superseded by a later KD or removed by user.

`permanent` is FORBIDDEN unless:
- operation is ADD
- risk_level is LOW
- user has explicitly approved (recorded via approval log)

A BYPASS injection is FORBIDDEN as `permanent`. Konrad enforces this at emission time.

## 6. Validation expectations

A KD directive is malformed and MUST be rejected (do not write to disk) if:

- `evidence_refs` is empty
- Any `evidence_refs` entry does not match a real artefact
- `confidence` is outside [0.0, 1.0]
- `failure_cluster.cluster_id` does not start with `FS-` followed by 8 hex chars
- `injection.lifespan = permanent` and approval matrix says approval required and `requires_approval = false`
- `expected_impact.score_delta` is "+0" -- a directive with no expected gain is meaningless

The skill's VERIFICATION GATE in SKILL.md enforces these rules.

## 7. Lifecycle

```
PENDING_APPROVAL  -> approved by user            -> APPROVED
APPROVED          -> consumed by target          -> APPLIED
APPLIED           -> next cycle effect measured  -> SUCCESS | NOOP | REGRESSION
REGRESSION        -> superseded by new KD        -> SUPERSEDED
PENDING_APPROVAL  -> rejected by user            -> REJECTED
APPROVED          -> lifespan exhausted          -> EXPIRED
```

State transitions are appended to `_alire/02_LOGS/Journals/meta/directives/KD-{id}.history.jsonl`:

```json
{"timestamp":"ISO","state":"APPROVED","actor":"user","note":"..."}
```

The skill writes the initial PENDING_APPROVAL state on emission. All other transitions are written either by the user (approval / rejection) or by the consuming skill (apex / audit-pdca on consumption).
