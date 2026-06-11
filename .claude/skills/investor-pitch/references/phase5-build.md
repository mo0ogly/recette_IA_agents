# Phase 5 -- BUILD

**Goal:** Generate the .pptx file from the validated outline using the `pptx` skill. Produce speaker notes in parallel.

**Complexity:** COMPLEX
**Dependencies:** Phase 4 G4 USER VALIDATED (BLOCKING)
**Output:** deliverables/pitch_v1.pptx, deliverables/speaker_notes.md

## Critical pre-condition

If `deliverables/deck_outline.md` does NOT contain a `Status : VALIDATED` line, STOP. Re-present G4 to the user. NEVER build a draft outline.

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 5.1 | Pre-build screenshot prep | Bash + ImageMagick optional | All screenshots resized to consistent dimensions |
| 5.2 | Pre-build diagram generation | Mermaid CLI / canvas-design | Diagrams rendered as PNG, named consistently |
| 5.3 | Theme selection | brand-guidelines OR theme-factory OR custom | Theme picked, palette + fonts documented |
| 5.4 | Invoke pptx skill with the outline | Skill tool : pptx | pitch_v1.pptx exists and opens |
| 5.5 | Generate speaker notes | Write | speaker_notes.md per-slide notes |
| 5.6 | Smoke test : open the .pptx | Bash : `unzip -l` | At least N slide entries returned |
| 5.7 | Iterate if pptx skill returns errors | (loop) | Build succeeds |

## Theme selection guide

| User context | Recommended theme |
|--------------|------------------|
| Cyber/security product, deep-tech audience | "cyber pro" : dark navy + electric accent (orange/teal), monospace headlines |
| Compliance/GRC product, enterprise audience | "executive" : grey/white + corporate blue, serif headlines |
| AI product, generalist VC | "minimal" : white/black + bold accent, sans-serif |
| Industrial/IoT product | "industrial" : steel grey + safety orange |
| User has brand assets | use `brand-guidelines` skill with their assets |

The theme is documented in `deliverables/theme.md` for future iterations.

## Invoking the pptx skill

```
Skill({
  skill: "pptx",
  args: "Generate a {N}-slide investor deck from the outline at {PITCH_DIR}/deliverables/deck_outline.md. Theme : {theme name}. Output to {PITCH_DIR}/deliverables/pitch_v1.pptx. Each slide must have title, content bullets, and the visual specified in the outline. Embed screenshots from {PITCH_DIR}/platform/screenshots/. Embed diagrams from {PITCH_DIR}/deliverables/diagrams/. Use the speaker_notes.md as notes attached to each slide."
})
```

If the pptx skill fails on a specific slide:
- Read its error message
- Identify the offending element (image too large, missing file, malformed bullet)
- Fix in the outline OR pre-process the asset
- Retry once
- If second failure -> /replan with simplified slide

## Speaker notes structure

```markdown
# Speaker Notes -- {PRODUCT}

## Slide 1 : Cover
{1-2 sentence intro line you say while the cover is up}

## Slide 2 : The problem
{Talking points :}
- {opening hook}
- {key statistic to mention}
- {transition to next slide}

Time budget : 30 seconds
```

Total time budget should match the user's pitch time (usually 5/10/20 minutes for investor pitches).

## Smoke test

```bash
unzip -l "${PITCH_DIR}/deliverables/pitch_v1.pptx" | grep -c "ppt/slides/slide" 
# Must equal N (the slide count)

# Open it locally if possible
file "${PITCH_DIR}/deliverables/pitch_v1.pptx"
# Must show "Microsoft PowerPoint 2007+" or "Zip archive"
```

If smoke test fails -> the build did not produce a valid .pptx -> /replan or retry with different pptx parameters.

## Anti-patterns in this phase

- Building from a draft outline (no Status : VALIDATED)
- Reimplementing slide generation instead of calling pptx skill
- Inventing screenshots that do not exist in phase 1
- Embedding low-resolution screenshots
- Skipping speaker notes because "the user will write them"
- Picking a flashy theme that contradicts the audience
