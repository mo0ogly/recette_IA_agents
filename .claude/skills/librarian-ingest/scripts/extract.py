#!/usr/bin/env python3
"""
LIA-SEC Librarian -- verbatim docx -> markdown extractor.

Rule #0: zero reformulation, zero reduction, zero correction.
The text in the docx must survive the extraction byte-for-byte (modulo
the mandatory format translation: docx xml -> markdown).

Usage:
    librarian_extract.py --docx PATH --start N --end M --out OUT.md \
        [--item-id ID] [--item-type operator|function|guide] [--item-name NAME] \
        [--wave W1] [--dry-run]

If --start and --end are omitted, the entire document is extracted.
If --dry-run is set, output is written to stdout instead of OUT.md.

The script iterates over the docx body in XML order so that paragraphs
and tables appear in their original sequence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

# ---------------------------------------------------------------------------
# Heading / style detection
# ---------------------------------------------------------------------------

HEADING_LEVELS = {
    f"Heading {i}": i for i in range(1, 10)
}
# "Title" and "Subtitle" map to H1 / H2 implicitly.
TITLE_STYLE_TO_LEVEL = {"Title": 1, "Subtitle": 2}

# Styles explicitly marking code content.
CODE_STYLE_NAMES = {"Code", "HTML Preformatted", "Preformatted Text", "Source Code"}

# Monospace font families used in LIA-SEC docx for code samples.
MONOSPACE_FONTS = {
    "consolas", "courier", "courier new", "menlo", "fira code", "fira mono",
    "jetbrains mono", "monospace", "source code pro", "inconsolata",
    "liberation mono", "lucida console",
}


def iter_body_items(doc: DocxDocument) -> Iterable[object]:
    """Yield paragraphs and tables in document body order.

    python-docx exposes paragraphs and tables as separate sequences; to
    preserve their original order we walk the underlying XML body.
    """
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            yield DocxParagraph(child, doc)
        elif tag == qn("w:tbl"):
            yield DocxTable(child, doc)
        # Section properties and other XML elements are skipped silently.


# ---------------------------------------------------------------------------
# Paragraph classification
# ---------------------------------------------------------------------------

@dataclass
class Classified:
    kind: str   # heading / code / list-bullet / list-number / normal / empty
    level: int  # heading level (0 if not heading)
    text: str   # inline markdown text (bold/italic inlined)


def _run_is_monospace(run) -> bool:
    font_name = (run.font.name or "").strip().lower()
    if font_name in MONOSPACE_FONTS:
        return True
    rpr = run._element.find(qn("w:rPr"))
    if rpr is None:
        return False
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        return False
    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
        val = rfonts.get(qn(f"w:{attr}"))
        if val and val.strip().lower() in MONOSPACE_FONTS:
            return True
    return False


def _is_code_paragraph(p: DocxParagraph) -> bool:
    """Paragraph is code if its style is a known code style, OR if ALL
    non-empty runs use a monospace font."""
    style_name = (p.style.name or "").strip()
    if style_name in CODE_STYLE_NAMES:
        return True
    runs = [r for r in p.runs if (r.text or "")]
    if not runs:
        return False
    return all(_run_is_monospace(r) for r in runs)


def _list_kind(p: DocxParagraph) -> Optional[str]:
    """Return 'bullet' / 'number' if the paragraph is in a list, else None."""
    style_name = (p.style.name or "").strip()
    if style_name.startswith("List Bullet"):
        return "bullet"
    if style_name.startswith("List Number"):
        return "number"
    if style_name.startswith("List Paragraph"):
        # Ambiguous; inspect numbering properties.
        pPr = p._element.find(qn("w:pPr"))
        if pPr is not None:
            numPr = pPr.find(qn("w:numPr"))
            if numPr is not None:
                # We cannot cheaply distinguish bullet vs numbered without
                # reading the numbering definitions, so default to bullet.
                return "bullet"
    return None


def _runs_to_markdown(p: DocxParagraph) -> str:
    """Inline-format a paragraph's runs preserving bold/italic markers.

    Text is NEVER rewritten; only the surrounding markers change.
    """
    pieces: List[str] = []
    for run in p.runs:
        text = run.text or ""
        if not text:
            continue
        bold = bool(run.bold)
        italic = bool(run.italic)
        if bold and italic:
            pieces.append(f"***{text}***")
        elif bold:
            pieces.append(f"**{text}**")
        elif italic:
            pieces.append(f"*{text}*")
        else:
            pieces.append(text)
    if pieces:
        return "".join(pieces)
    # Fallback: some paragraphs expose text only via p.text (hyperlinks, etc.).
    return p.text or ""


def classify(p: DocxParagraph) -> Classified:
    style_name = (p.style.name or "").strip()
    if style_name in HEADING_LEVELS:
        return Classified("heading", HEADING_LEVELS[style_name], _runs_to_markdown(p))
    if style_name in TITLE_STYLE_TO_LEVEL:
        return Classified("heading", TITLE_STYLE_TO_LEVEL[style_name], _runs_to_markdown(p))
    if _is_code_paragraph(p):
        # Preserve the raw text for code (do not insert bold/italic markdown).
        return Classified("code", 0, p.text or "")
    list_kind = _list_kind(p)
    if list_kind == "bullet":
        return Classified("list-bullet", 0, _runs_to_markdown(p))
    if list_kind == "number":
        return Classified("list-number", 0, _runs_to_markdown(p))
    text = _runs_to_markdown(p)
    if not text.strip():
        return Classified("empty", 0, "")
    return Classified("normal", 0, text)


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def table_to_markdown(table: DocxTable) -> str:
    """Render a docx table to a markdown pipe table.

    Every cell is extracted verbatim (no reformulation). Newlines inside a
    cell are replaced with `<br>` so the markdown table stays on one row.
    """
    rows = table.rows
    if not rows:
        return ""
    out: List[str] = []
    def cell_text(cell) -> str:
        # Join all paragraphs inside the cell with <br> to preserve multi-line content.
        parts = []
        for para in cell.paragraphs:
            txt = _runs_to_markdown(para)
            parts.append(txt)
        # Escape pipe characters to keep table integrity.
        joined = "<br>".join(parts)
        return joined.replace("|", "\\|").replace("\n", "<br>")

    header_cells = [cell_text(c) for c in rows[0].cells]
    out.append("| " + " | ".join(header_cells) + " |")
    out.append("| " + " | ".join("---" for _ in header_cells) + " |")
    for row in rows[1:]:
        cells = [cell_text(c) for c in row.cells]
        # Some tables have inconsistent column counts -- pad to match header.
        while len(cells) < len(header_cells):
            cells.append("")
        out.append("| " + " | ".join(cells[: len(header_cells)]) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

@dataclass
class ExtractOptions:
    docx_path: str
    start: Optional[int]
    end: Optional[int]
    out_path: Optional[str]
    item_id: str
    item_type: str
    item_name: str
    wave: str
    dry_run: bool


def build_frontmatter(opts: ExtractOptions, source_name: str) -> str:
    today = dt.date.today().isoformat()
    range_str = "ALL" if opts.start is None and opts.end is None else f"{opts.start}-{opts.end}"
    lines = [
        "---",
        f'source_docx: "{source_name}"',
        f'source_paragraphs: "{range_str}"',
        f'extracted_at: "{today}"',
        'extractor: "scripts/librarian_extract.py v1"',
        'status: "DRAFT"',
        f'item_type: "{opts.item_type}"',
        f'item_name: "{opts.item_name}"',
        f'item_id: "{opts.item_id}"',
        f'wave: "{opts.wave}"',
        'verbatim: true',
        "---",
        "",
    ]
    return "\n".join(lines)


def extract(opts: ExtractOptions) -> str:
    doc = Document(opts.docx_path)
    source_name = opts.docx_path.split("/")[-1]

    # Build a linear list of (index_in_paragraphs, body_item).
    # The start/end filter applies only to paragraphs; tables between selected
    # paragraphs are kept.
    paragraphs_seen = 0
    buffered: List[object] = []
    selecting = opts.start is None  # if no bounds, select from start
    for item in iter_body_items(doc):
        if isinstance(item, DocxParagraph):
            idx = paragraphs_seen
            paragraphs_seen += 1
            if opts.start is not None and idx == opts.start:
                selecting = True
            if selecting:
                buffered.append(item)
            if opts.end is not None and idx >= opts.end:
                selecting = False
        else:
            # Table: include only if currently selecting.
            if selecting:
                buffered.append(item)

    # Render buffered items.
    out_chunks: List[str] = [build_frontmatter(opts, source_name)]

    code_accum: List[str] = []
    list_accum_kind: Optional[str] = None
    list_counter = 0

    def flush_code():
        nonlocal code_accum
        if code_accum:
            # Collapse leading / trailing empty lines but keep content verbatim.
            block = "\n".join(code_accum)
            out_chunks.append("```")
            out_chunks.append(block)
            out_chunks.append("```")
            out_chunks.append("")
            code_accum = []

    def flush_list():
        nonlocal list_accum_kind, list_counter
        if list_accum_kind is not None:
            out_chunks.append("")
            list_accum_kind = None
            list_counter = 0

    for item in buffered:
        if isinstance(item, DocxTable):
            flush_code()
            flush_list()
            out_chunks.append(table_to_markdown(item))
            out_chunks.append("")
            continue

        c = classify(item)

        if c.kind == "code":
            flush_list()
            code_accum.append(c.text)
            continue
        # Any non-code item flushes a pending code block.
        flush_code()

        if c.kind == "heading":
            flush_list()
            hashes = "#" * max(1, min(c.level, 6))
            text = c.text.strip()
            out_chunks.append(f"{hashes} {text}")
            out_chunks.append("")
            continue

        if c.kind == "list-bullet":
            if list_accum_kind != "bullet":
                flush_list()
                list_accum_kind = "bullet"
            out_chunks.append(f"- {c.text}")
            continue

        if c.kind == "list-number":
            if list_accum_kind != "number":
                flush_list()
                list_accum_kind = "number"
                list_counter = 0
            list_counter += 1
            # Avoid double numbering when Word's autonumber has already been
            # materialized into the paragraph text (e.g. "1. Item one").
            stripped = c.text.lstrip()
            import re as _re
            if _re.match(r"^\d+[.)]\s", stripped):
                out_chunks.append(f"{stripped}")
            else:
                out_chunks.append(f"{list_counter}. {c.text}")
            continue

        if c.kind == "normal":
            flush_list()
            out_chunks.append(c.text)
            out_chunks.append("")
            continue

        # empty: preserve as blank line.
        flush_list()
        out_chunks.append("")

    flush_code()
    flush_list()

    # Collapse runs of >=3 blank lines to 2 to keep markdown tidy without
    # losing content.
    raw = "\n".join(out_chunks)
    while "\n\n\n\n" in raw:
        raw = raw.replace("\n\n\n\n", "\n\n\n")
    return raw


def parse_args(argv: List[str]) -> ExtractOptions:
    ap = argparse.ArgumentParser(description="Verbatim docx -> markdown extractor")
    ap.add_argument("--docx", required=True, help="Path to source docx")
    ap.add_argument("--start", type=int, default=None, help="Start paragraph index (inclusive)")
    ap.add_argument("--end", type=int, default=None, help="End paragraph index (inclusive)")
    ap.add_argument("--out", default=None, help="Output .md path")
    ap.add_argument("--item-id", default="UNKNOWN", help="Queue item id (e.g. OP-CONTAINS)")
    ap.add_argument("--item-type", default="guide", choices=["operator", "function", "guide"])
    ap.add_argument("--item-name", default="unknown", help="Human-readable item name")
    ap.add_argument("--wave", default="W0", help="Wave label")
    ap.add_argument("--dry-run", action="store_true", help="Print to stdout, do not write file")
    ns = ap.parse_args(argv)
    return ExtractOptions(
        docx_path=ns.docx,
        start=ns.start,
        end=ns.end,
        out_path=ns.out,
        item_id=ns.item_id,
        item_type=ns.item_type,
        item_name=ns.item_name,
        wave=ns.wave,
        dry_run=ns.dry_run,
    )


def main(argv: List[str]) -> int:
    opts = parse_args(argv)
    md = extract(opts)
    if opts.dry_run or not opts.out_path:
        sys.stdout.write(md)
        sys.stdout.write("\n")
        return 0
    with open(opts.out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
