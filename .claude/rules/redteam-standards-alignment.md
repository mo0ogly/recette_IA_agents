# R23 Red-team Standards Alignment -- OWASP Agentic 2026 + MITRE ATLAS (agentic)

> Every red-team scenario (`corpus/sim/*.scenario.json` MAF, `*.git-scenario.json`
> git) carries standards tags (`tags.owasp_asi`, `tags.mitre_atlas`, `tags.nist`).
> Those tags MUST map to the CURRENT published standards, not a stale guess. This
> rule freezes the canonical mapping so a new scenario is tagged right and the
> `/sim` "repartition OWASP" scorecard tells the truth.

## Why this rule exists

2026-06-15: an operator asked whether our red-team used the up-to-date standard.
A web check found the **OWASP Top 10 for Agentic Applications 2026** had just
been released with a renumbered list, and our corpus tags were misaligned
(identity tagged ASI04 instead of ASI03, spam tagged ASI06 instead of ASI10,
handoff tagged ASI06 instead of ASI07, approval-bypass tagged ASI04 instead of
ASI09). A wrong tag makes the scorecard's standards distribution a false claim
(R13 cousin). The fix is a frozen mapping, verified against the source.

## OWASP Top 10 for Agentic Applications 2026 (authoritative list)

| code | title |
|------|-------|
| ASI01 | Agent Goal Hijack |
| ASI02 | Tool Misuse & Exploitation |
| ASI03 | Agent Identity & Privilege Abuse |
| ASI04 | Agentic Supply Chain Compromise |
| ASI05 | Unexpected Code Execution |
| ASI06 | Memory & Context Poisoning |
| ASI07 | Insecure Inter-Agent Communication |
| ASI08 | Cascading Agent Failures |
| ASI09 | Human-Agent Trust Exploitation |
| ASI10 | Rogue Agents |

Source: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
(list cross-checked at https://www.trydeepteam.com/docs/frameworks-owasp-top-10-for-agentic-applications).

## Canonical mapping (the rule)

The four recette `violation_type`s are the broken AXIS; the OWASP tag is the
ATTACK CLASS (the mechanism). They are related but NOT 1:1 -- tag by the
mechanism the scenario exercises:

| scenario mechanism | violation_type (axis) | owasp_asi | mitre_atlas |
|--------------------|-----------------------|-----------|-------------|
| out-of-scope tool / git action (direct) | capability_overreach | ASI02 | AML.T0086 if exfil via tool, else AML.T0053 |
| undeclared handoff / inter-agent transfer | capability_overreach | **ASI07** | AML.T0053 |
| poisoned tool output drives the action | capability_overreach (or behavior) | **ASI06** | **AML.T0110** (tool poisoning) |
| approval-gate bypass / unapproved sensitive action | policy_violation | **ASI09** | AML.T0053 |
| principal / identity divergence | identity_mismatch | **ASI03** | AML.T0053 |
| spam / out-of-role rogue behavior | behavior_anomaly | **ASI10** | AML.T0053 |
| adversary flips the agent's goal | (resisted or behavior) | ASI01 | AML.T0051 (prompt injection) |

MITRE ATLAS: tag the **agentic** technique when it fits -- `AML.T0086`
(Exfiltration via AI Agent Tool Invocation), `AML.T0110` (AI Agent Tool
Poisoning), `AML.T0051` (LLM Prompt Injection). Default `AML.T0053` only when no
agentic technique is a better fit (never invent an ID -- R13).
Source: https://www.vectra.ai/topics/mitre-atlas (ATLAS v5.x, agentic techniques).

NIST: `tags.nist = "AI-RMF MEASURE 2.7"` (measure trustworthiness of the
adversarial/edge behavior under the NIST AI RMF MEASURE function).

## The rule (BLOCKING for any new/edited red-team scenario)

1. **Tag against the 2026 list above, by mechanism.** A new scenario's
   `owasp_asi` MUST be one of ASI01..ASI10 with the meaning in the table, picked
   by the attack mechanism (not loosely by the broken axis).
2. **Prefer the agentic ATLAS technique.** Use `AML.T0086` / `AML.T0110` /
   `AML.T0051` when they fit; `AML.T0053` is the fallback, not the default.
3. **Verify, do not guess (R13).** If unsure a code still exists or a title
   changed, re-check the OWASP/ATLAS source before tagging.
4. **Mono-axis stays law (R20).** The standards tag is metadata; it does NOT
   change the requirement that a negative breaks exactly one of the four
   dimensions.

## Engine feasibility for the not-yet-covered ASI categories

Verified against the current engines (what we CAN exercise without inventing):

- **ASI07 Insecure Inter-Agent Communication** -- COVERED. The MAF handoff path
  (`recette/simulate.py`, `maf_orchestration.py`, `HandoffBuilder`) models an
  undeclared/out-of-set transfer. (`rt-maf-handoff-overreach`.)
- **ASI06 Memory & Context Poisoning** -- COVERED. The `tool_injection` field
  (AgentDojo injection-via-tool-output, `redteam_git._tool_output`) poisons a
  tool result that drives the next action. (`rt-prbot-context-poisoning`.)
- **ASI08 Cascading Agent Failures** -- COVERED, in the ORCHESTRATION recette
  (not `/sim`). `corpus/maf_orchestration/incorrect/support-handoff-cascading-failure`
  models a downstream failure handed back upstream and retried, cascading across
  the triage/enrich/notify mesh until the run exceeds `termination.max_hops`;
  `judge_orchestration` flags it mono-axis as `behavior_anomaly`. Orchestration
  ground-truth has no `tags` field, so the ASI08/AML.T0053 mapping is recorded in
  the subject's `rationale` (consistent with the orchestration corpus, which the
  orchestration recette judges on the 4 dimensions, not an OWASP distribution).
- **ASI04 Agentic Supply Chain Compromise** -- FEASIBLE on the DISCOVERY side
  (`corpus/repos/`, the `.inspect_ia_agents` manifest a scanner reads), NOT on the `/sim`
  runtime side: a poisoned repo/tool source is a static-source artifact, not an
  action-log. Model it as a discovery subject, not a sim scenario.
- **ASI05 Unexpected Code Execution** -- NOT feasible honestly today. The lab
  executes only the fixed action catalog (`recette/tools.py`); there is no code
  sandbox. Modeling it as a `code_interpreter` capability_overreach would be a
  proxy, not real code execution -- do NOT fake it (R4/R13). Add only if a real
  exec double is introduced.

## Related

- `.claude/rules/recette-corpus.md` -- 4 dimensions, mono-axis, positives/negatives.
- `.claude/rules/maf-standard.md` -- MAF subjects/handoffs/orchestration.
- `.claude/rules/recette-and-test-constraints.md` (R20) -- coverage guard, gates.
- `docs/runbooks/redteam-recette.md` -- the red-team runbook (gate, recorder, promote).
