# Plan : G1 -- AuthN/AuthZ sur l'API console (I3)

Date : 2026-06-13
Status : TERMINE
Branch : feat/g1-api-auth
Invariants : I3 (liaison identite), I2 (mediation), R6 (log structure), R8 (secret env)
Source gap : docs/tracking/TODO_APEX_platform-gaps_2026-06-13.md G1

## Constat (verifie)

`/actions/execute` prend `agent_id` du body verbatim, zero verification ; 0 `Depends/
Security` sur les 15 routers. Une requete peut se faire passer pour n'importe quel
agent -> I3 non applique. Pas de PyJWT dispo ; projet = deps minimales.

## Decision

JWT HS256 implemente en **stdlib** (hmac/hashlib/base64), pas de nouvelle dependance.
Alternative PyJWT rejetee (dep dure inutile pour HS256). Enforcement gate par la
presence de `AGENTRAIL_JWT_SIGNING_KEY` : cle set -> deny-by-default (401) ; cle
unset -> open-mode dev/test avec WARNING bruyant au demarrage. Production DOIT set la cle.

## Etapes

- [ ] S1 recette/api/auth.py : HS256 stdlib (decode/verify + issue helper), Principal
      (sub, kind agent|operator, agent_id), AuthError. Securite : alg pinne HS256
      (rejette none/RS/ES), compare constant-time, exp/nbf, taille bornee. + tests.
- [ ] S2 Middleware dans app.py : ASGI, allowlist (/health, OPTIONS preflight,
      openapi/docs), enforce si cle set, attache request.state.principal, 401 + log
      structure (R6) sur echec.
- [ ] S3 Liaison identite sur /actions/execute : agent_id body DOIT == principal
      (deny 403 + log si mismatch). Ferme I3.
- [ ] S4 tests/test_api_auth.py : roundtrip, alg-confusion (none/RS256) rejete, sig
      falsifiee rejetee, expire rejete, 401 sans token (cle set), 403 mismatch agent,
      200 token valide, open-mode si cle unset.
- [ ] S5 doc : runbook docs/runbooks/api-auth.md + mermaid (flux auth), maj RETEX.

## Done

- Suite complete verte (auth off par defaut -> tests existants inchanges).
- Route non-allowlist + cle set + sans token -> 401 ; mismatch agent -> 403.
- gates ruff/mypy/bandit verts sur le delta. Aucun secret en dur (R8).

## Ecarts / replan

(a remplir)
