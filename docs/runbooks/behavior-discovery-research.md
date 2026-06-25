# Correlation Comportement <-> Discovery -- runbook recherche

> Pour l'equipe recherche IA. Comment utiliser la plateforme pour analyser le
> COMPORTEMENT d'un agent (ce qu'il fait au runtime) en relation avec le moteur
> de DISCOVERY (ce que sa source declare), et lire le desaccord entre les deux.

## Le modele mental -- discovery PREDIT, comportement MESURE

Deux moteurs observent le meme agent par des bouts opposes :

- **Discovery** lit la SOURCE (`corpus/repos/<slug>`, un vrai repo publiable
  statique). C'est un predicteur de risque STATIQUE : detection, action_pattern,
  cible, ordre de risque relatif, presence de policy. La ground-truth ne porte
  que des proprietes invariantes -- jamais un score opaque.
- **Le moteur d'analyse comportementale** lit la preuve RUNTIME (bundles
  ebpf / proxy / action-log). Il MESURE ce que l'agent a reellement fait :
  egress, dns, credential, doh, process, said-vs-done, et un `behavioral_score`.

La valeur recherche est l'accord -- et surtout le desaccord -- entre la
prediction statique et la mesure runtime :

|                  | runtime propre  | runtime sale                            |
|------------------|-----------------|-----------------------------------------|
| source bas-risque| agree_clean     | **static_blind** (faux negatif du scanner) |
| source haut-risque| static_overflag| agree_dirty                             |

`static_blind` -- une source que le scanner a jugee propre mais qui se comporte
salement au runtime -- est le signal phare. C'est la ou une revue purement
statique aurait rate une vraie menace.

## La carte d'identite -- `corpus/agent_links.json`

Les sujets discovery et les sujets runtime sont des objets de corpus distincts.
Ils sont joints par `corpus/agent_links.json` : une entree par `agent_id`,
nommant son `discovery_subject` (un repo) et son `runtime_subject` /
`evidence_bundle`. C'est une ground-truth hand-maintenue jusqu'a l'existence des
jumeaux 1:1 (P3). Un lien sans sujet discovery resolvable ou sans preuve runtime
est reporte loud (`unresolved[]`), jamais avale silencieusement.

## Flux jour-le-jour

1. **Risque statique** -- lance le scorecard discovery :
   ```
   python3 -m recette discovery --adapter reference
   ```
   C'est la prediction cote source (detection par repo + ordre de risque relatif).

2. **Preuve runtime** -- construis / rafraichis les evidence bundles (corpus
   d'abord, deterministe) et lance des vagues comportementales :
   ```
   python3 -m recette analyze wave --evidence <bundle> --profile <profile.json>
   ```
   Chaque vague est pure (I4) : meme `(evidence, profile)` -> rapport byte-identique.

3. **Correler** -- joins les deux moteurs via la carte d'identite :
   ```
   python3 -m recette analyze correlate
   ```
   Affiche la matrice de quadrants. Lis la ligne `static_blind` en premier. Les
   lignes `unresolved` et coverage-gap montrent exactement quels liens n'ont pas
   pu etre resolus a l'etat actuel du corpus (la frontiere honnete P1).

4. **Inspecter static_blind** -- pour chaque agent de ce quadrant, ouvre son
   trois-temps (PLANNED / SAID / DONE) et ses findings OWASP ASI 2026 + MITRE
   ATLAS pour voir CE QU'il a fait que le scan de source a rate.

5. **Metrologie** -- transforme une correlation en mesure :
   - `python3 -m recette analyze sweep ...` -- fait varier un knob (ex le seuil
     `runtime_dirty`) -> ROC de "le risque statique predit-il le comportement
     runtime ?".
   - `python3 -m recette analyze ablate ...` -- delta de detection par lens.
   - `python3 -m recette analyze export ...` -- un package d'experience citable.
     La correlation porte sa provenance (`tool_version`, `thresholds`), donc un
     resultat est reproductible.

6. **Console** -- la page Probe heberge le **panneau Correlation** : la grille de
   quadrants 2x2 (static_blind en accent alerte), un knob de seuil `runtime_dirty`
   qui relance la correlation en direct, la ligne de provenance, et un bloc
   explicite unresolved / coverage-gap. Clique une cellule pour voir ses agents.

## Lire le resultat honnetement (frontiere P1)

En P1, la carte d'identite paire les sujets qui existent deja des deux cotes ;
les liens sans preuve runtime apparaissent en `evidence_missing` dans
`unresolved[]`. C'est attendu et visible par conception -- ce n'est pas un bug,
c'est la frontiere de couverture. P2 laisse un scan discovery alimenter une
cohorte de vague directement ; P3 construit les evidence bundles jumeaux 1:1 par
sujet discovery et ferme les trous (le coverage guard passe alors rouge sur tout
sujet discovery non lie).

## Determinisme et provenance (pourquoi c'est publiable)

- `correlate` est une fonction pure de `(discovery_facts, behavior_reports,
  links, thresholds)` -- pas d'horloge, pas de random, sortie triee,
  byte-identique au replay (I4). Le scan discovery de reference est lui-meme
  deterministe.
- `static_flagged` est derive de proprietes discovery invariantes (detection +
  niveau de risque + action_pattern), jamais d'un score statique opaque -- la
  correlation respecte donc la regle de ground-truth discovery.
- Chaque correlation reporte ses `thresholds` + `tool_version`, donc une
  affectation de quadrant est reproductible et citable.

## Voir aussi

- `docs/plans/2026-06-25-behavioral-analysis-engine-design.md` -- le moteur
  comportemental (evidence bundles, profils, lenses, couche recherche).
- `docs/plans/2026-06-25-behavior-discovery-correlation-design.md` -- ce design
  de correlation (approche A, phasage).
- `.claude/rules/recette-corpus.md` -- les trois formes d'un agent (runtime /
  identification / discovery) et pourquoi discovery ne voit jamais le runtime.
- `.claude/rules/redteam-standards-alignment.md` (R23) -- les tags OWASP ASI
  2026 + MITRE ATLAS que portent les findings.
