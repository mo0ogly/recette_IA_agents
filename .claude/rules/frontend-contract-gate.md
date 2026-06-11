# R16 Frontend Contract Gate -- console d'approbation + audit (React/TS)

## Pourquoi

La console AgentRail (workflows d'approbation, observabilite, replay) consomme les APIs du
Control/Audit Plane. Un composant qui rend une reponse API sans l'avoir validee contre un
payload reel casse en prod sur un mismatch d'enveloppe. Cette gate l'empeche.

## La regle (BLOQUANTE pour tout composant React appelant une API)

Tout composant qui appelle un endpoint AgentRail DOIT satisfaire :

1. **Fixture payload reel** -- capturer la reponse du backend (curl / DevTools) et la
   sauver dans `__fixtures__/{component}.fixture.json`. PAS un payload invente.

2. **Render-and-assert test** -- rendre le composant avec la fixture et asserter :
   - aucune erreur console / runtime (`Cannot read properties of undefined`...),
   - au moins un element DOM attendu present (etat d'approbation, agent_id, decision...).

3. **Smoke test live post-build** -- naviguer le flux reel (ex: ouvrir une demande
   d'approbation `pending`, approuver, verifier la transition d'etat) via Playwright /
   webapp-testing, pas seulement le chargement de page.

4. **Service unwrap de l'enveloppe** -- si le backend renvoie `{ success, data }`, le service
   DOIT unwrap `.data` explicitement. Jamais retourner la reponse brute.

## Specificite AgentRail : etats d'approbation

Pour tout composant affichant un `approval_state` ou une `policy_decision`, le test DOIT
couvrir les variantes du discriminated union : `none | pending | approved | denied | timeout`
et `allow | deny | escalate`. Une variante non geree dans l'UI = bug d'affichage en prod.

## RETEX (champ obligatoire pour une vague frontend)

```markdown
## R16 Contract Gate
- Endpoint(s): /api/...
- Fixture: __fixtures__/{component}.fixture.json (oui/non)
- Render-and-assert: chemin/du/test (oui/non)
- Smoke live: flux teste (oui/non, capture)
- Etats couverts: pending/approved/denied/timeout (oui/non)
- Crashes observes: aucun | <liste>
```

## Raccourcis interdits

- "le type compile" -> les types ne sont pas un contrat tant qu'ils ne sont pas valides contre un vrai payload.
- "teste en local, ca marchait" -> sans fixture dans le repo, ca n'existe pas.
- "on ajoutera le test a la prochaine vague" -> non, la vague ne se cloture pas.

> Skills utiles : `react-expert`, `typescript-pro`, `frontend-design`, `webapp-testing`, `test-first`.
