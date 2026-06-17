# Recette de discovery MCP -- runbook

La surface de discovery `mcp` valide que le scanner Manifest/MCP detecte un agent
decrit par un manifest de serveur MCP et le note sur les memes proprietes invariantes
que la surface github (detection, count/dedup, couverture d'action, target, ordre relatif
de risque, presence de policy) -- jamais les scores opaques (determinisme I4).

## Corpus

```
corpus/manifests/<slug>/
  discovery-ground-truth.json   # invariant expectations (schema: discovery-ground-truth)
  repo/
    .inspect_ia_agents/manifest.json    # inspect_ia_agents manifest with target_system: "mcp"  (detected agent)
    mcp.json                    # plain MCP server descriptor (true-negative decoy)
```

Un sujet est detecte quand `repo/.inspect_ia_agents/manifest.json` declare un agent avec
`target_system: "mcp"` et des capabilities git-canoniques (par exemple `read_repo`, `open_pr`).
Un `mcp.json` simple avec des outils arithmetiques et sans manifest inspect_ia_agents est un VRAI NEGATIF :
le scanner ne doit pas le signaler (garde anti faux-positif, voir `mcp-no-agent`).

Sujets existants : `mcp-pr-bot`, `mcp-readonly-reporter`, `mcp-admin-overreach`
(detectes) et `mcp-no-agent` (vrai negatif).

## Lancement

```
python3 -m recette validate                       # schema-validate every corpus incl mcp
python3 -m recette discovery --surface mcp        # mcp surface scorecard (offline oracle)
python3 -m recette discovery --adapter http       # against a live scanner on :8081
python3 -m recette report                         # unified verdict: identification + MAF + every surface
```

La surface est enregistree dans `recette/discovery_harness.py` :
`SURFACE_ORDER` inclut `"mcp"`, mappe vers `corpus/manifests/` par `SURFACE_CORPUS`.
Le scanner de reference (`ReferenceSourceScanAdapter._from_manifest`) lit le
`.inspect_ia_agents/manifest.json` directement.

## API

La scorecard agregee expose chaque surface, mcp inclus :

```
GET /subjects/scorecard
-> { "identification": {...}, "maf": {...},
     "discovery": { "github": {...}, ..., "mcp": {repos, passed, false_positives,
        false_negatives, ordering_ok, all_passed} },
     "all_passed": bool }
```

`GET /subjects` liste les sujets du corpus unifie (familles git_agent + maf_agent).

## Console

La page `Discovery` (`console/src/pages/discovery/`) rend `GET /subjects/scorecard` :
une ligne par surface de discovery (github/gitlab/temporal/openapi/mcp) plus les
resumes identification et MAF, avec le verdict agrege PASS/FAIL. Elle n'assert
que les proprietes invariantes. Test de contrat + fixture capturee :
`console/src/pages/discovery/index.test.tsx` + `__fixtures__/scorecard.fixture.json`.

## Extension

Ajouter un sujet detecte : creer `corpus/manifests/<slug>/repo/.inspect_ia_agents/manifest.json`
avec `target_system: "mcp"` et ses capabilities, plus un `discovery-ground-truth.json`
assertant la detection, `agent_count`, `action_patterns`, `risk_rank` et `policy_generated`.
Garder `risk_rank` monotone avec le risque pour que la verification d'ordre cross-corpus reste verte.
