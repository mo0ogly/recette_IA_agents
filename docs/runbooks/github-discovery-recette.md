# Runbook -- GitHub Discovery Recette

How a developer validates the Discovery / Enrichment Plane GitHubScanner (`:8081`)
against the ground-truth test-agent repositories in this repo.

## What you get

- 4 realistic test-agent repos under `corpus/repos/` (benign read-only, medium PR bot,
  high-risk infra syncer, and a true-negative library).
- A harness that scores the scanner on invariant properties (detection, count/dedup,
  action coverage, target, relative risk ordering, determinism, policy presence, FP/FN).
- An offline reference oracle so the recette is meaningful even before `:8081` is reachable.

## A. Offline pre-flight (no scanner needed)

```bash
python3 -m recette validate
python3 -m recette discovery --adapter reference
python3 -m unittest discover -s tests
```

`discovery --adapter reference` must print `VERDICT: PASS`. This proves the corpus +
ground-truth are internally consistent and define exactly what a correct scanner must output.

## B. Publish the test-agent repos to GitHub

Dry-run first (prints the plan, touches nothing):

```bash
python3 -m recette publish gh-readonly-reporter --owner <your-test-org>
python3 -m recette publish gh-pr-bot --owner <your-test-org>
python3 -m recette publish gh-admin-overreach --owner <your-test-org>
python3 -m recette publish gh-no-agent --owner <your-test-org>
```

Create them for real (requires `gh auth login` to an account with create rights on the org):

```bash
python3 -m recette publish gh-readonly-reporter --owner <your-test-org> --apply
python3 -m recette publish gh-pr-bot --owner <your-test-org> --apply
python3 -m recette publish gh-admin-overreach --owner <your-test-org> --apply
python3 -m recette publish gh-no-agent --owner <your-test-org> --apply
```

The publisher refuses to touch a repo that already exists and never force-pushes.

## C. Point the Discovery scanner at the repos and score it

Set the connection (dev tenant + service URL + token from your environment):

```bash
export AGENTRAIL_DISCOVERY_URL=http://127.0.0.1:8081
export AGENTRAIL_TENANT=<tenant>
export AGENTRAIL_DISCOVERY_TOKEN=<token>
python3 -m recette discovery --adapter http
```

The harness registers each published repo as a `discovery_source`, triggers a scan, reads
`discovery_risks`, and prints the scorecard.

> The `:8081` REST routes and the `estimated_risk` JSON shape are assumed in
> `recette/http_adapter.py` (constants `ROUTE_*`, `_unwrap`, and `risks()` parsing).
> If the real Discovery API differs, adjust that one file -- nothing else changes.

## D. Read the scorecard

A correct scanner yields:
- detection 100% (3 agents found, `gh-no-agent` not flagged -> 0 false positives),
- action coverage 100% (planted action patterns surfaced),
- risk ordering OK (`gh-readonly-reporter` < `gh-pr-bot` < `gh-admin-overreach`),
- determinism OK (re-scan identical),
- policy emitted for the medium/high agents.

Any `MISS` cell or a non-zero false-positive/negative count points at the exact repo and
dimension to investigate against its `discovery-ground-truth.json`.

## Notes

- The recette never compares opaque values (`canonical_agent_id`, exact risk score) -- only
  invariant properties (arch invariant 2 + fingerprinting are internal to the scanner).
- Realism is static: the repos contain genuine runnable agent code + CI/CD + manifest, but
  the recette does not execute them (no live GitHub side effects).
