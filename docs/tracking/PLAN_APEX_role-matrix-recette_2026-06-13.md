# Plan : Role x Action matrix recette

Date : 2026-06-13
Status : TERMINE
Invariants concernes : I2 (mediation Control Plane), I4 (replay deterministe), I6 (blocage sur approbation)

## Objectif

Combler le trou "agents sous-sondes" : aujourd'hui chaque action cataloguee est
testee une fois via son admin privilegie (campagnes coverage), mais chaque ROLE
n'est sonde que sur une tranche etroite de ce qu'il peut tenter (ex bnp-soc-agent
4/25). On veut prouver que pour CHAQUE role defini et CHAQUE action du catalogue,
la gateway emet le verdict role-specifique attendu : verdict_privileged si le role
est privilegie sur l'action, sinon deny-by-default (capability_overreach bloque).

## Contrat (source de verite)

`recette/platform/policy/engine.py` : decide(event, policy, catalog) decide sur le
ROLE seul. `ActionSpec.verdict_for_role(role)` = verdict_privileged si role in
privileged_roles, sinon verdict_default (deny). C'est l'oracle : meme donnee que
le moteur lit -> expected == actual par construction, prouve en live par le harness.

## Etapes

- [x] S1 scripts/gen_role_matrix_campaigns.py : lit le catalogue committe, emet 1
      campagne par role (11) dans campaigns/role-matrix/, chaque campagne sonde les
      118 actions, expect = verdict_for_role(role), rationale in-scope vs overreach.
- [x] S2 Generer les 11 campagnes + valider structurellement (validate_campaign).
- [x] S3 scripts/run_role_matrix.py : harness offline (catalogue committe + baseline
      policy + stub proxy), rejoue chaque campagne via la vraie gateway, asserte que
      chaque action matche son verdict attendu, exit 0/1 + chaine d'audit intacte.
- [x] S4 tests/test_role_matrix.py : oracle == campagnes generees, couverture 11x118,
      chaque role a >=1 escalate in-scope et >=1 deny overreach.
- [x] S5 Python pipeline (ruff/mypy/bandit) + pytest vert + run_role_matrix PASS.

## Decisions prises

- Matrice complete 11x118 (et non domaine+echantillon) -> "chaque action de chaque role".
- Baseline policy (pas le bundle bnp-v1) -> teste la posture du catalogue committe.

## Resultat

Livre. 11 campagnes role-matrix (1 par role privilegie), 118 actions chacune
= 1298 paires (role, action). Harness run_role_matrix.py: ALL PASS via la vraie
gateway, 0 mismatch. Verdict in-scope (escalate) + overreach (deny) prouves par role.
Generation deterministe (regen byte-identique, I4). 5 tests unittest verts, suite
complete OK, recette validate OK. Trou 'agents sous-sondes' (ex 4/25) -> 118/118 par role.
