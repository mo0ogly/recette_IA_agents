# Konrad-Kurze -- Memory Schema

Two persistent files under `_alire/02_LOGS/Journals/meta/`:

- `K_KURZE_LEARNING_LOG.json` -- accumulated knowledge of failure clusters
- `K_KURZE_SELF_DOUBT.json` -- explicit confidence caps from past misdiagnoses

## Table of contents

1. K_KURZE_LEARNING_LOG.json
2. K_KURZE_SELF_DOUBT.json
3. Validation rules (run by `validate_memory.py`)
4. Quarantine
5. Pruning policy

---

## 1. K_KURZE_LEARNING_LOG.json

Persistent map keyed by `cluster_id`. Each entry tracks one failure cluster across sessions.

```json
{
  "FS-abc12345": {
    "first_seen": "2026-04-25T17:00:00Z",
    "last_seen": "2026-04-25T17:30:00Z",
    "occurrences": 3,
    "classifications": ["CONVENTION_CONFLICT"],
    "directives_emitted": ["KD-20260425-170000", "KD-20260425-173000"],
    "outcomes": {
      "APPLIED": 1,
      "SUCCESS": 1,
      "REGRESSION": 0,
      "REJECTED": 1
    },
    "evidence_signature": [
      "sigma-react-frontend/src/components/foo/Bar.tsx",
      "scorecard:HYG-03"
    ],
    "global_learning_mode": false,
    "notes": "string -- short narrative, never auto-generated marketing language"
  }
}
```

### When to update

- New cluster seen: insert with `occurrences: 1`, `first_seen = last_seen = now`.
- Existing cluster reopened: increment `occurrences`, update `last_seen`, append directive id.
- Outcome of a previous directive becomes known: update `outcomes` counters.
- `occurrences >= 3`: set `global_learning_mode: true` (stable pattern, future runs may boost confidence).

## 2. K_KURZE_SELF_DOUBT.json

Persistent list of confidence caps tied to clusters where Konrad has been wrong.

```json
{
  "caps": [
    {
      "cluster_id": "FS-abc12345",
      "max_confidence": 0.7,
      "reason": "User rejected 3 directives in a row claiming CONVENTION_CONFLICT, root cause was META_DATA_AMNESIA",
      "set_at": "2026-04-25T17:30:00Z",
      "set_by_session": "konrad-kurze-001",
      "review_after": "2026-05-25T00:00:00Z"
    }
  ]
}
```

### When to update

- 3 rejections by user on the same cluster -> add cap at 0.5.
- 1 REGRESSION recorded after APPLIED -> add cap at 0.7.
- 30 days passed AND no further rejection -> remove cap (manual review).

The `review_after` field is informational. Konrad does not auto-remove caps.

## 3. Validation rules (run by `scripts/validate_memory.py`)

Before any write to `K_KURZE_LEARNING_LOG.json` or `K_KURZE_SELF_DOUBT.json`, the candidate JSON MUST pass all 3 rules:

### Rule A -- Internally generated

The candidate must contain at least one `evidence_refs` entry produced by THIS run. The validator checks:

- `evidence_refs` exists and is non-empty
- Each entry matches one of: `^[a-zA-Z0-9_/.-]+:\d+$` (file:line), `^scorecard:[A-Z]+-\d+$`, `^decision_log:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`, or `^cycle_\d+/[a-zA-Z0-9_.-]+$`

### Rule B -- No contradiction with prior entries

For each existing entry on the same `cluster_id`:

- If the candidate's `classifications` is fully disjoint from the existing one AND the candidate does not include `note: "supersedes ..."`: REJECT
- If the candidate's `outcomes` decrements an existing counter: REJECT
- If the candidate sets `global_learning_mode: false` while the existing entry has `true` AND `occurrences >= 3`: REJECT

### Rule C -- Recurring pattern relevance

The candidate must satisfy at least one of:

- `occurrences >= 2` after this update
- The `cluster_id` already exists in `K_KURZE_LEARNING_LOG.json`
- The candidate includes a `note` justifying first-occurrence inclusion (manual override, must be explicit)

If A, B, or C fails: write the candidate to `_alire/02_LOGS/Journals/meta/quarantine/{timestamp}_quarantine.json` and exit non-zero.

## 4. Quarantine

Quarantined files preserve the candidate verbatim plus a header:

```json
{
  "quarantined_at": "ISO",
  "session": "konrad-kurze-{id}",
  "rule_failed": "A | B | C",
  "details": "...",
  "candidate": { ... }
}
```

A quarantine entry is NEVER promoted to the main log automatically. A user must review quarantined entries (or a future Konrad run with explicit override).

If 3 quarantines occur in the same session: STOP, escalate to user with the 3 candidates.

## 5. Pruning policy

The learning log is append-mostly. Pruning is rare and explicit:

- `K_KURZE_LEARNING_LOG.json` is never auto-pruned. Entries with `occurrences = 1` and `last_seen` older than 180 days are candidates for manual archive into `_alire/02_LOGS/Journals/meta/archive/learning_log_{YYYY-MM}.json`.
- `K_KURZE_SELF_DOUBT.json` caps with `review_after < now` and no recent occurrence are candidates for removal -- but only by user action, never silently by Konrad.

Konrad NEVER deletes a cluster entry that has at least one `outcomes.SUCCESS = 1`. That entry is institutional knowledge.
