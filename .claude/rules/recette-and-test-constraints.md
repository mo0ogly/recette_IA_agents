# R20 Recette & Test Constraints -- what a test/recette MUST satisfy here

> The consolidated gate index for everything that validates behaviour in this
> repo: the unittest suite, the recette (identification + discovery), the
> coverage guard, the frontend contract gate, and the live smokes. A change
> that adds or judges behaviour is INCOMPLETE until it clears the gates below.
> This rule points to the detailed rules; it does not duplicate them.

## Why this rule exists

The repo is a ground-truth CORPUS plus the harness that judges it. A test that
is non-deterministic, a recette gap found by hand, a frontend rendered without a
real payload, or a live proof left in `/tmp` all silently erode that ground
truth. These constraints make each failure mode loud (a red gate) instead of
silent.

## Test harness constraints

- **Runner is stdlib unittest, zero install.** The Python suite runs with
  `python3 -m unittest discover -s tests` (also `./recette.sh test`,
  `make test`). The only hard dependency is `jsonschema`; real SDKs
  (`PyGithub`, `python-gitlab`, provider clients) are the optional `[real]`
  extra. Do not add a test that needs an uninstalled package to collect.
- **Tests live in `tests/`**, fixtures in `tests/fixtures/` (Python) or
  `__fixtures__/` (console). End-to-end browser/flow tests live in
  `tests/e2e/` (Python) and `scripts/smoke_*.py`. Never leave a test or a
  live-proof script in `/tmp` -- if it is worth running once it is worth
  committing where the next run can find it (see "Live proof" below).
- **Determinism is law (I4 / R11).** No `time.time()`, `datetime.now()`, or
  `random` in agent execution, the decision path, or a judge. The logical
  clock is injected (`recette.events.LogicalClock`); `event_id` is sequence-
  derived. Any new decision/judge path ships a replay test asserting a
  byte-stable result. Detail: `.claude/rules/determinism-replay.md`.
- **No mock/placeholder in a production path (R4).** Fixtures are explicit and
  scoped to `tests/` / `__fixtures__/`; they never leak into `recette/` runtime.

## Recette constraints (identification + discovery)

- **Positives AND negatives, mono-axis.** Every negative agent breaks EXACTLY
  ONE of the four dimensions (identity, capabilities, policy, behavior) via its
  `violation_type`; the other three stay conform. Cover correct + incorrect on
  GitHub AND GitLab. Detail: `.claude/rules/recette-corpus.md`.
- **Three forms of an agent, never confused.** runtime (`config/inspect_ia_agents.config.json`,
  the dashboard "Lancer") -> identification subject (`corpus/agents/`, a frozen
  action-log) -> discovery subject (`corpus/repos/`, a real publishable repo).
  Discovery never sees the runtime; identification never sees the source.
- **Discovery ground-truth = invariant properties only** (detection, count/dedup,
  coverage, relative risk order, determinism, policy presence) -- never opaque
  values (`canonical_agent_id`, exact score).
- **MAF subjects follow the standard** (`kind: "maf_agent"`, tool/handoff
  capabilities, deterministic judge, I6 approval-gated tools). Detail:
  `.claude/rules/maf-standard.md`.

## The coverage guard is the anti-silence gate

`tests/test_coverage_guard.py` (also `make recette`) asserts the corpus is
fully wired across six dimensions (D1 action-in-campaign, D2 action-has-lab-
handler, D3 role-matrix, D4 domain triplet, D5 identification enum exercised,
D6 no campaign action without an expected verdict / no orphan declared agent).
A new role/action/domain/campaign that is not fully covered turns it RED. Known
exceptions are frozen in explicit constants -- they cannot grow silently, and
closing one without updating the constant also fails. **A coverage gap is a
failing test, never something to find by hand.** Detail (memory): the
"no-silent-recette-gaps" lesson.

## Frontend constraints (R16 contract gate)

Any React component calling an inspect_ia_agents API needs: a REAL captured payload in
`__fixtures__/{component}.fixture.json`, a render-and-assert test, the service
unwrapping the response envelope, and -- for `approval_state` / `policy_decision`
-- coverage of every discriminated-union variant. "The type compiles" is not a
contract. Detail: `.claude/rules/frontend-contract-gate.md`.

## Live proof goes in the versioned smoke, not /tmp (R14)

When a change needs a real end-to-end proof (click the UI, drive the API, hit a
provider), put the reproducible scenario in the committed smoke -- not a
throwaway script. The homes already exist:

- `scripts/smoke_console.py` -- real Chromium drives the console -> API (run via
  `./recette.sh smoke`). Make new flows deterministic (mock/`StubLlm` backend,
  no real key) so the smoke is re-runnable without secrets.
- `scripts/smoke_lab.py` -- API -> mock server -> replay.

A one-off `/tmp/*.mjs` is acceptable ONLY as a scratch during a turn and MUST be
deleted before finishing; the durable assertion lives in a unittest
(deterministic regression) and/or the smoke (live wiring). Detail:
`.claude/rules/no-fix-without-live-verification.md`.

## The gates (run before declaring done)

| Gate | Command |
|------|---------|
| Python lint/format/type/security | `make gates` (ruff check + ruff format --check + mypy + bandit) |
| Python suite | `./recette.sh test` (`python3 -m unittest discover -s tests`) |
| Recette + coverage guard | `make recette` (coverage-guard, validate, run, discovery, ...) |
| Console build | `./recette.sh console-build` (tsc + vite, from `console/`) |
| Console tests | `./recette.sh console-test` (vitest, from `console/`) |
| Live wiring (when relevant) | `./recette.sh smoke` |

Services for any live check are started by `./recette.sh` only (R19): never
hand-launch, never change a port.

## Related

- `.claude/rules/recette-corpus.md` -- 4 dimensions, 3 agent forms, positives/negatives.
- `.claude/rules/maf-standard.md` -- MAF subjects/judges.
- `.claude/rules/determinism-replay.md` (I4/R11) -- replay test obligation.
- `.claude/rules/frontend-contract-gate.md` (R16) -- console contract.
- `.claude/rules/no-fix-without-live-verification.md` (R14) -- live proof.
- `.claude/rules/recette-sh-single-entrypoint.md` (R19) -- one launcher, fixed ports.
- `.claude/skills/audit-pdca/` -- the continuous-improvement loop that runs these gates.
