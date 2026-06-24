# Presentation decks -- source

Reproducible source for the two `inspect_ia_agents` presentation decks. The
built `.docx` deliverables live at the repository root
(`inspect_ia_agents-presentation.docx`, `inspect_ia_agents-presentation-simple.docx`);
this directory is what regenerates them.

## Files

| File | Role |
|------|------|
| `build.js` | Technical deck (full jargon, audience: engineers / RSSI). |
| `build-simple.js` | Plain-language deck (same content + functions, no jargon, audience: managers / non-specialists). |
| `png/` | The 10 diagrams embedded as figures (rendered from `mmd/`). |
| `mmd/` | Mermaid sources for the diagrams (edit these, then re-render the png). |
| `package.json` | Pins `docx` (9.6.1) so the build is reproducible. |

## Build

```
cd docs/deck
npm install
npm run build:all
```

`build:all` writes both `.docx` next to the scripts. Copy them to the repo root
to update the committed deliverables:

```
cp inspect_ia_agents-presentation.docx inspect_ia_agents-presentation-simple.docx ../../
```

Individual builds: `npm run build` (technical) / `npm run build:simple` (plain).

## Re-rendering the diagrams

The `png/` are produced from `mmd/` with the Mermaid CLI:

```
npx @mermaid-js/mermaid-cli -i mmd/<name>.mmd -o png/<name>.png
```

## The "En chiffres" numbers

The counts in the decks (actions, AnnexC, discovery, red-team, templates,
providers, ...) are NOT hand-typed: derive them from the code with the single
source of truth and paste/update the tables:

```
python3 -m scripts.deck_metrics
```

This prevents the drift the deck verification surfaced (e.g. AnnexC 124 -> 148,
discovery 20 -> 22, red-team 15 -> 13).
