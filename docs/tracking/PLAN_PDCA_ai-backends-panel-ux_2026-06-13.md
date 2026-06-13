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
