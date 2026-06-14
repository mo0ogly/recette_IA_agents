---
name: doc-librarian
description: >
  Manages the complete LIA-SEC documentation workflow: metadata enrichment (.doc-meta.json files),
  Mermaid SVG pre-rendering (mmdc), Docusaurus 3 site build, and deploy to inspect-ia-agents.tech/docs/.
  Use when the user asks to: audit documentation coverage, enrich doc metadata, build the doc site,
  deploy docs to production, render Mermaid diagrams, identify doc gaps, or run the full doc pipeline.
  Triggers on: /doc-librarian, "build the doc site", "update doc metadata", "deploy docs",
  "render diagrams", "audit documentation", "doc pipeline", "SOMMAIRE update".
---

# Doc Librarian -- LIA-SEC Documentation Workflow

## Syntax

```
/doc-librarian [command] [options]

Commands:
  audit    -- Check metadata coverage, detect gaps (no writes)
  enrich   -- Fill empty descriptions/tags, normalize titles, approve foundational docs
  build    -- Pre-render Mermaid SVGs + run Docusaurus 3 build
  deploy   -- rsync docs-site/build/ to VPS /opt/lia-sec/source/docs-site/
  full     -- enrich + build + deploy in sequence
  sommaire -- Regenerate SOMMAIRE.md from current doc state

Options:
  --dry-run   Simulate writes (audit + enrich only)
  --approve   Promote foundational docs from DRAFT to APPROVED (enrich only)
```

## Source Layout

```
_alire/01_DOCUMENTATION/          <- SEUL repertoire doc (R15)
├── api/                           TYPE=API  (*_api_en.md)
├── architecture/                  TYPE=ARCH (*_arch_en.md)
├── technical/                     TYPE=TECH (*_tech_en.md)
├── user-guides/                   TYPE=USER (*_user_en.md)
├── security/                      TYPE=SEC  (*_sec_en.md)
├── specs/                         TYPE=SPEC (*_spec_en.md)
├── diagrams/                      Mermaid sources .mmd
│   └── svg/                       Pre-rendered SVG output (gitignored)
├── exports/                       Generated .docx (gitignored)
├── archive/                       Archived docs (NEVER deleted)
└── SOMMAIRE.md                    Table of contents + GAP markers

docs-site/                        Docusaurus 3 project (built artifact)
├── docusaurus.config.js
├── docs/ -> symlink to _alire/01_DOCUMENTATION/
└── build/                        Generated static site
```

## Decomposition des sous-taches

Identifier au demarrage selon la commande :
- **audit** : lire les .doc-meta.json, compter descriptions/tags manquants, compter GAP dans SOMMAIRE.md
- **enrich** : executer `scripts/enrich_metadata.py --approve` avec les options passees
- **build** : `./deploy.sh docs` (docusaurus build + Pagefind + rsync prod ; mmdc/render_diagrams VESTIGIAL, hors build)
- **deploy** : rsync build/ vers VPS + reload nginx
- **sommaire** : regen SOMMAIRE.md depuis etat actuel (lire INDEX.md + .doc-meta.json)
- Dependances : build depend de enrich (tags/descriptions utilises par Docusaurus search), deploy depend de build

## Plan d'execution

Creer `_alire/tracking/PLAN_DOC_LIBRARIAN_{YYYY-MM-DD}.md` avant toute action.
Template : `_alire/tracking/PLAN_TEMPLATE.md`.
Cocher chaque etape a la completion `[x]`.
Si replanification : Status -> REPLANIFIE, creer PLAN_*_REPLAN_*.md avec lien.

## Adaptation et replanification

- 1 echec : retry une fois avec parametres ajustes, log si non-bloquant
- 2 echecs consecutifs : STOP -> invoquer /replan -> NE PAS improviser
- Modification de > 10 fichiers sans verification intermediaire : STOP -> re-verification

## Outils declares

| Outil | Quand |
|-------|-------|
| Bash | enrich_metadata.py, ./deploy.sh docs (build+pagefind+rsync) |
| Read | lire .doc-meta.json ou .md specifique |
| Grep | chercher patterns dans les .mmd ou .md |
| Glob | trouver tous les .doc-meta.json ou .mmd |
| Edit | corriger un .mmd broken (%%{init}%% manquant) |
| Write | creer un nouveau doc ou SOMMAIRE.md |

Choix dynamique : Read si chemin exact connu, Glob si pattern, Grep si contenu inconnu.
Retry policy : 1 retry -> si 2eme echec -> log decision_log.jsonl + stop + signaler.

## Workflow Audit

```bash
# 1. Compter les .doc-meta.json sans description
cd /opt/lia-sec/dev
python3 scripts/enrich_metadata.py --dry-run

# 2. Compter les GAP dans SOMMAIRE
grep -c "GAP - A CREER" _alire/01_DOCUMENTATION/SOMMAIRE.md

# 3. VRAI chemin de rendu = fences ```mermaid dans les .md (rendus client-side par
#    mermaidClient.js, theme dark global). Compter les .md porteurs de fences.
#    NOTE: une fence sans %%{init} rend dark via la config globale -- ce n'est PAS un defaut.
#    Le pattern .mmd source (`grep -rL '%%{init' diagrams/*.mmd`) ne reflete PAS l'affichage.
echo "MD avec fence mermaid: $(grep -rln '```mermaid' _alire/01_DOCUMENTATION/ --include='*.md' 2>/dev/null | grep -v archive | wc -l)"
# Sanity : la config dark globale doit exister (sinon les fences nues rendraient en blanc)
grep -q "theme: 'dark'" docs-site/src/clientModules/mermaidClient.js && echo "global dark: OK" || echo "global dark: ABSENT (defaut blanc -- corriger mermaidClient.js)"

# 4. Rapport
echo "=== Doc Audit Report ==="
echo "Docs: $(find _alire/01_DOCUMENTATION -name '*.md' | grep -v archive | wc -l)"
echo "Meta: $(find _alire/01_DOCUMENTATION -name '*.doc-meta.json' | wc -l)"
echo "MMD source: $(find _alire/01_DOCUMENTATION/diagrams -name '*.mmd' | wc -l) (refs, pas le rendu)"
```

## Workflow Enrich

```bash
# Enrichissement complet avec approbation des docs fondationnels
python3 scripts/enrich_metadata.py --approve

# Dry-run pour preview
python3 scripts/enrich_metadata.py --dry-run --approve
```

Script : `scripts/enrich_metadata.py` (voir section Resources).
MODULE_MAPPING et APPROVED_DOCS list sont dans le script -- mettre a jour si nouveau module.

## Workflow Build

CHEMIN OFFICIEL = `./deploy.sh docs` (le hook `block_direct_build.sh` BLOQUE `npm run build`
direct ; deploy.sh appelle `node_modules/.bin/docusaurus build` + Pagefind + rsync prod).

```bash
# Build + Pagefind + rsync prod, en une commande VPS-aware
cd /opt/lia-sec/dev
./deploy.sh docs
# -> Docusaurus build, Pagefind index, rsync build/ -> /opt/lia-sec/source/docs-site/
```

> render_diagrams.sh (pre-rendu SVG via mmdc) est OPTIONNEL et VESTIGIAL : le rendu reel
> des diagrammes est client-side (`docs-site/src/clientModules/mermaidClient.js` ->
> `mermaid.initialize({theme:'dark'})`), `diagrams/svg/` n'est reference par AUCUN .md.
> NE PAS installer mmdc "pour la dette" -- ca produit des SVG que rien ne consomme.
> Le script reste pour un eventuel wiring SVG futur, mais ne fait PAS partie du build.

## Workflow Deploy

```bash
# Rsync vers VPS (depuis local) -- ou directement sur VPS si deja en dev/
rsync -avz --delete docs-site/build/ /opt/lia-sec/source/docs-site/

# Reload nginx (nginx lit l'alias /docs/ -> /opt/lia-sec/source/docs-site/)
sudo systemctl reload nginx

# Verification
curl -s -o /dev/null -w "%{http_code}" https://inspect-ia-agents.tech/docs/
# Doit retourner 200
```

Config Nginx : voir `references/nginx-config.md`.

## Corrections Mermaid (.mmd)

> RENDU REEL = client-side. Les diagrammes affiches sur le site sont les fences
> ` ```mermaid ` dans les `.md`, rendus par `docs-site/src/clientModules/mermaidClient.js`
> qui force `mermaid.initialize({theme:'dark'})` globalement (+ `themeConfig.mermaid.theme={light:'dark',dark:'dark'}`).
> Donc une fence SANS bloc `%%{init}` rend quand meme en dark (defaut global). Le bloc
> `%%{init}` per-diagramme ne sert qu'a des couleurs custom au-dela du theme dark.
>
> Le pre-rendu SVG (`render_diagrams.sh` -> `diagrams/svg/`) est VESTIGIAL : aucun `.md`
> ne reference `diagrams/svg/*.svg` (verifie 2026-05-29), et `mmdc` n'est pas installe sur
> le VPS. Ne PAS installer mmdc "pour la dette" : ca produit des SVG que rien ne consomme.
> Le bloc init dans les `.mmd` source reste utile pour rendre un `.mmd` en standalone.

Tout fichier `.mmd` DEVRAIT commencer par le bloc %%{init}%% (self-consistance standalone) :

```
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#0d1b2a', 'primaryTextColor': '#a8dadc', 'primaryBorderColor': '#1e6091', 'lineColor': '#00b4d8', 'secondaryColor': '#1a1a2e', 'tertiaryColor': '#0f3460', 'background': '#050d1a', 'mainBkg': '#0d1b2a', 'nodeBorder': '#1e6091', 'clusterBkg': '#0f1e30', 'titleColor': '#90e0ef', 'edgeLabelBackground': '#0f3460', 'fontSize': '14px', 'fontFamily': 'JetBrains Mono, monospace'}}}%%
```

Problemes courants et fix :
1. **%%{init}%% manquant** : prepend le bloc avant `graph TB` / `erDiagram` / `sequenceDiagram`
2. **Wrapped dans markdown fence** (` ```mermaid ... ``` `) : réécrire le fichier sans le wrapper
3. **Participant name multiligne** : `participant Main as Main Context\n(Orchestrator)` -> `participant Main as Main Orchestrator`

Detecter les .mmd broken :
```bash
# Sans %%{init}%%
grep -rL '%%{init' _alire/01_DOCUMENTATION/diagrams/*.mmd

# Avec fence markdown
grep -rl "^\`\`\`mermaid" _alire/01_DOCUMENTATION/diagrams/
```

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` pour toute decision non-triviale :
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"doc-librarian","action":"ACTION","reasoning":"...","alternatives_rejected":[],"outcome":"...","confidence":"high","plan_ref":"PLAN_doc-librarian_*.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_doc-librarian_{YYYY-MM-DD}.md`.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :
- [ ] `python3 scripts/enrich_metadata.py --dry-run` : 0 descriptions vides
- [ ] Build via `./deploy.sh docs` : sortie `[SUCCESS] Generated static files` + `Indexed N pages`
- [ ] `curl -o /dev/null -w "%{http_code}" https://inspect-ia-agents.tech/docs/` : 200, OU **401**
      (le bloc nginx `/docs/` est protege `auth_basic` .htpasswd-docs -- 401 = sert + gate OK,
      404/502 = casse). Verifier aussi `ls /opt/lia-sec/source/docs-site/index.html`.

Le check `.mmd %%{init}` N'EST PLUS dans la gate : le rendu est client-side dark global
(`mermaidClient.js`), donc une fence `.md` sans `%%{init}` rend quand meme dark. Voir
Workflow Audit etape 3 pour l'inspection du VRAI chemin de rendu (fences `.md`).

## Scoring agentique

| Critere | Description | Score |
|---------|-------------|-------|
| C1 Decomposition | Sous-taches identifiees au demarrage | /10 |
| C2 Planification | PLAN_*.md cree, suivi, cloture | /10 |
| C3 Replanification | /replan sur 2+ echecs consecutifs | /10 |
| C4 Outillage | Outils choisis dynamiquement | /10 |
| C5 Tracabilite | decision_log.jsonl + RETEX si < 40 | /10 |

Score total : /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Resources

- `scripts/enrich_metadata.py` -- Enrichissement metadonnees .doc-meta.json (descriptions, tags, titres, APPROVED)
- `scripts/render_diagrams.sh` -- VESTIGIAL : pre-rendu SVG via mmdc, HORS build (rendu reel = client-side dark, `diagrams/svg/` consomme par aucun .md). Conserve pour un wiring SVG futur eventuel.
- `references/docusaurus-config.md` -- Config Docusaurus 3 LIA-SEC (plugins, sidebar, theme)
- `references/nginx-config.md` -- Bloc Nginx /docs/ + rollback + verification
