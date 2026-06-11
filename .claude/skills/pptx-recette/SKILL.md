---
name: pptx-recette
description: Recette visuelle d'un export PPTX LIA-SEC. Boucle autonome VALIDATE -> EVALUATE -> FIX. Convertit le .pptx genere (dashboard EBIOS, ISO 27005, investor pitch) en PNG par slide via libreoffice headless, detecte slides vides / charts non rendus / texte tronque, produit un rapport visuel + verdict SUCCESS/PARTIAL/FAILURE. Composes with /konrad-kurze (meta-cognitive auditor invoked before the 3rd FIX iteration on the same check). Se declenche sur "/pptx-recette", "test le pptx", "recette visuelle du deck", "valide l'export slides", ou apres toute modification d'un generateur PPTX (ebios_rm_v2_dashboard_pptx.go, iso27005_dashboard_pptx.go, generate.js).
---

# pptx-recette v1.0 -- Visual recette of PPTX exports

## Why this skill exists

RETEX 2026-04-15 (PPTX COPIL-grade upgrade) documented "Aucune validation visuelle : les 63 slides
generees n'ont pas ete ouvertes dans LibreOffice/PowerPoint pour valider le rendu. Confiance basee
sur le code. Les proportions radar/bubble peuvent etre off sans que je le sache." -> FAILURE mode
5. This skill closes that gap with automated visual recette.

## Scope

Applies to any PPTX produced by LIA-SEC:
- `cmd/sigma_web/ebios_rm_v2_dashboard_pptx.go` + `_advanced.go` (33 slides)
- `scripts/iso27005_dashboard_pptx/generate.js` (30 slides)
- Investor pitch decks under `_alire/tracking/investor_pitch_liascan_2026-04-11/deliverables/`
- Any future `*_pptx.go` generator

## Autonomous loop

```
OBJECTIVE -> VALIDATE -> EVALUATE -> (FIX if FAILURE) -> re-VALIDATE -> LOOP or COMPLETE
```

## Prerequisites

```bash
sudo apt install -y libreoffice-core libreoffice-impress imagemagick poppler-utils
```

Verify:
```bash
which soffice && which convert && which pdftoppm
```

If missing -> escalate to user (install requires sudo). Do not proceed without soffice.

## Phase 1 : OBJECTIVE (parse input)

Input forms:
- `/pptx-recette {path/to/file.pptx}` -- recette a specific file
- `/pptx-recette --endpoint=/api/ebios/dashboard/export/pptx --study-id=X` -- trigger export then recette
- `/pptx-recette --generator=ebios` -- find latest .pptx from that generator in `_alire/temp/`

Expected slide count (from SYNTHETIC_DATA.md or SKILL input):
- ebios : 33
- iso27005 : 30
- investor-pitch : varies per version

## Phase 2 : VALIDATE (visual checks)

Script: `scripts/pptx_visual_recette.sh <pptx_file> <expected_slide_count>`

Checks performed:

| # | Check | Tool | Threshold |
|---|-------|------|-----------|
| V1 | File exists and > 10 KB | `stat` | size > 10240 |
| V2 | File parses as PPTX (ZIP with ppt/presentation.xml) | `unzip -l` | presentation.xml present |
| V3 | LibreOffice headless conversion to PDF succeeds | `soffice --headless --convert-to pdf` | exit 0, PDF created |
| V4 | Actual slide count matches expected | `pdfinfo Pages` | equals expected_count |
| V5 | PDF size reasonable (not corrupt) | `stat` PDF | size > 50 KB |
| V6 | Per-slide PNG rendering succeeds | `pdftoppm -png` | N PNGs created |
| V7 | No "blank" slide (PNG < 5 KB suggests empty) | `stat` each PNG | all > 5120 |
| V8 | No soffice warnings about missing fonts / broken charts | parse soffice log | zero warnings on "chart", "font" |
| V9 | PPTX XML has no literal `{placeholder}`, `TODO`, `FIXME`, `lorem`, `example.com` | `unzip -p ppt/slides/*.xml \| grep -iE ...` | zero matches |
| V10 | Text truncation heuristic : any slide PNG width/height ratio vs standard 16:9 | `identify` ImageMagick | 1.77 +/- 0.05 |

Output : `pptx_recette_report.md` with per-check status + artifact dir `pptx_recette_artifacts/` containing the PDF + N PNGs.

## Phase 3 : EVALUATE

Verdict:

| Condition | Verdict |
|-----------|---------|
| V1-V6 all PASS + V9 PASS | **SUCCESS** |
| V1-V6 PASS but V7 or V8 WARN (blank/font warning) | **PARTIAL** |
| Any of V1-V6 FAIL or V9 FAIL (placeholder detected) | **FAILURE** |

## Phase 4 : FIX (autonomous loop on FAILURE)

- V1/V2 FAIL (file corrupt) -> inspect generator output (Go `w.Header().Set(...)` vs actual write, Node `pres.writeFile` exit code)
- V3 FAIL (soffice conversion) -> read `/tmp/soffice-*.log`, common causes: XML malformed, unsupported chart type, embedded font
- V4 FAIL (slide count mismatch) -> `grep -cE "pres.addSlide\|slides = append" generator_file` vs expected, identify missing insertion
- V7 FAIL (blank slide) -> open specific PNG, identify empty-state guard failure -> fix the slide function
- V9 FAIL (placeholder) -> grep the generator for the literal, replace with real data source

Each fix : ACT -> re-run VALIDATE -> EVALUATE -> LOOP if still not SUCCESS.

After 2 consecutive FAILURE iterations on the same check (V1..V9), invoke the
Konrad-Kurze meta-cognitive gate BEFORE the 3rd iteration that would escalate:

- Invoke `/konrad-kurze` via the Skill tool (model: **sonnet**) with scope =
  `pptx-recette/{deck_name}/V{N}`. Pass the soffice log slice, the offending
  PNG path, the generator file path, and the previous fix attempts as
  evidence.
- Read the directive at `_alire/02_LOGS/Journals/meta/directives/KD-{id}.json`.
- If `risk_level = LOW` AND `injection.operation = ADD` AND
  `requires_approval = false`: apply the directive as the 3rd fix (e.g. adding
  a guard for an empty dataset, removing an unsupported chart type, switching
  to a safe font fallback). Log `action="KONRAD_DIRECTIVE_APPLIED"`.
- Otherwise: surface the directive to the user along with the ESCALATE
  message. Do not auto-apply.

Particularly useful classifications here:
- META_DATA_AMNESIA: the generator received an empty dataset (the upstream
  module has no data to render). The fix belongs upstream, not in the
  generator's draw code.
- PHYSICAL_VISUAL_MISMATCH: the chart code compiles and the slide count is
  correct, but the rendered visual is empty / overlapped / illegible. The
  generator needs visual guards (chart-external-labels R23, theme-aware
  colors R25).
- LEMANRUSS_TAINT: the loop is "fixing" V7 (blank slide) when the real cause
  is V3 (soffice failed silently and produced 0-byte PNGs). The cause was
  misclassified upstream.

Max 3 iterations before escalating to user (with the Konrad directive
included if emitted).

## Phase 5 : RETEX (mandatory display)

```markdown
## RETEX /pptx-recette

File: {path}
Generator: {ebios|iso27005|pitch}
Expected slides: {N}
Actual slides: {M}

| Check | Status |
|-------|--------|
| V1 File size | PASS/FAIL |
| V2 ZIP parse | PASS/FAIL |
| ... | ... |

Visual artifacts: `pptx_recette_artifacts/slide_NN.png` (N files)

Verdict: SUCCESS | PARTIAL | FAILURE

Improvements for next iteration:
- ...
```

## Integration with apex / audit-pdca

When `/apex` or `/audit-pdca` modifies a `*_pptx.go` or `generate.js` generator, Phase RECETTE MUST
invoke `Skill({skill: "pptx-recette", args: "{generated_pptx_path}"})` before declaring SUCCESS.
Without this visual gate, charts with wrong proportions / empty slides ship silently.

## Artifacts (gitignored)

- `_alire/temp/pptx_recette/<timestamp>/report.md`
- `_alire/temp/pptx_recette/<timestamp>/*.pdf` + `*.png`
- Clean up after 7 days: `find _alire/temp/pptx_recette/ -mtime +7 -delete`

## References

- `.claude/skills/pptx-recette/scripts/pptx_visual_recette.sh` : main validator
- RETEX source : `_alire/02_LOGS/Journals/retex/RETEX_PPTX_COPIL_GRADE_2026-04-15.md`
- Generators : `cmd/sigma_web/ebios_rm_v2_dashboard_pptx*.go`, `scripts/iso27005_dashboard_pptx/generate.js`
