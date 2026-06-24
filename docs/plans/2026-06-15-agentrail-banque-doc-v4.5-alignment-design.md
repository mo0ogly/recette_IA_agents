# Design: align AgentRail x BANQUE Paribas Design Partner doc (v4.5) with the code + standards

Date: 2026-06-15
Status: APPROVED (brainstorm)
Source doc: `~/Downloads/AgentRail_BANQUEParibas_Design_Partner_v4.5.docx` (outside repo)
Repo ground truth: `corpus/referentials/annex-c-governed-actions.json`, `recette/platform/catalog/domains/*`

## Objective

The v4.5 partner doc added: a C1-C4 criticality model (1.1), a "niveau de
risque" column, MITRE/OWASP tags per use case, 12 governed use cases (UC01-12),
pilot KPIs (1.4), and a 118-action referential synthesis (1.5, detail in Annex
C). Brainstorm verdict: the content is strong but has three credibility/coherence
gaps that a BANQUE technical reviewer (RSSI, conformite) would catch. This design
fixes them. Scope chosen by the operator: critique credibility + align with code
+ enrich.

## Verified facts (R13)

- **OWASP standard mismatch.** The doc tags use cases with **OWASP Top 10 LLM
  v2025** (`LLM01`, `LLM06`). The repo corpus uses **OWASP Top 10 for Agentic
  Applications 2026** (`ASI01..ASI10`, confirmed present in `corpus/`, frozen by
  rule R23). The product is one standard ahead of its own pitch.
- **94% citation is real but inverts the paper's thesis.** arXiv:2603.19328 "The
  Verifier Tax" (18 Mar 2026, CAIS 2026) does say mediation can "intercept up to
  94 percent of non-compliant actions" -- but its conclusion is the opposite:
  safe success rate <5% in most settings, because models hallucinate user
  identifiers to bypass mandatory auth ("Integrity Leaks"). Citing 94% alone is
  cherry-picking; a reviewer opening the arXiv sees the inverse thesis.
- **6 sensitive action types cited in UC scenarios are ABSENT from the 118-action
  referential** (verified against `annex_c_action_type` set):
  `compliance.kyc.review_open` (UC02, recommended pilot), `identity.delegation.assume`
  (UC10, DENY C1), `mcp.tool.invoke` (UC09), `identity.token.revoke` (UC06),
  `cloud.host.isolate` (UC06), `scm.secret.read` (UC09). The catalog already has
  `open_kyc_review` in `compliance.py` but it is not exposed as a governed action
  in the referential. The remaining cited-but-absent types (`finance.operation.freeze`,
  `comms.customer.notify`, `support.alert.qualify`, `support.case.*`,
  `data.scope.read`) are C4 non-sensitive filler the doc already declares "hors
  annexe C" -- leave them.
- **Referential is test-gated:** `tests/test_annex_c_referential.py` and
  `tests/test_action_criticality.py` cross-check the JSON against the catalog;
  the coverage guard (R20) reacts to new governed actions.

## Decisions (operator-approved)

1. **94%:** reframe, do not drop. Keep the 94% but recast the Verifier Tax as a
   differentiator: the paper shows mediation alone fails when identity is
   falsifiable (integrity leaks); AgentRail answers exactly that with
   cryptographic agent identity (Ed25519, I3). Interception 94% + non-hallucinable
   identity binding.
2. **Action types:** Option A -- add the 6 sensitive types to the referential
   (and the catalog where missing), bumping the count 118 -> 124, rather than
   downgrading the scenarios.
3. **OWASP:** remap LLM v2025 -> Agentic 2026 by mechanism (R23), keeping the
   valid ATT&CK Enterprise technique IDs and preferring agentic ATLAS techniques.
4. **Gains/risk column:** tighten the gain ranges and resolve the "niveau de
   risque" column redundancy with C1-C4.

## Proposed changes

### A. OWASP remap (12 UC + section 2), by mechanism (R23)

| UC | from | to (OWASP Agentic 2026) | ATLAS |
|----|------|--------------------------|-------|
| UC01 fraude | LLM06 | ASI02 Tool Misuse | T1565 + AML.T0053 |
| UC02 KYC | LLM01 | ASI06 Memory & Context Poisoning | AML.T0051 |
| UC03 AML | LLM06 | ASI02 | AML.T0053 |
| UC04 credit | LLM06 | ASI02 | T1565 |
| UC05 reporting | LLM06 | ASI02 | -- |
| UC06 IAM | (ATT&CK only) | ASI03 Identity & Privilege Abuse | T1078/T1098/T1548 |
| UC07 SOC | LLM01 | ASI06 (injection via ticket) | AML.T0051 + T0086 (exfil) |
| UC08 client | LLM06 | ASI02 | -- |
| UC09 supply | LLM03/07 | ASI04 Supply Chain Compromise | AML.T0110 tool poisoning |
| UC10 Guardian | (ATT&CK only) | ASI03 (delegation abuse) | T1548 |
| UC11 DevOps | LLM06 | ASI02 (+ASI09 review bypass) | T1562 |
| UC12 treasury | (ATT&CK only) | ASI02 (+ASI06 input manip) | T1565 |

Section 2 normative table: replace the "OWASP Top 10 LLM v2025 (LLM06, LLM01)"
row with "OWASP Top 10 for Agentic Applications 2026 (ASI02 Tool Misuse, ASI03
Identity & Privilege Abuse, ASI06 Context Poisoning, ...)".

### B. Add 6 sensitive governed actions (referential 118 -> 124)

Each entry added to `corpus/referentials/annex-c-governed-actions.json` with full
fields (category, label, annex_c_action_type, target_system, action_type,
criticality, risk_level, risk_score, verdict_privileged, verdict_default,
privileged_roles), wired in the catalog domain, and reflected in docx Annex C +
section 1.5 synthesis.

| annex_c_action_type | target_system | action_type | crit | catalog domain | note |
|---------------------|---------------|-------------|------|----------------|------|
| compliance.kyc.review_open | compliance | open_kyc_review | C3 | compliance.py (exists) | expose existing action |
| identity.delegation.assume | okta | assume_delegation | C1 | okta.py (new) | UC10 DENY, never unblockable |
| mcp.tool.invoke | mcp | invoke_tool | C3 | mcp.py | UC09, escalate on manifest drift |
| identity.token.revoke | okta | revoke_token | C3 | okta.py (new) | UC06, reversible defensive |
| cloud.host.isolate | cloud | isolate_host | C2 | cloud.py (new) | UC06, shared prod -> escalate |
| scm.secret.read | github | read_secret | C2 | github_devops.py (new) | UC09, out-of-build-context |

Ripples: count 118->124; section 1.5 per-domain breakdown table; if `mcp` becomes
a distinct referential category, the "11 domaines" wording -> "12". Update
`tests/test_annex_c_referential.py` expected count and `test_action_criticality.py`.
Verify the coverage guard stays green (R20) -- new governed actions may need
campaign/lab-handler coverage or an explicit frozen exception.

### C. 94% reframe (section 1.4 + Annex D source note)

Recast the Verifier Tax citation: state the paper's actual finding (mediation
intercepts up to 94% of non-compliant actions but safe-success stays <5% because
identity is falsifiable -- integrity leaks), then position AgentRail's Ed25519
cryptographic identity (I3) as the answer to exactly that failure mode. Keep
"repere externe, a mesurer en pilote".

### D. Gains + risk column

- Narrow the gain ranges (e.g. a single prudent bound) or move them out of the
  prospective UCs, keeping the measurement method in 1.4.
- "Niveau de risque" column is near-redundant with C1-C4 (C1=Critique...). Either
  grade it meaningfully (it is "Eleve" almost everywhere) or fold it into the
  criticality column.

## Out of scope (YAGNI)

- Restructuring the document layout/order (operator did not select it).
- Adding new use cases / KPIs (enrichment ideas captured below as backlog, not
  this change): vendor-bank-change UC, RGPD/LLM-exfil UC, HR UC; KPIs for
  delegation-chain depth, crypto-signed-action share, deterministic-replay rate,
  ghost-agent count; a 5th criticality criterion (auditability/silence).

## Testing / gates

- `python3 -m unittest tests/test_annex_c_referential.py tests/test_action_criticality.py`
- `make recette` (coverage guard) green after catalog additions.
- `make gates` (ruff/mypy/bandit) on touched Python.
- docx: re-render with pandoc, diff the UC tag tables / Annex C / 1.5 / 1.4.
