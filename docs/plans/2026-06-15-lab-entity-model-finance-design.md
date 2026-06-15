# Design: deterministic entity model for lab doubles (finance first)

Date: 2026-06-15
Status: APPROVED -- implementing
Invariants: I4 (determinism/replay), I5 (side effects via proxy double)

## Objective

Make the lab doubles answer agents in richer, more legible detail without
breaking replay determinism (I4). Start with the finance domain. Four asks:
richer responses, multi-call coherence, more telling errors, a seeded world.

## Key insight

An entity (invoice, payee, account, supplier) is a PURE function of its id.
`derive_invoice("inv/9")` returns the same Invoice for every action touching
`inv/9`, this run and every replay. Cross-call coherence therefore needs NO
mutable state: two actions on the same id observe the same entity because both
recompute it from the id alone. This is the only design that satisfies the
coherence ask while keeping I4 (no clock, no random, no session store).

## Where it lands

Rich responses fire only on the HTTP double path: `LabHttpProxy` -> mock_server
-> `finance.handle()`. The in-memory `LabForge` records actions and never calls
handlers, so it is unaffected (correct: ProxyTrace legibility is the target).

## Components

- `recette/lab/domains/_entities.py` (new): `Invoice`/`Payee`/`Account`/
  `Supplier` dataclasses + `derive_*` pure functions keyed on id, seed tuples,
  shared deterministic helpers. No wall-clock dates -- relative ordinals only
  (`due_in_days`), so it stays byte-stable under replay.
- `recette/lab/errors.py`: `LabActionError` gains optional `code` + `detail`
  (back-compatible; existing callers keep emitting message-only).
- `recette/lab/mock_server.py`: `_envelope_err(message, code=None, detail=None)`
  -> `{success:false, error, code?, detail?}`.
- `recette/lab/domains/finance.py`: rewritten to source invoice-bound actions
  from `derive_invoice`; structured errors; seed discovery on empty resource;
  `trigger_refund` on a PAID invoice -> 422 `invoice_paid` (paid invoices are
  closed; the credit-note flow handles them).
- `recette/platform/proxy/lab_proxy.py`: on a 4xx, parse the envelope and
  surface `code: message` in `ExecutionResult.error` (was a generic string).

## Coherence behaviours

- `read_invoice_status(id)` and `trigger_refund`/`validate_invoice`/
  `create_credit_note` on the same id observe one Invoice (status, currency,
  payee, amount, line items).
- `add_payee` -> `payee_id`; `create_payment` to that id resolves (existing
  rule, kept).
- A no-amount refund refunds the full invoice amount (coherent total).

## Structured errors (finance)

| Status | code | detail |
|---|---|---|
| 422 | invalid_amount | field, got, expected |
| 422 | unsupported_currency | field, got |
| 422 | invalid_iban | field |
| 422 | unknown_payee | field, got |
| 422 | invalid_discount | field, got, expected |
| 422 | invoice_paid | invoice_id, status, hint |

## Determinism + tests

All derives pure -> I4. New tests: replay byte-stability, read<->refund
coherence, paid-invoice refund rejection, seed discovery, structured error
fields. Existing finance double tests updated (the double is its own ground
truth). Campaign harness asserts verdicts only -> unaffected.

## Scope

Finance only this iteration. `_entities.py` is generic so crm/hris/legal/support
adopt the derive-by-id pattern in later iterations.
