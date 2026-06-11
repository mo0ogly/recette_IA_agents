---
name: codeeditor-migrate
description: Scans a React .tsx file for legacy <TextField multiline rows={>=6}> that are being used to edit code (YAML/JSON/markdown/other) and migrates them to the universal <CodeEditor> from src/components/common/CodeEditor.tsx. Triggers on "/codeeditor-migrate <file>", "migrate textarea to CodeEditor in <file>", "remplace les textarea par CodeEditor", "detect editor candidates". Reference doc for the CodeEditor component -- _alire/01_DOCUMENTATION/technical/code_editor_component_tech_en.md.
model: sonnet
---

# /codeeditor-migrate -- Automated migration to the universal CodeEditor

## What it does

Given a React `.tsx` file path, this skill :

1. Scans the file for `<TextField multiline rows={N>=6}>` blocks (threshold 6 lines = code, below = free text)
2. For each candidate, infers the language :
   - `yaml` if `yaml.dump(` / `yaml.load(` is visible around the value/onChange
   - `json` if `JSON.stringify(` / `JSON.parse(` is visible around the value/onChange
   - `markdown` if the field name or placeholder hints at Markdown (body, description, content, md...)
   - `plaintext` otherwise
3. Replaces the `<TextField>` block by a `<CodeEditor value=... onChange=... language="..." height={...} logScope="..." />` preserving behaviour (read-only, placeholder via caption, error fallback via ErrorBoundary)
4. Adds the import `import CodeEditor from '../common/CodeEditor';` if absent (adjust relative path)
5. Runs `vite build` to verify zero TS errors

The intent is to avoid the 10-15 min of manual migration done in the APEX Monaco universal cycle (2026-04-20, commit 3d017d8bf3).

## When to invoke

- The user writes `/codeeditor-migrate path/to/File.tsx`
- The user writes `/codeeditor-migrate --auto path/to/File.tsx` (bulk mode, see below)
- The user asks "migrate the textareas in X to CodeEditor"
- A reviewer flags that a new component re-introduces `<TextField multiline rows={20}>` for YAML/JSON content
- Before merging a new component that handles code content via TextField

Do NOT invoke for :
- `<TextField multiline rows={N<6}>` blocks (those are free-text descriptions, rationale, single-line)
- `<TextField>` without `multiline`
- Files outside `sigma-react-frontend/src/`

## Flags

| Flag | Behavior |
|------|----------|
| `--auto` | Skip the per-candidate confirmation (Step 2). Apply all detected candidates in one pass. Still runs the build gate + the long-file gate. Use for bulk migrations when the scan output has already been reviewed. |
| `--dry-run` | Only print the detection report (Step 1). Do not modify any file. Use to preview what `--auto` would do. |
| `--language=<yaml\|json\|markdown\|plaintext>` | Force a single language for all candidates in the file. Overrides the heuristic from Step 1. Use when the heuristic guesses plaintext but the content is actually YAML/JSON and the context strings are unusual. |

The flags are parsed from the user's message. Default (no flag) : confirm-each-candidate mode.

## Workflow (ACT-OBSERVE-EVALUATE loop)

### Step 1 : Detect candidates

Run the helper script :

```bash
.claude/skills/codeeditor-migrate/scripts/detect-candidates.sh <absolute-file-path>
```

The script outputs a JSON list of candidates with : line number, rows count, inferred language, whether the field uses `yaml.dump`/`JSON.stringify` nearby, and the likely component label.

### Step 2 : Confirm with the user (SKIPPED in --auto mode)

**Default (no flag) :** for each candidate, ask :

```
Line 1826-1855 : rows=6, language=yaml (yaml.dump visible at line 1830)
  -> Migrate to : <CodeEditor language="yaml" height={160}>
  Y/n ?
```

If the user confirms, proceed. If rejected, skip that candidate.

**`--auto` mode :** skip the prompt entirely. Print a compact summary instead :

```
[auto] 6 candidates detected in SigmaEditorLegacy.tsx :
  - line 1826 rows=6  language=yaml  height=160
  - line 1868 rows=6  language=yaml  height=160
  - line 1929 rows=8  language=yaml  height=218
  - line 1965 rows=20 language=yaml  height=530
  - line 2148 rows=12 language=yaml  height=322
  - line 3643 rows=30 language=yaml  height=790
[auto] Applying all 6 migrations without per-candidate confirmation.
```

Apply every candidate. If a candidate FAILS the build gate, REPLAN
(per APEX conventions) -- do not silently skip.

**`--dry-run` mode :** print the summary above and STOP. Do not modify any
file. Do not run the build gate. Exit with status OK.

### Step 3 : Apply migration (1 candidate at a time, or batch in --auto)

In `--auto` mode, process candidates in REVERSE line order (highest line number first) so earlier edits do not shift the line numbers of later candidates. In default mode, the user may pick candidates in any order -- the same reverse-order rule applies if the user accepts multiple.


For each confirmed candidate, use the Edit tool to replace the TextField block. Pattern :

**Before**
```tsx
<TextField
    fullWidth
    multiline
    rows={6}
    value={X ? yaml.dump(X, {...}) : ''}
    onChange={(e) => {
        try {
            const parsed = yaml.load(e.target.value);
            setX(parsed);
        } catch (err) { /* ignore */ }
    }}
    placeholder="..."
    sx={{ fontFamily: 'inherit' }}
    helperText="YAML format"
/>
```

**After**
```tsx
<Box>
    <CodeEditor
        value={X ? yaml.dump(X, {...}) : ''}
        onChange={(val: string) => {
            try {
                const parsed = yaml.load(val);
                setX(parsed);
            } catch (err) { /* ignore */ }
        }}
        language="yaml"
        height={160}
        logScope="ComponentName.fieldName"
    />
    <Typography variant="caption" color="text.secondary">
        YAML format
    </Typography>
</Box>
```

Important transformations :
- `onChange={(e) => ... e.target.value}` -> `onChange={(val: string) => ... val}`
- `rows={N}` -> `height={N * 26 + 10}` (26 px per row + padding). For markdown with preview, default 400-560.
- `helperText` -> `<Typography variant="caption" color="text.secondary">`
- `readOnly` / `InputProps.readOnly: true` -> `readOnly` prop on CodeEditor
- `sx={{ fontFamily: 'inherit' }}` -> nothing (CodeEditor handles theme fontFamily)
- `placeholder` -> drop (CodeEditor does not accept placeholder ; the empty state is visible)

### Step 4 : Import gate

Ensure `import CodeEditor from '../common/CodeEditor';` is present. Resolve the relative path based on the file depth :
- `components/X/File.tsx` -> `'../common/CodeEditor'`
- `components/X/Y/File.tsx` -> `'../../common/CodeEditor'`
- `components/X/Y/Z/File.tsx` -> `'../../../common/CodeEditor'`

If the file declares a local `styled(TextField)` wrapper named `CodeEditor`, rename it to `StyledCodeTextField` to avoid shadowing.

### Step 5 : Verify build

```bash
cd sigma-react-frontend && NODE_OPTIONS="--max-old-space-size=8192" node node_modules/.bin/vite build 2>&1 | grep -iE "error|transformed" | head -10
```

Zero TypeScript / Rollup error is required. If build fails :
- Check that all imports resolve
- Check that the TextField -> CodeEditor signature is correct (value/onChange/language/height)
- REPLAN if necessary (per APEX conventions)

### Step 6 : Long-file directive

If the migrated file exceeds 400 LOC (React) or 500 LOC (TS), add at the top :

```tsx
// @allow-long-file -- legacy component (XXXX LOC), deferred refactor. TODO: decompose into subcomponents using CodeEditor as base brick.
```

(The pre-commit hook enforces this.)

### Step 7 : Commit

Conventional commit, scope `frontend`, type `refactor` :

```
refactor(frontend): migrate {ComponentName} to universal CodeEditor (N zones)

- Replace {N} <TextField multiline rows={M>=6}> blocks with <CodeEditor>
- Languages : {yaml:2, json:1, markdown:0}
- Preserves read-only, error handling, behavioural contracts
- Build green ({modules} modules transformed)
- Reference : _alire/01_DOCUMENTATION/technical/code_editor_component_tech_en.md
```

## Language inference heuristics

| Signal (around value/onChange) | Inferred language |
|--------------------------------|-------------------|
| `yaml.dump(` or `yaml.load(` | yaml |
| `JSON.stringify(` or `JSON.parse(` | json |
| `label` contains "Markdown" or "body" or "content" or ".md" | markdown |
| file path in `cyber-skills/` or `docs/` | markdown |
| placeholder starts with `#` | markdown |
| field name contains "yaml" / "sigma" / "rule" | yaml |
| field name contains "json" / "test_data" / "payload" | json |
| none of the above | plaintext |

When the signal is ambiguous (both yaml and json visible), prefer the language that appears CLOSEST to the TextField (line distance).

## Heuristics for height

| Original rows | Target height (px) |
|---------------|--------------------|
| 6 | 160 |
| 8 | 200 |
| 10 | 260 |
| 12 | 300 |
| 15 | 380 |
| 20 | 480 |
| 30 | 640 |

Formula : `height = rows * 26 + 10`. Override to 400 minimum for dashboards/previews, 640 maximum when wrapped in a dialog.

## Anti-patterns to avoid

- Do NOT migrate `<TextField rows={2-5}>` (free text, migration would harm UX)
- Do NOT migrate `<TextField>` that is a search input, a single-line label editor, or a descriptive field
- Do NOT drop the surrounding `<Typography variant="caption">` that replaces `helperText` -- users rely on it
- Do NOT import CodeEditor from a random path -- always relative from the current file to `components/common/CodeEditor`
- Do NOT inline `<pre>{content}</pre>` instead of CodeEditor for code display -- violates the library rule

## Related

- Reference doc : `_alire/01_DOCUMENTATION/technical/code_editor_component_tech_en.md`
- APEX cycle that introduced the component : `_alire/tracking/PLAN_APEX_MONACO_UNIVERSAL_EDITOR_2026-04-20.md`
- Frontend library section : `sigma-react-frontend/CLAUDE.md` (top of file)
- YAML schema for Sigma rules : `sigma-react-frontend/src/schemas/sigma-rule.schema.json`
