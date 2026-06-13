# RETEX APEX -- G1 API auth / identity binding (I3)

Date : 2026-06-13
Branch : feat/g1-api-auth
Agentic score : 45/50

| Criterion | Score | Comment |
|-----------|-------|---------|
| C1 Decomposition | 9/10 | 5 sous-taches SRP (verifier, middleware, binding, tests, doc), deps explicites |
| C2 Planning (THINK) | 9/10 | 2 alternatives (PyJWT vs stdlib), choix stdlib justifie, critique securite inline integree (alg-pin, constant-time, exp/nbf, DoS guard) |
| C3 Replanning | 8/10 | 1 REPLAN (UnicodeDecodeError fuyait hors decode_token -> wrap ValueError) |
| C4 Tooling | 10/10 | .venv (fastapi) + .venv-pyaudit (gates), mmdc valide mermaid |
| C5 Traceability | 9/10 | PLAN + TODO maj + RETEX + runbook + commit branche |

Sous-taches : 5 SUCCESS / 0 PARTIAL / 0 FAILURE / 1 REPLAN
THINK : 2 alternatives, 1 rejetee (PyJWT), critique securite integree.

## Livre

- `recette/api/auth.py` : HS256 stdlib (decode/verify + issue + Principal), alg pinne,
  compare constant-time, exp/nbf, sub requis, taille bornee, cle >= 16o.
- `recette/api/app.py` : `JWTAuthMiddleware`, gate par `AGENTRAIL_JWT_SIGNING_KEY`
  (set -> 401 deny-by-default ; unset -> open dev + WARNING). CORS reste outermost.
- `recette/api/routers/actions.py` : `_bind_identity` -- agent ne peut agir que comme
  lui-meme (403 + log sur mismatch). Ferme le trou I3 (agent_id n'est plus pris verbatim).
- `tests/test_api_auth.py` : 17 tests (verifier + middleware bout-en-bout via TestClient).
- `docs/runbooks/api-auth.md` : modele, gate, binding, 2 mermaid (sequence + decision).

## Preuves (faits)

- 749 tests OK (9 skip). Zero regression : open-mode par defaut preserve l'existant.
- Enforcement prouve via TestClient (vrai flux middleware) : sans token -> 401,
  token agentA + body agentB -> 403, token valide -> < 400, /health ouvert.
- Forgeries refusees : alg:none, RS256 (alg-confusion), signature falsifiee, expire, nbf.
- gates : ruff + ruff-format + mypy (122 fichiers) + bandit -> 0 finding sur le delta
  (auth/app/actions). Les 3 MEDIUM bandit restants sont pre-existants (config/server/sqlite).
- system-recette PASS. Aucun secret en dur (R8) ; cle via env.

## Ce qui a marche

- HS256 stdlib : zero dep, securite explicite et auditable, coherent avec l'ethos du repo.
- Gate par cle : I3 enforce des que configure, sans casser 749 tests ni la console.

## Ce qui a coince

- `json.loads` sur un segment non-UTF8 leve `UnicodeDecodeError` (sous-classe de
  ValueError) qui fuyait hors `decode_token` -> wrap dans `_json_segment` -> AuthError.

## Evolutions possibles

- Quick win : roles plus fins (operator vs agent) par route sensible (config/policies).
- Notable : rotation de cle (kid dans le header, multi-cles), audit des 401 en evenement borne.
- Refactor : passer la verif d'identite a une dependency FastAPI reutilisable par route.

## Suite (gaps plateforme)

G2 (approbation durable Temporal, I6) recommande ensuite -- cf.
docs/tracking/TODO_APEX_platform-gaps_2026-06-13.md.
