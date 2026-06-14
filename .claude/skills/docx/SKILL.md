---
name: docx
description: Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include any mention of "Word doc", "word document", ".docx", or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a "report", "memo", "letter", "template", or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation.
---

# DOCX Creation, Editing, and Analysis v3.0

A .docx file is a ZIP archive containing XML files. This skill orchestrates multi-agent document workflows: collection, analysis, generation, validation, and traceability.

## Architecture Multi-Agent

| Step | Role | Responsibility |
|------|------|----------------|
| 1. Input analysis | COLLECTOR | Read source files, extract content, identify format (create/edit/convert) |
| 2. Structure planning | ANALYST | Determine sections, styles, page layout, TOC needs |
| 3. Content generation | EXECUTOR | Generate JavaScript (docx-js) or edit XML directly |
| 4. Validation | ANALYST | Run `validate.py`, verify rendering, check schema compliance |
| 5. Fix loop | EXECUTOR | Fix validation errors, re-validate (max 3 iterations) |
| 6. Traceability | LIBRARIAN | Log decisions, archive output, update action journal |

## Quality Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| PRE_GENERATE | Before docx-js script execution | Verify all imports exist, page size set explicitly, no unicode bullets |
| POST_VALIDATE | After `validate.py` runs | If exit != 0, EXECUTOR fixes XML and re-validates (max 3 retries) |
| POST_PACK | After `pack.py` creates .docx | Open with Read tool to verify file size > 0, check content types |
| STYLE_CHECK | Before final delivery | Verify no hardcoded fonts (use Arial default), no WidthType.PERCENTAGE |

## Autonomy Levels

| Level | Description | When to use |
|-------|-------------|-------------|
| FULL | Autonomous end-to-end: collect, generate, validate, deliver | Simple documents, clear requirements |
| GUIDED | Execute with checkpoints: confirm structure before generation | Complex multi-section documents |
| SUPERVISED | Propose plan, wait for approval at each step | Templates, branded documents, legal content |
| MANUAL | Provide instructions only, user executes | Training, debugging existing documents |

## Quick Reference

| Task | Approach |
|------|----------|
| Read/analyze content | `pandoc` or unpack for raw XML |
| Create new document | Use `docx-js` - see Creating New Documents below |
| Edit existing document | Unpack, edit XML, repack - see Editing Existing Documents below |

### Converting .doc to .docx

```bash
python scripts/office/soffice.py --headless --convert-to docx document.doc
```

### Reading Content

```bash
# Text extraction with tracked changes
pandoc --track-changes=all document.docx -o output.md

# Raw XML access
python scripts/office/unpack.py document.docx unpacked/
```

### Converting to Images

```bash
python scripts/office/soffice.py --headless --convert-to pdf document.docx
pdftoppm -jpeg -r 150 document.pdf page
```

### Accepting Tracked Changes

```bash
python scripts/accept_changes.py input.docx output.docx
```

---

## Creating New Documents

Generate .docx files with JavaScript, then validate. Install: `npm install -g docx`

### Setup
```javascript
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
        Header, Footer, AlignmentType, PageOrientation, LevelFormat, ExternalHyperlink,
        TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
        VerticalAlign, PageNumber, PageBreak } = require('docx');

const doc = new Document({ sections: [{ children: [/* content */] }] });
Packer.toBuffer(doc).then(buffer => fs.writeFileSync("doc.docx", buffer));
```

### Validation
After creating the file, validate it. If validation fails, unpack, fix the XML, and repack.
```bash
python scripts/office/validate.py doc.docx
```

### Page Size

```javascript
// CRITICAL: docx-js defaults to A4, not US Letter
sections: [{
  properties: {
    page: {
      size: { width: 12240, height: 15840 },   // 8.5 x 11 inches in DXA
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
    }
  },
  children: [/* content */]
}]
```

**Common page sizes (DXA units, 1440 DXA = 1 inch):**

| Paper | Width | Height | Content Width (1" margins) |
|-------|-------|--------|---------------------------|
| US Letter | 12,240 | 15,840 | 9,360 |
| A4 (default) | 11,906 | 16,838 | 9,026 |

**Landscape orientation:** pass portrait dimensions and let docx-js handle the swap:
```javascript
size: { width: 12240, height: 15840, orientation: PageOrientation.LANDSCAPE },
```

### Styles (Override Built-in Headings)

Use Arial as the default font (universally supported). Keep titles black.

```javascript
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 } },
    ]
  },
  sections: [{ children: [
    new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Title")] }),
  ]}]
});
```

### Lists (NEVER use unicode bullets)

```javascript
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{ children: [
    new Paragraph({ numbering: { reference: "bullets", level: 0 },
      children: [new TextRun("Bullet item")] }),
  ]}]
});
// Same reference = continues numbering. Different reference = restarts.
```

### Tables

**CRITICAL: Tables need dual widths** - set both `columnWidths` on the table AND `width` on each cell.

```javascript
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [4680, 4680],
  rows: [new TableRow({ children: [
    new TableCell({
      borders, width: { size: 4680, type: WidthType.DXA },
      shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun("Cell")] })]
    })
  ]})]
})
```

**Width rules:** Always use `WidthType.DXA` (never PERCENTAGE). Table width = sum of columnWidths. Cell width must match corresponding columnWidth.

### Images

```javascript
new Paragraph({ children: [new ImageRun({
  type: "png",  // Required: png, jpg, jpeg, gif, bmp, svg
  data: fs.readFileSync("image.png"),
  transformation: { width: 200, height: 150 },
  altText: { title: "Title", description: "Desc", name: "Name" }
})]})
```

### Page Breaks

```javascript
new Paragraph({ children: [new PageBreak()] })
// Or: new Paragraph({ pageBreakBefore: true, children: [new TextRun("New page")] })
```

### Table of Contents

```javascript
new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" })
```

### Headers/Footers

```javascript
sections: [{
  properties: { page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
  headers: { default: new Header({ children: [new Paragraph({ children: [new TextRun("Header")] })] }) },
  footers: { default: new Footer({ children: [new Paragraph({
    children: [new TextRun("Page "), new TextRun({ children: [PageNumber.CURRENT] })]
  })] }) },
  children: [/* content */]
}]
```

### Critical Rules for docx-js

- **Set page size explicitly** - defaults to A4
- **Landscape: pass portrait dimensions** - docx-js swaps internally
- **Never use `\n`** - use separate Paragraph elements
- **Never use unicode bullets** - use `LevelFormat.BULLET`
- **PageBreak must be in Paragraph**
- **ImageRun requires `type`**
- **Always use `WidthType.DXA`** - never PERCENTAGE
- **Tables need dual widths** - columnWidths + cell width must match
- **Use `ShadingType.CLEAR`** - never SOLID
- **TOC requires HeadingLevel only**
- **Override built-in styles** with exact IDs: "Heading1", "Heading2"
- **Include `outlineLevel`** in heading styles for TOC

---

## Editing Existing Documents

**Follow all 3 steps in order.**

### Step 1: Unpack
```bash
python scripts/office/unpack.py document.docx unpacked/
```
Use `--merge-runs false` to skip run merging.

### Step 2: Edit XML

Edit files in `unpacked/word/`. For XML reference patterns (tracked changes, comments, images), see `references/xml-reference.md`.

**Use "Claude" as the author** for tracked changes and comments, unless the user requests a different name.

**Use the Edit tool directly for string replacement. Do not write Python scripts.**

**CRITICAL: Use smart quotes for new content:**

| Entity | Character |
|--------|-----------|
| `&#x2018;` | left single quote |
| `&#x2019;` | right single quote / apostrophe |
| `&#x201C;` | left double quote |
| `&#x201D;` | right double quote |

**Adding comments:**
```bash
python scripts/comment.py unpacked/ 0 "Comment text with &amp; and &#x2019;"
python scripts/comment.py unpacked/ 1 "Reply text" --parent 0
python scripts/comment.py unpacked/ 0 "Text" --author "Custom Author"
```

### Step 3: Pack
```bash
python scripts/office/pack.py unpacked/ output.docx --original document.docx
```
Validates with auto-repair. Use `--validate false` to skip.

**Auto-repair fixes:** durableId overflow, missing xml:space="preserve".
**Auto-repair does NOT fix:** malformed XML, invalid nesting, missing relationships.

### Common Pitfalls

- **Replace entire `<w:r>` elements** for tracked changes - don't inject tags inside a run
- **Preserve `<w:rPr>` formatting** - copy original run properties into tracked change runs

---

## Adaptation and Replanification

- If validation fails 2 consecutive times with the same error: invoke /replan to reassess the approach
- If docx-js produces invalid XML 2 times: switch to unpack/edit/repack approach
- NEVER improvise a workaround without logging the decision -- use the decision log
- If a dependency is missing (pandoc, LibreOffice, docx npm): report immediately, do not mock output

## Traceability

Every non-trivial document operation MUST be traced:

**Decision log** (for architectural choices):
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"docx-gen","action":"CHOSE_DOCX_JS","reasoning":"new document with TOC and headers","alternatives_rejected":["xml-edit: overkill for new doc"],"outcome":"success","confidence":"high","plan_ref":null}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

**Action journal** (for each step executed):
- Log: approach chosen (docx-js vs XML edit), validation result, fix iterations, final file path
- Format: append to decision_log.jsonl with action = DOCX_CREATED / DOCX_EDITED / DOCX_VALIDATED / DOCX_FIX_APPLIED

## Dependencies

- **pandoc**: Text extraction
- **docx**: `npm install -g docx` (new documents)
- **LibreOffice**: PDF conversion (auto-configured via `scripts/office/soffice.py`)
- **Poppler**: `pdftoppm` for images

## Scoring Agentique

| Critere | Description | Points |
|---------|-------------|--------|
| C1 Autonomie | Skill executes end-to-end without unnecessary user prompts | /10 |
| C2 Qualite | Output validates (validate.py exit 0), correct styles, no rendering issues | /10 |
| C3 Tracabilite | All decisions logged, action journal complete, plan updated | /10 |
| C4 Adaptation | Failures handled via fix loop or /replan, no silent errors | /10 |
| C5 Efficacite | Minimal iterations, correct approach chosen first time | /10 |
| **TOTAL** | | **/50** |
