# Phase 0 -- INIT

**Goal:** Lock the scope, create the working directory, bootstrap the tracking files, present G1 (scope gate) to the user.

**Complexity:** MODERATE
**Dependencies:** none
**Output:** working directory + PLAN.md + README.md + decision_log.jsonl seeded + scope_intake.md

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 0.1 | Scope intake (ask user the 8 questions below) | conversation | All 8 answers captured |
| 0.2 | Create working directory + skeleton | Bash | `ls` returns the 6 expected subdirs |
| 0.3 | Write README.md from template | Write | File exists, mentions resume protocol |
| 0.4 | Write PLAN.md from template | Write | File exists, all phases unchecked, status EN_COURS |
| 0.5 | Seed decision_log.jsonl with phase 0 entry | Bash | `jq` validates the JSON line |
| 0.6 | Write scope_intake.md (the 8 answers) | Write | Document captures every answer + date |
| 0.7 | Present G1 Scope gate to user | conversation | User answers OK / valide / go |

## Scope intake (the 8 questions) -- ASK ALL OF THEM

Do NOT proceed without explicit answers. If the user is vague, ask a follow-up. Defaults are NOT assumptions -- only use them if the user says "use the default".

| # | Question | Default | Why it matters |
|---|----------|---------|---------------|
| 1 | What product is the pitch for? (full name + slug) | none | Names the working dir, drives all phase 1 inventory |
| 2 | Who is the audience? (deep-tech VC, generalist VC, angels, strategic, family office, public funding) | deep-tech VC | Drives narrative tone (technical vs vision-led) |
| 3 | What round and target amount? (pre-seed, seed, series A, bridge, grant) | seed, EUR 1-2M | Drives the "ask" slide and milestones |
| 4 | What geography is the round? (FR, EU, US, global) | EU | Drives competitor selection and regulatory framing |
| 5 | How many slides? | 20 | Sets the outline contract |
| 6 | Which competitors must be included by name? | none, ask the user | Cannot research competitors blind |
| 7 | Existing brand assets? (logo, color palette, .pptx template) | none, propose theme-factory cyber-pro | Drives phase 5 styling |
| 8 | Hard deadline? (date) | none | Drives parallelization choices in phases 1+2 |

## Bonus question (do not block on it)

- Confidentiality: can we publish real product metrics (route count, table count, customer count) or do we stay vague?

## Bash bootstrap (template)

```bash
PRODUCT_SLUG="{ask the user}"
DATE=$(date +%Y-%m-%d)
PITCH_DIR="_alire/tracking/investor_pitch_${PRODUCT_SLUG}_${DATE}"

mkdir -p "${PITCH_DIR}"/{research,platform/screenshots,positioning,deliverables,sources_raw}

# Then Write README.md, PLAN.md, scope_intake.md from templates
# Then seed decision_log.jsonl
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"investor-pitch","action":"PHASE_0_INIT","reasoning":"Working directory created, scope captured","alternatives_rejected":[],"outcome":"PITCH_DIR ready","confidence":"high","plan_ref":"'${PITCH_DIR}'/PLAN.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

## G1 Scope gate -- exact wording to send to user

```
G1 SCOPE LOCK

Product : {answer}
Audience : {answer}
Round : {answer}
Geography : {answer}
Slides : {answer}
Competitors to include : {answer}
Brand assets : {answer}
Deadline : {answer}

Working directory created at : {PITCH_DIR}

Reply "valide" or "OK" to proceed to phase 1 DISCOVERY.
Reply with corrections if anything is wrong -- I will update the scope before any research.
```

NEVER auto-progress past G1.

## Anti-patterns in this phase

- Skipping a question because "the user already mentioned it earlier" -- re-confirm explicitly
- Picking a default without saying so
- Creating the working directory under a different path than the canonical one
- Forgetting to seed decision_log.jsonl (breaks future resume)
