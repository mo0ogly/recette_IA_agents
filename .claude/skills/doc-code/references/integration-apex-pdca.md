# Integration Guide -- doc-code with APEX / PDCA / audit-pdca

How doc-code plugs into the broader LIA-SEC skill ecosystem.

---

## Trigger Points

### From APEX

doc-code is invoked automatically after APEX step 09 (FINISH):

```
APEX FINISH:
  IF new handlers created OR new components created:
    /doc-code {module} --update
  IF new API routes registered:
    /doc-code {module} --update + update .claude/rules/api-reference.md
```

Manual invocation from APEX:
```
/apex -t -pr "implement feature X"
# ... APEX completes ...
/doc-code {module}   # Document what was built
```

### From audit-pdca

doc-code is called in phase A (Act) after fixes are applied:

```
audit-pdca Phase A:
  A.1: Apply fixes from brainstorm recommendations
  A.2: /doc-code {fixed_modules} --update   # Update docs for fixed code
  A.3: Update DASHBOARD.md
```

### From PDCA cycles

Every PDCA cycle MUST include a documentation task (feedback: `feedback_pdca_include_docs.md`):

```
PLAN:
  - [ ] Task N: Update documentation for {module}

DO:
  - /doc-code {module} --update

CHECK:
  - QA score >= 80
  - _alire/01_DOCUMENTATION/INDEX.md updated

ACT:
  - Archive obsolete docs
  - Surface anomalies to RETEX
```

---

## Existing Docs Protocol (CRITICAL)

### Step 1: CHECK before creating

BEFORE generating any documentation, ALWAYS check what exists:

```bash
# Check _alire/01_DOCUMENTATION/ directory
find _alire/01_DOCUMENTATION/ -name "*{module}*" -type f 2>/dev/null

# Check _alire/01_DOCUMENTATION/
find _alire/01_DOCUMENTATION/ -name "*{module}*" -type f 2>/dev/null

# Check metadata index
python3 .claude/skills/doc-code/scripts/doc_classifier.py list _alire/01_DOCUMENTATION/ 2>/dev/null

# Check git history for deleted/moved docs
git log --diff-filter=D --name-only -- "_alire/01_DOCUMENTATION/*{module}*" 2>/dev/null
```

### Step 2: DECIDE action

| Finding | Action |
|---------|--------|
| No doc exists | CREATE from standard template |
| Doc exists and current | SKIP (no work needed) |
| Doc exists but stale | UPDATE: read code, identify deltas, bump version |
| Doc exists but wrong | FIX: correct errors, bump PATCH, flag in RETEX |
| Doc in wrong location | MOVE to correct directory per librarian pattern |
| Multiple docs for same module | CONSOLIDATE: merge into one, archive duplicates |
| Doc references deleted code | ARCHIVE the doc, create new if code relocated |

### Step 3: ARCHIVE obsolete (NEVER delete)

```bash
# Archive pattern: move to _alire/01_DOCUMENTATION/archive/ with version and date
mv _alire/01_DOCUMENTATION/api/{module}_api_en.md \
   _alire/01_DOCUMENTATION/archive/{module}_api_en_v{OLD_VERSION}_archived_{YYYY-MM-DD}.md

# Update metadata
python3 .claude/skills/doc-code/scripts/doc_classifier.py status \
  _alire/01_DOCUMENTATION/archive/{module}_api_en_v{OLD_VERSION}_archived_{YYYY-MM-DD}.md ARCHIVED

# Log the archival
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"doc-code","action":"ARCHIVE_DOC","reasoning":"superseded by v{NEW}","alternatives_rejected":["delete"],"outcome":"archived to _alire/01_DOCUMENTATION/archive/","confidence":"high","plan_ref":null}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

**RULE: NEVER `rm` a documentation file. Always archive.**

### Step 4: TODO for problems

If during doc generation, problems are found that cannot be fixed:

```markdown
<!-- DOC-TODO: {YYYY-MM-DD} -->
<!-- Issue: {description of the problem} -->
<!-- Source: {file:line where the problem was found} -->
<!-- Action needed: {what needs to happen} -->
<!-- Blocker: {why this cannot be fixed now} -->
```

These TODOs are:
1. Listed in the Recette report under "Open Issues"
2. Surfaced in the RETEX anomaly report
3. Tracked until resolved in a future cycle

---

## Skill Chaining Reference

| After this skill... | Chain to doc-code when... |
|---------------------|--------------------------|
| `/apex` | New code was created (handlers, components, routes) |
| `/audit-pdca` | Fixes were applied that change documented behavior |
| `/create-lia-rule` | New rule created (document in rules guide) |
| `/debug-go` | Fix revealed undocumented behavior |
| `/debug-react` | Fix revealed undocumented component |
| `/create-ui-help` | New UI help entry created (reference in user guide) |
| `/spec-builder` | Spec finalized (generate ARCH doc from spec) |
| `/fingerprint-lab-improve` | New fingerprint patterns (update tech doc) |

| doc-code chains to... | When... |
|-----------------------|---------|
| `/create-ui-help` | Dashboard/page component without HelpButton |
| `doc_classifier.py` | Every doc created or updated (metadata) |
| `generate_mermaid.py` | Architecture/sequence/ER/component diagrams |
| `generate_word_doc.py` | User requests .docx export |

---

## Update Mode (`--update`)

When doc-code is called with `--update`:

1. OBSERVE: find existing doc, read metadata, compare git log dates
2. ORIENT: identify changed code sections since last doc update
3. DECIDE: which sections need rewriting vs which are still current
4. ACT: update only changed sections, bump version appropriately
5. QA: verify updated doc against current code

Version bump rules:
- Only metadata/formatting changed: PATCH (1.0.0 -> 1.0.1)
- New endpoints/components documented: MINOR (1.0.1 -> 1.1.0)
- Major rewrite or architecture change: MAJOR (1.1.0 -> 2.0.0)

---

## Read the Code Rule

**ABSOLUTE RULE: Read the code, never invent.**

Every claim in documentation MUST be verifiable by reading a file:

```
WRONG: "The compliance module handles 30+ endpoints"
RIGHT: "The compliance module handles 32 endpoints (counted from compliance_*.go handlers)"

WRONG: "The dashboard uses React hooks for state management"
RIGHT: "AuditDashboard.tsx uses useState (3), useEffect (2), useCallback (1)"
```

The QA agent verifies claims by reading actual files. Invented documentation fails QA.
