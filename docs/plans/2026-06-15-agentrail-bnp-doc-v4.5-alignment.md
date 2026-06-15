# AgentRail x BNP doc v4.5 alignment -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the BNP Design Partner doc v4.5 coherent with the repo ground truth and current standards: remap OWASP tags to Agentic 2026, add 6 sensitive governed actions to the referential (118 -> 124), reframe the 94% citation as an identity-crypto differentiator, and tighten the gain ranges / risk column.

**Architecture:** Two phases. Phase 1 is repo-side and test-driven: the action catalog (`recette/platform/catalog/domains/*`) is the source of truth; `scripts/gen_annex_c_referential.py` holds `ANNEX_C_SOURCE` (a hardcoded tuple of Annex C rows) and ENRICHES each row from the catalog to produce `corpus/referentials/annex-c-governed-actions.json`. An action reaches the referential only if it is in BOTH the catalog AND `ANNEX_C_SOURCE`. Phase 2 edits the .docx (outside the repo, in `~/Downloads`) to match, verified by pandoc re-render + grep.

**Tech Stack:** Python stdlib (unittest), the governed-action catalog, `scripts/gen_annex_c_referential.py`, pandoc + the `docx` skill for the Word file.

**Design:** `docs/plans/2026-06-15-agentrail-bnp-doc-v4.5-alignment-design.md`

---

## Background the executor MUST read first

- Catalog model: `recette/platform/catalog/model.py` -- `Criticality {C1,C2,C3,C4}`,
  `RiskLevel {LOW,MEDIUM,HIGH,CRITICAL}`, `RISK_SCORE {LOW:1,MEDIUM:2,HIGH:3,CRITICAL:4}`,
  `ActionSpec(target_system, action_type, risk_level, criticality, verdict_privileged,
  verdict_default, privileged_roles, description)`.
- Domains are registered in `recette/platform/catalog/domains/__init__.py::DOMAIN_MODULES`
  (compliance and mcp ARE registered). Each domain module exports `TARGET_SYSTEM`
  and `ACTIONS`.
- `okta.py` has a `_escalate(action_type, criticality, risk_level, description)`
  helper = `verdict_privileged=ESCALATE, verdict_default=DENY, privileged_roles=("identity_admin",)`.
- `compliance.py` ALREADY defines `open_kyc_review` (C3, MEDIUM, escalate/deny,
  `compliance_admin`) but it is NOT in `ANNEX_C_SOURCE`, so it is absent from the
  referential. Adding it = one source row, no catalog change.
- Regenerate the referential with: `python -m scripts.gen_annex_c_referential`.
- Drift guard: `tests/test_annex_c_referential.py` (asserts JSON == fresh
  generation, `count == 118`, per-category counts) and `tests/test_action_criticality.py`.
- The 6 actions to add and their categories (one NEW category, "MCP / outils"):

| annex_c_action_type | category | target_system | action_type | crit | risk | catalog work |
|---------------------|----------|---------------|-------------|------|------|--------------|
| compliance.kyc.review_open | Juridique / conformite | compliance | open_kyc_review | C3 | MEDIUM | none (exists) |
| identity.token.revoke | Identite / acces | okta | revoke_token | C3 | MEDIUM | add (mirror revoke_api_key) |
| identity.delegation.assume | Identite / acces | okta | assume_delegation | C1 | CRITICAL | add (deny/deny, no role) |
| scm.secret.read | GitHub / DevOps | github | read_secret | C2 | HIGH | add |
| cloud.host.isolate | Cloud / infrastructure | cloud | isolate_host | C2 | HIGH | add |
| mcp.tool.invoke | MCP / outils | mcp | invoke_tool | C3 | HIGH | add (verify mcp.py shape) |

---

## PHASE 1 -- Repo: add 6 governed actions (TDD)

### Task 1: Expose the existing compliance KYC review action in the referential

**Files:**
- Modify: `scripts/gen_annex_c_referential.py` (the `ANNEX_C_SOURCE` tuple)
- Test: `tests/test_annex_c_referential.py`

**Step 1: Update the count test to the new target (write the failing expectation)**

In `tests/test_annex_c_referential.py`, change `test_count_is_118` to expect 124
(rename to `test_count_is_124`) and update both assertions to `124`. Also update
`test_category_counts` expected map: Identite/acces +2, GitHub/DevOps +1, Cloud/
infrastructure +1, Juridique/conformite +1, add "MCP / outils": 1.

**Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_annex_c_referential -v`
Expected: FAIL (count is still 118, categories mismatch).

**Step 3: Add the compliance source row**

In `ANNEX_C_SOURCE`, after the "Juridique / conformite" block, add:
```python
    (
        "Juridique / conformite",
        "Ouvrir une revue KYC",
        "compliance.kyc.review_open",
        "compliance",
        "open_kyc_review",
    ),
```

**Step 4: Regenerate + run**

Run: `python -m scripts.gen_annex_c_referential`
Run: `python3 -m unittest tests.test_annex_c_referential -v`
Expected: count now 119; still FAIL on count (target 124) -- that is expected,
the remaining 5 come in Tasks 2-5. (If you prefer green-between-tasks, stage the
test count bump to the end; otherwise proceed -- the suite goes green at Task 6.)

**Step 5: Commit**

```bash
git add scripts/gen_annex_c_referential.py corpus/referentials/annex-c-governed-actions.json tests/test_annex_c_referential.py
git commit -m "feat(referential): expose compliance KYC review in Annex C"
```

### Task 2: Add the two identity actions (token revoke + delegation assume)

**Files:**
- Modify: `recette/platform/catalog/domains/okta.py` (the `ACTIONS` tuple)
- Modify: `scripts/gen_annex_c_referential.py`
- Test: `tests/test_action_criticality.py`, `tests/test_annex_c_referential.py`

**Step 1: Write/extend the failing catalog test**

In `tests/test_action_criticality.py` add assertions:
```python
def test_token_revoke_is_c3(self):
    spec = load_catalog().get("okta", "revoke_token")
    self.assertIsNotNone(spec)
    self.assertEqual(spec.criticality, Criticality.C3)

def test_delegation_assume_is_c1_deny(self):
    spec = load_catalog().get("okta", "assume_delegation")
    self.assertIsNotNone(spec)
    self.assertEqual(spec.criticality, Criticality.C1)
    self.assertEqual(spec.verdict_privileged, PolicyVerdict.DENY)
    self.assertEqual(spec.verdict_default, PolicyVerdict.DENY)
```

**Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_action_criticality -v`
Expected: FAIL ("NoneType has no attribute criticality").

**Step 3: Add the catalog specs**

In `okta.py` `ACTIONS`, add the reversible defensive revoke (mirror `revoke_api_key`):
```python
    _escalate("revoke_token", Criticality.C3, RiskLevel.MEDIUM, "Revoke an issued token (defensive, reversible)."),
```
And the never-allowed delegation assumption (deny for everyone, no privileged
role -- construct ActionSpec directly, do not use `_escalate`):
```python
    ActionSpec(
        target_system=TARGET_SYSTEM,
        action_type="assume_delegation",
        risk_level=RiskLevel.CRITICAL,
        criticality=Criticality.C1,
        verdict_privileged=PolicyVerdict.DENY,
        verdict_default=PolicyVerdict.DENY,
        privileged_roles=(),
        description="Act under another agent's delegation outside the granted scope.",
    ),
```
Ensure `ActionSpec` is imported in `okta.py` (it imports `Criticality, RiskLevel`
already; add `ActionSpec` and confirm `PolicyVerdict` import).

**Step 4: Add the two source rows + regenerate**

In `ANNEX_C_SOURCE`, in the "Identite / acces" block add:
```python
    ("Identite / acces", "Revoquer un token", "identity.token.revoke", "okta", "revoke_token"),
    ("Identite / acces", "Agir sous la delegation d'un autre agent", "identity.delegation.assume", "okta", "assume_delegation"),
```
Run: `python -m scripts.gen_annex_c_referential`
Run: `python3 -m unittest tests.test_action_criticality -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add recette/platform/catalog/domains/okta.py scripts/gen_annex_c_referential.py corpus/referentials/annex-c-governed-actions.json tests/test_action_criticality.py
git commit -m "feat(catalog): add identity token-revoke (C3) and delegation-assume (C1 deny)"
```

### Task 3: Add scm.secret.read (github, C2)

**Files:** `recette/platform/catalog/domains/github_devops.py`, `scripts/gen_annex_c_referential.py`, tests.

**Step 1:** Add a failing assertion in `tests/test_action_criticality.py`:
`load_catalog().get("github", "read_secret")` is not None and is `Criticality.C2`.
**Step 2:** Run -> FAIL.
**Step 3:** Add to `github_devops.py` `ACTIONS` (mirror the domain's escalate helper
/ existing C2 entries like `modify_cicd_secrets`):
```python
# read a CI/CD secret outside the expected build context
<helper-or-ActionSpec>("read_secret", Criticality.C2, RiskLevel.HIGH, "Read a CI/CD secret value.")
```
Use whatever constructor the module already uses for escalate/deny C2 rows.
**Step 4:** Add source row `("GitHub / DevOps", "Lire un secret CI/CD", "scm.secret.read", "github", "read_secret")`, regenerate, run -> PASS.
**Step 5:** Commit `feat(catalog): add scm.secret.read (C2)`.

### Task 4: Add cloud.host.isolate (cloud, C2)

Same shape as Task 3 in `recette/platform/catalog/domains/cloud.py`:
- action_type `isolate_host`, C2, HIGH, escalate/deny, `cloud_admin`.
- source row `("Cloud / infrastructure", "Isoler un serveur", "cloud.host.isolate", "cloud", "isolate_host")`.
- failing test first, regenerate, PASS, commit `feat(catalog): add cloud.host.isolate (C2)`.

### Task 5: Add mcp.tool.invoke (mcp, C3)

**Files:** `recette/platform/catalog/domains/mcp.py`, `scripts/gen_annex_c_referential.py`, tests.

**Step 1:** First READ `mcp.py` to learn its `TARGET_SYSTEM` (expected `"mcp"`),
its helper, and `privileged_roles` convention. Add a failing test:
`load_catalog().get("mcp", "invoke_tool")` is `Criticality.C3`.
**Step 2:** Run -> FAIL.
**Step 3:** Add `invoke_tool` (C3, HIGH, escalate/deny) to `mcp.py` `ACTIONS`
using the module's own constructor.
**Step 4:** Add source row in a NEW category block:
```python
    # --- MCP / outils ---
    ("MCP / outils", "Invoquer un outil MCP", "mcp.tool.invoke", "mcp", "invoke_tool"),
```
Regenerate, run -> PASS.
**Step 5:** Commit `feat(catalog): add mcp.tool.invoke (C3)`.

### Task 6: Green the full suite + coverage guard

**Step 1:** Run the targeted tests:
`python3 -m unittest tests.test_annex_c_referential tests.test_action_criticality -v`
Expected: PASS, count == 124, category counts match.
**Step 2:** Run the gates:
- `./recette.sh test` (full unittest suite)
- `make recette` (coverage guard, R20). If a new governed action trips a
  coverage dimension (D1 action-in-campaign / D2 lab-handler / D6 verdict), either
  wire the minimal coverage OR add it to the explicit frozen-exception constant
  with a one-line justification -- NEVER silence by hand (memory: no-silent-recette-gaps).
- `make gates` (ruff/mypy/bandit) on the touched Python.
**Step 3:** Commit any guard wiring: `test(recette): cover the 6 new governed actions`.

---

## PHASE 2 -- docx: align tags, Annex C, synthesis, 94%, gains

> The file is `~/Downloads/AgentRail_BNPParibas_Design_Partner_v4.5.docx` (outside
> the repo). Use the `docx` skill (Skill tool) for structured edits; python-docx
> may be installed in a disposable venv (authorized, memory:docker-disposable-env-installs-ok).
> After EACH task, re-render and grep to verify: `pandoc -t markdown <file> | grep ...`.
> Keep a backup copy before the first edit.

### Task 7: Remap OWASP LLM v2025 -> Agentic 2026 across the 12 use cases

For each UC "Tags" cell, replace the `OWASP LLM..` token (keep the ATT&CK
Enterprise IDs, they remain valid; prefer agentic ATLAS where listed):

| UC | new OWASP | ATLAS to set/keep |
|----|-----------|-------------------|
| UC01 | ASI02 Tool Misuse | T1565 + AML.T0053 |
| UC02 | ASI06 Memory & Context Poisoning | AML.T0051 |
| UC03 | ASI02 | AML.T0053 |
| UC04 | ASI02 | T1565 |
| UC05 | ASI02 | (keep AI Act/DORA) |
| UC06 | ASI03 Identity & Privilege Abuse | T1078/T1098/T1548 |
| UC07 | ASI06 (injection via ticket) | AML.T0051 + AML.T0086 |
| UC08 | ASI02 | -- |
| UC09 | ASI04 Supply Chain Compromise | AML.T0110 |
| UC10 | ASI03 | T1548 |
| UC11 | ASI02 (note ASI09 review bypass) | T1562 |
| UC12 | ASI02 (note ASI06 input manip) | T1565 |

Verify: `pandoc -t markdown <file> | grep -c 'LLM0'` -> expect 0 in UC tag rows
(LLM mentions may remain only in section 2 before its row is updated -- handled
in Task 9). Commit (the design doc), do NOT commit the external .docx into the repo.

### Task 8: Add the 6 actions to Annex C table + section 1.5 synthesis

- Annex C table: insert 6 rows with `annex_c_action_type` + criticality matching
  the regenerated referential (source: the new `corpus/referentials/annex-c-governed-actions.json`).
- Section 1.5: change "118 actions ... 11 domaines" -> "124 actions ... 12
  domaines" (the new "MCP / outils" domain). Update the per-domain breakdown table
  (Identite 13->15, GitHub 13->14, Cloud 12->13, Juridique 9->10, add MCP row 1)
  and the C1/C2/C3/C4 totals line accordingly (recount from the referential:
  `python3 -c "import json,collections;d=json.load(open('corpus/referentials/annex-c-governed-actions.json'));print(collections.Counter(a['criticality'] for a in d['actions']))"`).
- Verify the numbers in the doc equal the referential (single source of truth).

### Task 9: Update the normative table (section 2) OWASP row

Replace "OWASP Top 10 LLM v2025 (LLM06 Excessive Agency, LLM01 Prompt Injection)"
with "OWASP Top 10 for Agentic Applications 2026 (ASI02 Tool Misuse, ASI03 Agent
Identity & Privilege Abuse, ASI06 Memory & Context Poisoning, ASI04 Supply Chain
Compromise)". Keep the AgentRail response column.
Verify: `pandoc -t markdown <file> | grep -i 'ASI0' | head`.

### Task 10: Reframe the 94% / Verifier Tax citation (1.4 + Annex D)

Rewrite the source note so it states the paper's ACTUAL finding and turns it into
a differentiator (design decision 1). Suggested text:

> Repere externe : Tanmay Sah et al., "The Verifier Tax: Horizon Dependent
> Safety-Success Tradeoffs in Tool Using LLM Agents", arXiv:2603.19328 (2026,
> CAIS 2026). L'etude observe qu'une couche de mediation runtime intercepte
> jusqu'a 94 % des actions non conformes, mais que cette interception ne suffit
> pas a elle seule : le taux de succes sur reste sous 5 % car les modeles
> hallucinent des identifiants pour contourner l'authentification ("integrity
> leaks"). AgentRail repond precisement a ce mode d'echec en liant chaque action
> a une identite d'agent cryptographique (Ed25519, non hallucinable) : la
> mediation runtime ET la liaison d'identite verifiee. Valeur a mesurer sur le
> perimetre BNP en pilote.

Verify: `pandoc -t markdown <file> | grep -i 'integrity leak\|Ed25519\|2603.19328'`.

### Task 11: Tighten gain ranges + resolve the risk column

- Replace each two-sided gain range (e.g. "-30 a -50 %") with a single prudent
  bound (e.g. "jusqu'a -30 %") OR move the figure out of the prospective UC and
  keep only the measurement method (1.4). Apply consistently across UC01-12.
- "Niveau de risque" column: it is "Eleve" almost everywhere and duplicates the
  criticality posture. Either (a) fold it into the criticality column, or (b)
  grade it meaningfully per UC. Pick one and apply to all 12 UC tables.
Verify by re-rendering and reviewing the UC tables.

### Task 12: Final verification

- `pandoc -t markdown <file> | grep -c 'LLM0'` -> 0 (no stale OWASP LLM tags).
- Annex C / 1.5 counts equal the referential (124, domain breakdown, C-totals).
- 94% note contains the integrity-leak + Ed25519 reframe.
- Provide a short diff summary to the operator; the .docx stays in `~/Downloads`
  (not committed). Offer to commit the repo-side changes + design/plan docs.

---

## Notes / guard-rails

- I4 determinism: nothing here touches the decision path; the catalog is static
  data. No clock/random introduced.
- R20: a new governed action must not create a SILENT coverage gap -- Task 6 makes
  the coverage guard the gate.
- R13: every doc number (124, per-domain, C-totals) is READ from the regenerated
  referential, never hand-counted.
- Commits: repo changes only; the external .docx is the operator's artifact.
