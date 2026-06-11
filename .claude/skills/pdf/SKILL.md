---
name: pdf
description: Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text and tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting or decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill.
---

# PDF Processing Guide v3.0

Essential PDF processing operations using Python libraries and command-line tools. For advanced features, JavaScript libraries, and detailed examples, see REFERENCE.md. For PDF form filling, read FORMS.md and follow its instructions.

## Architecture Multi-Agent

| Step | Role | Responsibility |
|------|------|----------------|
| 1. Input analysis | COLLECTOR | Read source PDFs, detect type (text/scanned/form), count pages |
| 2. Strategy selection | ANALYST | Choose tool chain (pypdf/pdfplumber/reportlab/qpdf/OCR) |
| 3. Processing | EXECUTOR | Execute extraction, merge, split, create, or transform |
| 4. Validation | ANALYST | Verify output (page count, text content, file integrity) |
| 5. Fix loop | EXECUTOR | Fix errors, retry with alternative tool (max 3 iterations) |
| 6. Traceability | LIBRARIAN | Log decisions, archive output, update action journal |

## Quality Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| PRE_CREATE | Before reportlab script | Verify no Unicode subscript/superscript chars, correct pagesize import |
| POST_MERGE | After merge operation | Verify page count = sum of input page counts |
| POST_EXTRACT | After text extraction | Verify extracted text is non-empty (if empty, suggest OCR path) |
| OUTPUT_CHECK | Before delivery | Verify output file exists, size > 0, is valid PDF (PdfReader succeeds) |

## Autonomy Levels

| Level | Description | When to use |
|-------|-------------|-------------|
| FULL | Autonomous: detect type, choose tool, process, validate, deliver | Standard merge/split/extract tasks |
| GUIDED | Execute with checkpoint: confirm tool choice before processing | Large PDFs (100+ pages), OCR, encryption |
| SUPERVISED | Propose plan, wait for approval | Form filling, watermarking branded docs |
| MANUAL | Provide instructions only | Debugging, training |

## Quick Start

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")

text = ""
for page in reader.pages:
    text += page.extract_text()
```

## Python Libraries

### pypdf - Basic Operations

#### Merge PDFs
```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as output:
    writer.write(output)
```

#### Split PDF
```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as output:
        writer.write(output)
```

#### Extract Metadata
```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"Title: {meta.title}, Author: {meta.author}")
```

#### Rotate Pages
```python
reader = PdfReader("input.pdf")
writer = PdfWriter()
page = reader.pages[0]
page.rotate(90)
writer.add_page(page)
with open("rotated.pdf", "wb") as output:
    writer.write(output)
```

### pdfplumber - Text and Table Extraction

#### Extract Text with Layout
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

#### Extract Tables
```python
with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f"Table {j+1} on page {i+1}:")
            for row in table:
                print(row)
```

#### Advanced Table Extraction (to Excel)
```python
import pandas as pd

with pdfplumber.open("document.pdf") as pdf:
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

### reportlab - Create PDFs

#### Basic PDF Creation
```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("hello.pdf", pagesize=letter)
width, height = letter
c.drawString(100, height - 100, "Hello World!")
c.line(100, height - 140, 400, height - 140)
c.save()
```

#### Multi-Page with Platypus
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

story.append(Paragraph("Report Title", styles['Title']))
story.append(Spacer(1, 12))
story.append(Paragraph("Body text content. " * 20, styles['Normal']))
story.append(PageBreak())
story.append(Paragraph("Page 2", styles['Heading1']))

doc.build(story)
```

#### Subscripts and Superscripts

**IMPORTANT**: Never use Unicode subscript/superscript characters in ReportLab PDFs. Built-in fonts render them as black boxes.

```python
# CORRECT: use XML markup tags in Paragraph objects
chemical = Paragraph("H<sub>2</sub>O", styles['Normal'])
squared = Paragraph("x<super>2</super>", styles['Normal'])
```

For canvas-drawn text, manually adjust font size and position.

## Command-Line Tools

### pdftotext (poppler-utils)
```bash
pdftotext input.pdf output.txt              # Extract text
pdftotext -layout input.pdf output.txt      # Preserve layout
pdftotext -f 1 -l 5 input.pdf output.txt   # Pages 1-5
```

### qpdf
```bash
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf     # Merge
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf               # Split
qpdf input.pdf output.pdf --rotate=+90:1                   # Rotate page 1
qpdf --password=mypassword --decrypt encrypted.pdf out.pdf  # Decrypt
```

### pdftk (if available)
```bash
pdftk file1.pdf file2.pdf cat output merged.pdf   # Merge
pdftk input.pdf burst                               # Split
pdftk input.pdf rotate 1east output rotated.pdf     # Rotate
```

## Common Tasks

### OCR Scanned PDFs
```python
import pytesseract
from pdf2image import convert_from_path

images = convert_from_path('scanned.pdf')
text = ""
for i, image in enumerate(images):
    text += f"Page {i+1}:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"
```

### Add Watermark
```python
from pypdf import PdfReader, PdfWriter

watermark = PdfReader("watermark.pdf").pages[0]
reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as output:
    writer.write(output)
```

### Extract Images
```bash
pdfimages -j input.pdf output_prefix
# Extracts as output_prefix-000.jpg, output_prefix-001.jpg, etc.
```

### Password Protection
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()
for page in reader.pages:
    writer.add_page(page)

writer.encrypt("userpassword", "ownerpassword")
with open("encrypted.pdf", "wb") as output:
    writer.write(output)
```

## Quick Reference

| Task | Best Tool | Command/Code |
|------|-----------|--------------|
| Merge PDFs | pypdf | `writer.add_page(page)` |
| Split PDFs | pypdf | One page per file |
| Extract text | pdfplumber | `page.extract_text()` |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Create PDFs | reportlab | Canvas or Platypus |
| Command line merge | qpdf | `qpdf --empty --pages ...` |
| OCR scanned PDFs | pytesseract | Convert to image first |
| Fill PDF forms | pdf-lib or pypdf | See FORMS.md |

---

## Adaptation and Replanification

- If text extraction returns empty on 2 consecutive attempts: switch to OCR pipeline (pdf2image + pytesseract)
- If pypdf fails on a corrupted PDF 2 times: try qpdf repair first (`qpdf --replace-input file.pdf`)
- If reportlab rendering is incorrect 2 times: invoke /replan to reassess approach (consider HTML-to-PDF via weasyprint)
- NEVER improvise a workaround without logging the decision
- If a dependency is missing (poppler-utils, tesseract, reportlab): report immediately, do not mock output

## Traceability

Every non-trivial PDF operation MUST be traced:

**Decision log** (for architectural choices):
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"pdf-proc","action":"CHOSE_PDFPLUMBER","reasoning":"table extraction needed, pypdf insufficient","alternatives_rejected":["pypdf: no table support","tabula: Java dependency"],"outcome":"success","confidence":"high","plan_ref":null}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

**Action journal** (for each step executed):
- Log: tool chosen, input file(s), output file, page count, operation type
- Format: append to decision_log.jsonl with action = PDF_CREATED / PDF_MERGED / PDF_EXTRACTED / PDF_SPLIT / PDF_OCR

## Next Steps

- For advanced pypdfium2 usage, see REFERENCE.md
- For JavaScript libraries (pdf-lib), see REFERENCE.md
- For PDF form filling, follow FORMS.md
- For troubleshooting guides, see REFERENCE.md

## Scoring Agentique

| Critere | Description | Points |
|---------|-------------|--------|
| C1 Autonomie | Skill executes end-to-end without unnecessary user prompts | /10 |
| C2 Qualite | Output is valid PDF, correct page count, text extractable | /10 |
| C3 Tracabilite | All decisions logged, action journal complete, plan updated | /10 |
| C4 Adaptation | Failures handled via tool switch or /replan, no silent errors | /10 |
| C5 Efficacite | Correct tool chosen first time, minimal iterations | /10 |
| **TOTAL** | | **/50** |
