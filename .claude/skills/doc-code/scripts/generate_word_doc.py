#!/usr/bin/env python3
"""
generate_word_doc.py - Generate Word documents (.docx) from Markdown

Converts LIA-SEC documentation (.md) to professional Word documents
with proper formatting, headers, tables, and code blocks.

Usage:
  python3 generate_word_doc.py <input.md> [output.docx]
  python3 generate_word_doc.py <input.md> --template <template.docx>

Dependencies: python-docx, lxml (install via setup.sh)
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

try:
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
except ImportError:
    print("python-docx not installed. Run: bash .claude/skills/doc-code/scripts/setup.sh")
    sys.exit(1)


# LIA-SEC brand colors
BRAND_PRIMARY = RGBColor(0x1F, 0x47, 0x88)    # Navy blue
BRAND_SECONDARY = RGBColor(0x2E, 0x75, 0xB6)  # Lighter blue
BRAND_TEXT = RGBColor(0x33, 0x33, 0x33)        # Dark gray


def parse_markdown(md_text: str) -> list:
    """Parse markdown into structured blocks."""
    blocks = []
    lines = md_text.split("\n")
    i = 0
    in_code = False
    code_block = []
    code_lang = ""
    in_table = False
    table_rows = []

    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.strip().startswith("```"):
            if in_code:
                blocks.append({"type": "code", "lang": code_lang, "content": "\n".join(code_block)})
                code_block = []
                in_code = False
            else:
                in_code = True
                code_lang = line.strip()[3:].strip()
            i += 1
            continue

        if in_code:
            code_block.append(line)
            i += 1
            continue

        # Tables
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            # Skip separator rows (|---|---|)
            if not re.match(r'^\|[\s\-:|]+\|$', line.strip()):
                cells = [c.strip() for c in line.strip().split("|")[1:-1]]
                table_rows.append(cells)
            i += 1
            continue
        elif in_table:
            blocks.append({"type": "table", "rows": table_rows})
            in_table = False
            table_rows = []

        # Headers
        if line.startswith("# "):
            blocks.append({"type": "h1", "text": line[2:].strip()})
        elif line.startswith("## "):
            blocks.append({"type": "h2", "text": line[3:].strip()})
        elif line.startswith("### "):
            blocks.append({"type": "h3", "text": line[4:].strip()})
        elif line.startswith("#### "):
            blocks.append({"type": "h4", "text": line[5:].strip()})
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({"type": "bullet", "text": line[2:].strip()})
        elif line.strip().startswith("> "):
            blocks.append({"type": "quote", "text": line.strip()[2:]})
        elif line.strip() == "---":
            blocks.append({"type": "hr"})
        elif line.strip():
            blocks.append({"type": "paragraph", "text": line.strip()})

        i += 1

    # Flush remaining
    if in_table and table_rows:
        blocks.append({"type": "table", "rows": table_rows})
    if in_code and code_block:
        blocks.append({"type": "code", "lang": code_lang, "content": "\n".join(code_block)})

    return blocks


def generate_docx(blocks: list, title: str, output_path: str, meta: dict = None):
    """Generate a Word document from parsed markdown blocks."""
    doc = Document()

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)
    font.color.rgb = BRAND_TEXT

    # Title page
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("\n\n\n").font.size = Pt(24)
    run = p.add_run(title)
    run.font.size = Pt(28)
    run.font.color.rgb = BRAND_PRIMARY
    run.bold = True

    if meta:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.add_run(f"\n{meta.get('type', '')} | v{meta.get('version', '1.0.0')}").font.size = Pt(14)
        p2.add_run(f"\n{meta.get('classification', 'INTERNAL')}").font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        p2.add_run(f"\n\n{date.today().isoformat()}").font.size = Pt(12)
        p2.add_run(f"\nLIA-Scan Platform").font.color.rgb = BRAND_SECONDARY

    doc.add_page_break()

    # Content
    for block in blocks:
        btype = block["type"]

        if btype == "h1":
            h = doc.add_heading(block["text"], level=1)
            for run in h.runs:
                run.font.color.rgb = BRAND_PRIMARY
        elif btype == "h2":
            h = doc.add_heading(block["text"], level=2)
            for run in h.runs:
                run.font.color.rgb = BRAND_SECONDARY
        elif btype == "h3":
            doc.add_heading(block["text"], level=3)
        elif btype == "h4":
            doc.add_heading(block["text"], level=4)
        elif btype == "paragraph":
            doc.add_paragraph(block["text"])
        elif btype == "bullet":
            doc.add_paragraph(block["text"], style="List Bullet")
        elif btype == "quote":
            p = doc.add_paragraph(block["text"])
            p.style = doc.styles.get("Quote", doc.styles["Normal"])
        elif btype == "code":
            p = doc.add_paragraph()
            run = p.add_run(block["content"])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x2E, 0x2E, 0x2E)
        elif btype == "table":
            rows = block["rows"]
            if rows:
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                for i, row in enumerate(rows):
                    for j, cell in enumerate(row):
                        table.cell(i, j).text = cell
                        if i == 0:
                            for run in table.cell(i, j).paragraphs[0].runs:
                                run.bold = True
        elif btype == "hr":
            doc.add_paragraph("_" * 60)

    # Footer info
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Generated by LIA-Scan Documentation Engine")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.save(output_path)
    print(f"Generated: {output_path}")
    return output_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        sys.exit(1)

    # Determine output path
    if len(sys.argv) >= 3 and not sys.argv[2].startswith("--"):
        output_path = sys.argv[2]
    else:
        output_path = os.path.join(
            "_alire/01_DOCUMENTATION/exports",
            Path(input_path).stem + ".docx"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Read markdown
    with open(input_path) as f:
        md_text = f.read()

    # Try to load metadata
    meta = None
    try:
        import json
        meta_file = Path(input_path).parent / f".{Path(input_path).stem}.doc-meta.json"
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
    except Exception:
        pass

    # Extract title from first heading
    title = Path(input_path).stem.replace("_", " ").title()
    for line in md_text.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    blocks = parse_markdown(md_text)
    generate_docx(blocks, title, output_path, meta)


if __name__ == "__main__":
    main()
