# PDCA : AI backends panel UX (console)

Date : 2026-06-13
Status : TERMINE
Cycle : PDCA (Plan / Do / Check / Act)
Scope : console/src/pages/agents/AiBackendsPanel.tsx + agents.css
Invariants concernes : aucun plane backend touche (UI seule). R16 (contract gate) applique.

## PLAN

Objectif : ameliorer la lisibilite et la justesse du panneau "AI backends" sans
toucher la logique, les data-testid ni les contrats de test.

Criteres de succes mesurables :
1. Aucune copie fausse visible (la note ne doit plus pretendre que la cle n'est
   jamais stockee, alors que le secret store par backend existe).
2. Les deux outils distincts du panneau (probe "Test" vs "Ask the model") ne
   doivent plus partager une seule cellule indifferenciee.
3. Focus clavier visible sur chaque controle interactif (a11y).
4. Une seule echelle de rayon sur chips / inputs / panneau de reponse.
5. Zero regression : suite console verte, contrats data-testid intacts.

Mode : redesign-preserve (le systeme de tokens et l'IA existants sont propres).
Le skill design-taste-frontend est hors-perimetre esthetique ici (UI produit,
pas landing) ; seules ses regles universelles s'appliquent.

## DO (commit d3f9609)

- Note reecrite : la cle est stockee par backend en write-only, fallback env var.
- Cellule d'action scindee : cluster "Test" (bouton + resultat + hint) groupe ;
  "Ask the model" deplace sur un panneau teinte sous un filet, avec caption visible.
- a11y : anneau focus-visible accent sur chaque button/input/select du panneau.
- Shape lock : `--agents-radius` / `--agents-radius-pill` sur chips, inputs,
  texte de reponse ; le key input adopte le style des inputs du formulaire.

## CHECK

- [x] Critere 1 : `grep "never stored here"` = 0 ; nouvelle formulation presente.
- [x] Critere 2 : classes `agents-probe`, `agents-probe-row`, `agents-ask-caption`
      cablees (tsx + css), Ask sur panneau separe.
- [x] Critere 3 : regle `:focus-visible` accent presente, portee a tous les controles.
- [x] Critere 4 : rayons normalises sur les tokens scoped.
- [x] Critere 5 : suite console verte ; tsc sans nouvelle erreur (seule erreur
      restante = fluxModel.ts d'une session parallele, non touche).
- Lacune trouvee : la copie corrigee et la caption n'etaient verrouillees par
  AUCUN test (R16) -> une regression passerait inapercue. Nom de test obsolete
  ("lists all 8 providers" alors qu'il y en a 11).
- Limite : pas de smoke navigateur (pas de Playwright MCP cette session) ->
  le rendu visuel reste a verifier par l'utilisateur (R14).

## ACT

- Ajout de 2 tests render-and-assert (R16) : note veridique (absence de
  "never stored here" + presence du wording write-only) et caption "Ask the
  model" visible par ligne. Suite panel : 14 -> 16 verts.
- Renommage du test obsolete "lists all 8 providers" -> "lists every provider".
- PDCA trace ici + entree decision_log.

## RESULTAT

Panneau plus lisible (probe vs ask separes), copie veridique, focus a11y,
formes coherentes, et regressions de copie/caption desormais bloquees par test.
Reste hors-scope de cette session : smoke navigateur visuel (a verifier par l'utilisateur).

---

## Cycle 2 -- audit-pdca (structural)

Status : TERMINE
Declencheur : skill audit-pdca sur le panneau.

### CHECK (audit)
Sante du scope : R25 (couleurs hex) clean, zero console.log (R6), zero `any`/
`@ts-ignore`, zero XSS, fixtures presentes (R17 satisfait), tsc scope clean,
16 tests verts. UNE dette structurelle : `AiBackendsPanel.tsx` = 509 LOC,
au-dessus du plafond .tsx de 400 (R29).

### ACT (remediation)
Extraction des 3 renderers de cellule (`KeyCell`, `AskCell`, `TestCell`) +
types `TestState`/`AskState` + `statusOf` vers un module presentationnel
`AiBackendRowCells.tsx` (179 LOC, sous plafond, R29 No-Birth OK). Composants
purs : tout l'etat reste dans le parent, passe en props ; DOM identique
(classes, data-testid, roles, copie inchanges).

Resultat : `AiBackendsPanel.tsx` 509 -> 381 LOC (sous plafond). tsc scope
clean, 16 tests panel verts (contrats DOM preserves), suite console 175 verte.

### Scorecard (evidence-based, recette PASS 0 critical)
| Domaine | Score | Preuve |
|---------|-------|--------|
| security | 20/20 | pas de XSS/secret/URL en dur (placeholder seul), cle write-only R8 |
| testing | 15/15 | 16 tests panel, fixtures R17, locks copie+caption |
| architecture | 15/15 | extraction SRP, sous plafond LOC |
| code_hygiene | 15/15 | dette LOC resorbee (509->381) |
| completeness | 15/15 | 11 providers, key/test/ask/console complets |
| documentation | 10/10 | doc-comments module + PDCA trace |

Verdict : COMPLETE. Residuel hors-scope (A2) : smoke navigateur visuel
(pas de Playwright MCP) -> a verifier par l'utilisateur.
