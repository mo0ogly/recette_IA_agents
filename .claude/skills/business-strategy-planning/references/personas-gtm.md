# Personas + Go-To-Market + Product Roadmap

Reference for the persona, GTM, and roadmap sub-tasks. Load when the deliverable
requires buyer personas, a launch plan, or a phased product roadmap.

## Table of contents

1. Persona template
2. Buyer vs user vs champion
3. GTM strategy components
4. Five-phase product roadmap
5. PRD skeleton
6. LIA-SEC grounding

## 1. Persona template

```markdown
### Persona: <name> -- <role title>

- Segment: <company size / sector / regulatory regime>
- Job-to-be-done: <the outcome they are hired to produce>
- Top pains: <3 ranked>
- Top gains: <3 ranked>
- Buying trigger: <event that starts the search -- audit, breach, regulation deadline>
- Decision criteria: <how they choose, ranked>
- Objections: <what makes them say no>
- Where they are reached: <channel>
```

Build at most 3 personas. More than 3 = unfocused GTM. Rank them; the first is
the beachhead.

## 2. Buyer vs user vs champion

A B2B deal has distinct actors. Name each:

- Economic buyer -- signs the budget (often CISO / RSSI for LIASCAN).
- User -- operates the product daily (analyst, auditor).
- Champion -- internal advocate who drives the purchase.
- Blocker -- procurement, legal, sovereignty/compliance gatekeeper.

A pitch that addresses only the user loses the buyer's budget conversation.

## 3. GTM strategy components

1. Beachhead segment -- the narrowest segment you can dominate first.
2. Wedge -- the single feature/outcome that wins the first deals.
3. Motion -- self-serve / inside-sales / field-sales / channel (match to ACV).
4. Pricing + packaging -- tied to the value metric (see business-model-canvas.md).
5. Channels -- direct, partner, marketplace, community.
6. Proof assets -- design partners, references, certifications (e.g. ANSSI,
   sovereignty posture for the FR market).
7. Metrics -- CAC, payback, win-rate, expansion (NRR).

GTM must be consistent with the competitive separation FR vs international: the
sovereign/airgap posture is the FR-market wedge; it is NOT the wedge against a
US-only incumbent that already ships SaaS-only.

## 4. Five-phase product roadmap

```
Discovery  -> Definition -> Development -> Launch     -> Growth
problem ID    persona+MVP    prototype     beta+GA       expand+monetize
interviews    value prop     user test     feedback      scale+new modules
market scan   MVP scope      iterate       launch        retention
```

Each phase has an exit gate. Do not enter Development without a defined MVP and a
validated value proposition. Do not enter Launch without user-test evidence.

## 5. PRD skeleton

```markdown
# PRD: <feature/product>
## Problem        -- who, what pain, evidence it matters
## Goals          -- measurable outcomes (not features)
## Non-goals      -- explicit scope cuts
## Personas       -- who this serves (link personas)
## Requirements   -- prioritized (MoSCoW: Must/Should/Could/Won't)
## Success metrics -- how we know it worked
## Risks          -- what could break the assumption
## Rollout        -- phased, with a kill criterion
```

## 6. LIA-SEC grounding

- The roadmap "Growth" claims for LIASCAN must split SHIPPED vs ROADMAP, exactly
  as `STRATEGIC_ASSESSMENT.md` does (e.g. agentic AI analyst = ROADMAP, not
  shipped; RAG over 754 cyber skills = SHIPPED). Never present a roadmap item as
  a current capability.
- Personas for LIASCAN: RSSI/CISO (economic buyer), security auditor/pentester
  (user), compliance officer (champion for GRC modules), procurement +
  sovereignty officer (blocker -> answered by FR-cloud/airgap posture).
- Reuse the per-cluster competitive deep-dives under
  `_alire/01_DOCUMENTATION/business-plan/competitive/<cluster>/` to source the
  "decision criteria" and "objections" fields with real, cited competitor facts.
