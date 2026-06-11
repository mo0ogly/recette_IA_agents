---
name: xlsx
description: "Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file; create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger when the user references a spreadsheet file by name or path, and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files into proper spreadsheets."
---

# XLSX Skill v3.0 -- Multi-Agent Architecture

Skill de creation, lecture, edition et analyse de fichiers Excel (.xlsx, .xlsm, .csv, .tsv).
Orchestre 5 roles agents pour livrer des classeurs professionnels avec formules valides et formatage coherent.

---

## Architecture Multi-Agent

| Phase | Role | Responsabilite |
|-------|------|----------------|
| 1. Analyse brief | ANALYST | Comprendre le besoin, identifier type (financier, data, reporting), contraintes |
| 2. Collecte donnees | COLLECTOR | Extraire donnees sources (fichiers, API, pandas read), valider completude |
| 3. Planification structure | PLANNER | Definir sheets, colonnes, formules, formatage, color coding |
| 4. Generation classeur | EXECUTOR | Creer/editer le .xlsx (openpyxl ou pandas), recalculer formules |
| 5. Verification + archivage | LIBRARIAN | Recalc via scripts/recalc.py, verifier zero erreurs, tracer dans decision_log |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|--------------|--------|
| `POST_GENERATION` | Apres ecriture du .xlsx | `python scripts/recalc.py output.xlsx` -- zero tolerance sur erreurs formule |
| `FORMULA_AUDIT` | Apres recalc | Verifier que AUCUNE valeur n'est hardcodee quand une formule est possible |
| `FORMAT_VERIFY` | Avant livraison | Controle color coding (bleu=input, noir=formule), largeur colonnes, alignement |
| `REGRESSION_CHECK` | Apres chaque fix | Re-recalc + comparer error_summary avec run precedent |

---

## Autonomy Levels

| Niveau | Condition | Comportement |
|--------|-----------|-------------|
| FULL | Donnees claires, format standard, pas de formules complexes | Execution complete sans interruption |
| GUIDED | Modele financier, hypotheses a valider, formules cross-sheet | Proposer structure, attendre validation |
| SUPERVISED | Template existant a modifier, formules imbriquees | Checkpoint apres Phase 3 (plan structure) |
| BLOCKED | Donnees manquantes, format source illisible, brief incomplet | Demander les elements manquants |

---

## Requirements for Outputs

### All Excel files

#### Professional Font
- Use a consistent, professional font (e.g., Arial, Times New Roman) for all deliverables unless otherwise instructed by the user

#### Zero Formula Errors
- Every Excel model MUST be delivered with ZERO formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?)

#### Preserve Existing Templates (when updating templates)
- Study and EXACTLY match existing format, style, and conventions when modifying files
- Never impose standardized formatting on files with established patterns
- Existing template conventions ALWAYS override these guidelines

### Financial models

#### Color Coding Standards
Unless otherwise stated by the user or existing template

- **Blue text (RGB: 0,0,255)**: Hardcoded inputs, and numbers users will change for scenarios
- **Black text (RGB: 0,0,0)**: ALL formulas and calculations
- **Green text (RGB: 0,128,0)**: Links pulling from other worksheets within same workbook
- **Red text (RGB: 255,0,0)**: External links to other files
- **Yellow background (RGB: 255,255,0)**: Key assumptions needing attention or cells that need to be updated

#### Number Formatting Standards

- **Years**: Format as text strings (e.g., "2024" not "2,024")
- **Currency**: Use $#,##0 format; ALWAYS specify units in headers ("Revenue ($mm)")
- **Zeros**: Use number formatting to make all zeros "-", including percentages (e.g., "$#,##0;($#,##0);-")
- **Percentages**: Default to 0.0% format (one decimal)
- **Multiples**: Format as 0.0x for valuation multiples (EV/EBITDA, P/E)
- **Negative numbers**: Use parentheses (123) not minus -123

#### Formula Construction Rules

- Place ALL assumptions (growth rates, margins, multiples, etc.) in separate assumption cells
- Use cell references instead of hardcoded values in formulas
- Example: Use =B5*(1+$B$6) instead of =B5*1.05

#### Formula Error Prevention
- Verify all cell references are correct
- Check for off-by-one errors in ranges
- Ensure consistent formulas across all projection periods
- Test with edge cases (zero values, negative numbers)
- Verify no unintended circular references

#### Documentation Requirements for Hardcodes
- Comment or in cells beside (if end of table). Format: "Source: [System/Document], [Date], [Specific Reference], [URL if applicable]"

---

## CRITICAL: Use Formulas, Not Hardcoded Values

**Always use Excel formulas instead of calculating values in Python and hardcoding them.** This ensures the spreadsheet remains dynamic and updateable.

### WRONG - Hardcoding Calculated Values
```python
# Bad: Calculating in Python and hardcoding result
total = df['Sales'].sum()
sheet['B10'] = total  # Hardcodes 5000

# Bad: Computing growth rate in Python
growth = (df.iloc[-1]['Revenue'] - df.iloc[0]['Revenue']) / df.iloc[0]['Revenue']
sheet['C5'] = growth  # Hardcodes 0.15
```

### CORRECT - Using Excel Formulas
```python
# Good: Let Excel calculate the sum
sheet['B10'] = '=SUM(B2:B9)'

# Good: Growth rate as Excel formula
sheet['C5'] = '=(C4-C2)/C2'

# Good: Average using Excel function
sheet['D20'] = '=AVERAGE(D2:D19)'
```

---

## Reading and Analyzing Data

### Data analysis with pandas
```python
import pandas as pd

# Read Excel
df = pd.read_excel('file.xlsx')  # Default: first sheet
all_sheets = pd.read_excel('file.xlsx', sheet_name=None)  # All sheets as dict

# Analyze
df.head()      # Preview data
df.info()      # Column info
df.describe()  # Statistics

# Write Excel
df.to_excel('output.xlsx', index=False)
```

---

## Common Workflow

1. **Choose tool**: pandas for data, openpyxl for formulas/formatting
2. **Create/Load**: Create new workbook or load existing file
3. **Modify**: Add/edit data, formulas, and formatting
4. **Save**: Write to file
5. **Recalculate formulas (MANDATORY IF USING FORMULAS)**:
   ```bash
   python scripts/recalc.py output.xlsx
   ```
6. **Verify and fix any errors**:
   - The script returns JSON with error details
   - If `status` is `errors_found`, check `error_summary` for specific error types and locations
   - Fix the identified errors and recalculate again
   - Common errors: `#REF!` (invalid references), `#DIV/0!` (division by zero), `#VALUE!` (wrong type), `#NAME?` (unrecognized name)

### Creating new Excel files

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
sheet = wb.active

# Add data
sheet['A1'] = 'Hello'
sheet['B1'] = 'World'
sheet.append(['Row', 'of', 'data'])

# Add formula
sheet['B2'] = '=SUM(A1:A10)'

# Formatting
sheet['A1'].font = Font(bold=True, color='FF0000')
sheet['A1'].fill = PatternFill('solid', start_color='FFFF00')
sheet['A1'].alignment = Alignment(horizontal='center')

# Column width
sheet.column_dimensions['A'].width = 20

wb.save('output.xlsx')
```

### Editing existing Excel files

```python
from openpyxl import load_workbook

wb = load_workbook('existing.xlsx')
sheet = wb.active  # or wb['SheetName'] for specific sheet

# Working with multiple sheets
for sheet_name in wb.sheetnames:
    sheet = wb[sheet_name]

# Modify cells
sheet['A1'] = 'New Value'
sheet.insert_rows(2)
sheet.delete_cols(3)

# Add new sheet
new_sheet = wb.create_sheet('NewSheet')
new_sheet['A1'] = 'Data'

wb.save('modified.xlsx')
```

---

## Recalculating Formulas

Excel files created or modified by openpyxl contain formulas as strings but not calculated values. Use `scripts/recalc.py`:

```bash
python scripts/recalc.py <excel_file> [timeout_seconds]
```

The script:
- Automatically sets up LibreOffice macro on first run
- Recalculates all formulas in all sheets
- Scans ALL cells for Excel errors
- Returns JSON with detailed error locations and counts

### Interpreting recalc.py Output
```json
{
  "status": "success",
  "total_errors": 0,
  "total_formulas": 42,
  "error_summary": {}
}
```

If `status` is `errors_found`, the `error_summary` dict contains error types with counts and locations.

---

## Formula Verification Checklist

### Essential Verification
- [ ] **Test 2-3 sample references**: Verify they pull correct values before building full model
- [ ] **Column mapping**: Confirm Excel columns match (e.g., column 64 = BL, not BK)
- [ ] **Row offset**: Remember Excel rows are 1-indexed (DataFrame row 5 = Excel row 6)

### Common Pitfalls
- [ ] **NaN handling**: Check for null values with `pd.notna()`
- [ ] **Far-right columns**: FY data often in columns 50+
- [ ] **Multiple matches**: Search all occurrences, not just first
- [ ] **Division by zero**: Check denominators before using `/` in formulas
- [ ] **Wrong references**: Verify all cell references point to intended cells
- [ ] **Cross-sheet references**: Use correct format (Sheet1!A1) for linking sheets

### Formula Testing Strategy
- [ ] **Start small**: Test formulas on 2-3 cells before applying broadly
- [ ] **Verify dependencies**: Check all cells referenced in formulas exist
- [ ] **Test edge cases**: Include zero, negative, and very large values

---

## Best Practices

### Library Selection
- **pandas**: Best for data analysis, bulk operations, and simple data export
- **openpyxl**: Best for complex formatting, formulas, and Excel-specific features

### Working with openpyxl
- Cell indices are 1-based (row=1, column=1 refers to cell A1)
- Use `data_only=True` to read calculated values: `load_workbook('file.xlsx', data_only=True)`
- **Warning**: If opened with `data_only=True` and saved, formulas are replaced with values and permanently lost
- For large files: Use `read_only=True` for reading or `write_only=True` for writing
- Formulas are preserved but not evaluated -- use scripts/recalc.py to update values

### Working with pandas
- Specify data types to avoid inference issues: `pd.read_excel('file.xlsx', dtype={'id': str})`
- For large files, read specific columns: `pd.read_excel('file.xlsx', usecols=['A', 'C', 'E'])`
- Handle dates properly: `pd.read_excel('file.xlsx', parse_dates=['date_column'])`

### Code Style
- Write minimal, concise Python code without unnecessary comments
- Avoid verbose variable names and redundant operations
- Add comments to cells with complex formulas or important assumptions
- Document data sources for hardcoded values

---

## Adaptation et Replanification

- **2 echecs consecutifs sur la meme etape** (ex: recalc echoue 2 fois, formules #REF! persistent apres 2 corrections) -> invoquer /replan
- **JAMAIS improviser** : si openpyxl ne supporte pas une feature, basculer sur pandas (et inversement), mais toujours via le plan formel
- **Escalade** : si les donnees source sont corrompues ou le format illisible, BLOQUER et demander clarification (autonomy level BLOCKED)
- **Changement de strategie** : tracer dans decision_log.jsonl avec `action: REPLAN_XLSX` et `reasoning`

---

## Tracabilite

### decision_log.jsonl

Chaque decision non-triviale (choix openpyxl vs pandas, restructuration sheet, formule complexe) :

```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"xlsx-gen","action":"CHOSE_OPENPYXL","reasoning":"Formules cross-sheet necessaires, pandas insuffisant","alternatives_rejected":["pandas - pas de support formules natives"],"outcome":"workbook cree avec 3 sheets liees","confidence":"high","plan_ref":null}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### action_journal

Tracer les etapes cles dans le plan persistant ou le RETEX :
- Nombre de sheets creees
- Nombre de formules inserees
- Cycles recalc (combien de passes avant zero erreurs)
- Issues trouvees et corrigees

---

## Scoring Agentique

| Critere | Description | Points |
|---------|-------------|--------|
| C1 Autonomie | Execution complete sans interruption inutile, choix outil adapte (pandas vs openpyxl) | /10 |
| C2 Qualite | Zero erreur formule (#REF!, #DIV/0!), color coding correct, formatage pro | /10 |
| C3 Tracabilite | decision_log.jsonl + action_journal remplis, RETEX si cycle long | /10 |
| C4 Adaptation | Replanification formelle apres echec, pas d'improvisation sur formules | /10 |
| C5 Efficacite | Nombre minimal de cycles recalc, pas de refonte structure evitable | /10 |
| **TOTAL** | | **/50** |
