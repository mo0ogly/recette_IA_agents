#!/usr/bin/env python3
"""
LIA-SEC Librarian -- build alphabetical + category indexes.

Scans _alire/01_DOCUMENTATION/rules/01_Guides/{operators,functions,guides}/
and produces INDEX.md files with:
- Alphabetical list (with one-line description extracted from first H1 subtitle)
- Thematic grouping (hardcoded categories per item type)

Reads frontmatter YAML to get item_id, item_name, source info.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

ROOT = "_alire/01_DOCUMENTATION/rules/01_Guides"

# Curated short descriptions (used when the extracted H1 is not descriptive).
# These are DERIVED FROM THE SOURCE DOCX TITLES -- they are NOT a reformulation
# of the content, only a one-line summary for navigation.
DESCRIPTIONS: Dict[str, str] = {
    # Operators
    "contains": "substring / list membership check",
    "startswith_endswith": "prefix / suffix check",
    "not_startswith_not_endswith": "negative prefix / suffix",
    "re_regex": "regular expression match (partial)",
    "re_full": "full-string regex match (anchored start to end)",
    "re_ignorecase": "case-insensitive regex match",
    "len": "shorthand for length() (string length)",
    "length_equals": "exact string length equality",
    "length_greater_than_less_than": "length >, <, >=, <= comparisons",
    "eq_ne": "equality / inequality (case-sensitive)",
    "gt_lt_gte_lte": "numeric comparisons (>, <, >=, <=)",
    "between": "value ranges (inclusive) in where",
    "before_after_on": "temporal comparisons in where",
    "in": "value in list / set membership",
    "isempty_isnotempty": "emptiness / non-emptiness check",
    "any_all": "array quantifiers (exists-one / forall)",
    "ternary_if": "inline ternary expression and if() conditional",
    "base64_base64offset": "binary-aware decoding and byte-pattern checks",
    "combined_operators": "writing complex conditions with combined operators",

    # Functions
    "length": "string length as integer",
    "substring": "substring extraction",
    "contains_ignore_case": "case-insensitive contains",
    "extract_domain": "extract domain from DN / UPN",
    "case_insensitive_string_functions": "overview of case-insensitive string functions",
    "age_in_months": "months elapsed since a date",
    "days_since": "days elapsed since a date",
    "days_until": "days until a future date",
    "is_expired": "date is in the past",
    "is_within_days": "date is within N days of now",
    "has_flag": "bitwise flag check (generic)",
    "uac_has_flag": "UAC-specific flag decoder (22 flags)",
    "is_privileged_sid": "SID belongs to a privileged account",
    "has_cross_domain_sid": "SID from a different domain (sIDHistory)",
    "extract_rid": "extract RID integer from SID",
    "resolve_nested_groups": "recursive group membership resolution",
    "has_privilege_transitive": "transitive privilege detection",
    "group_privilege_depth": "privilege depth metric for a group",
    "coalesce": "first non-null / non-empty value",
    "ifnull": "two-argument coalesce alias",
    "if": "conditional branching expression",

    # Guides
    "engine_overview": "introduction to LiaScan and its engine",
    "key_schema_fields": "target, object_type, object_detection, output",
    "match_vs_where": "difference between match and where clauses",
    "classic_vs_extended_rules": "legacy classic rules vs structured extended rules",
    "practical_examples_match_where": "AD, Azure AD, AWS IAM, Google Workspace examples",
    "benchmark_classic_vs_extended": "detection times, memory, filtering benchmarks",
    "processing_pipeline": "unified CLI / GUI / API rule processing pipeline",
    "dynamic_variables": "placeholders in structured rules",
    "dynamic_variables_dates": "dynamic variables and date handling",
    "type_conversion": "int, windows_filetime, iso8601, list, hex, binary, null, json, base64",
    "supported_variable_formats": "complete list of supported variable formats",
    "exceptions_vs_where": "when to use exceptions vs where",
    "cheat_sheet_aws_azure": "AWS and Azure cheat sheet examples",
    "output_include": "friendly names and field projection",
    "output_computed": "computed fields with functions",
    "nested_functions_cross_references": "two-pass evaluation, recursive functions, cross-references",
    "operator_reference_table": "complete operator reference table",
    "rule_insertion_process": "rule insertion process for structured LiaScan rules",
    "performance_optimization": "rule tuning, operator costs, best practices",
    "benchmark_regex_vs_contains": "regex vs contains performance benchmarks",
    "authoring_guide_v36_updates": "engine v3.6 updates (operators, pitfalls, migration)",
    "date_time_functions_reference_fr": "chapitre 5 du Guide Fonctionnel (FR) -- date / time reference",
}

# Category mapping for operators.
OPERATOR_CATEGORIES: Dict[str, List[str]] = {
    "String matching": [
        "contains", "startswith_endswith", "not_startswith_not_endswith",
        "re_regex", "re_full", "re_ignorecase",
    ],
    "Length": [
        "len", "length_equals", "length_greater_than_less_than",
    ],
    "Comparison": [
        "eq_ne", "gt_lt_gte_lte", "between", "before_after_on",
    ],
    "Set / Membership": [
        "in", "isempty_isnotempty",
    ],
    "Array / Logic": [
        "any_all", "ternary_if",
    ],
    "Binary": [
        "base64_base64offset",
    ],
    "Complex": [
        "combined_operators",
    ],
}

FUNCTION_CATEGORIES: Dict[str, List[str]] = {
    "String": [
        "length", "substring", "contains_ignore_case", "extract_domain",
        "case_insensitive_string_functions",
    ],
    "Date / Time": [
        "age_in_months", "days_since", "days_until", "is_expired", "is_within_days",
    ],
    "UAC / Bitwise": [
        "has_flag", "uac_has_flag",
    ],
    "SID analysis": [
        "is_privileged_sid", "has_cross_domain_sid", "extract_rid",
    ],
    "AD graph traversal": [
        "resolve_nested_groups", "has_privilege_transitive", "group_privilege_depth",
    ],
    "Null handling": [
        "coalesce", "ifnull",
    ],
    "Control flow": [
        "if",
    ],
}

GUIDE_CATEGORIES: Dict[str, List[str]] = {
    "Introduction & architecture": [
        "engine_overview", "key_schema_fields", "classic_vs_extended_rules",
        "processing_pipeline",
    ],
    "Match / Where / Exceptions": [
        "match_vs_where", "practical_examples_match_where",
        "exceptions_vs_where", "cheat_sheet_aws_azure",
    ],
    "Output / Projection": [
        "output_include", "output_computed", "nested_functions_cross_references",
    ],
    "Dynamic variables": [
        "dynamic_variables", "dynamic_variables_dates",
        "supported_variable_formats",
    ],
    "Data handling": [
        "type_conversion",
    ],
    "Reference tables": [
        "operator_reference_table", "rule_insertion_process",
    ],
    "Benchmarks & Performance": [
        "benchmark_classic_vs_extended", "performance_optimization",
        "benchmark_regex_vs_contains",
    ],
    "Engine updates": [
        "authoring_guide_v36_updates", "date_time_functions_reference_fr",
    ],
}


@dataclass
class DocInfo:
    basename: str        # "contains"
    filename: str        # "contains.md"
    title: str           # first H1 text (from the body, not frontmatter)
    source_paragraphs: str
    item_id: str


def parse_doc(path: str) -> DocInfo:
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()

    # Parse frontmatter.
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    fm_raw = m.group(1) if m else ""
    body = m.group(2) if m else content

    def fget(key: str) -> str:
        mm = re.search(rf'^{key}:\s*"?([^"\n]+)"?\s*$', fm_raw, re.MULTILINE)
        return (mm.group(1).strip() if mm else "").strip('"')

    item_id = fget("item_id")
    source_paragraphs = fget("source_paragraphs")

    # First H1 in body.
    title = ""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            # Strip markdown emphasis/bold.
            title = re.sub(r"\*+", "", title)
            break

    filename = os.path.basename(path)
    basename = filename[:-3] if filename.endswith(".md") else filename
    return DocInfo(
        basename=basename,
        filename=filename,
        title=title or basename.replace("_", " "),
        source_paragraphs=source_paragraphs,
        item_id=item_id,
    )


def scan_dir(dirpath: str) -> Dict[str, DocInfo]:
    result: Dict[str, DocInfo] = {}
    if not os.path.isdir(dirpath):
        return result
    for name in sorted(os.listdir(dirpath)):
        if not name.endswith(".md"):
            continue
        if name.upper() in {"README.MD", "INDEX.MD"}:
            continue
        info = parse_doc(os.path.join(dirpath, name))
        result[info.basename] = info
    return result


def _desc(basename: str, fallback: str) -> str:
    return DESCRIPTIONS.get(basename, fallback)


def render_alphabetical(docs: Dict[str, DocInfo], kind: str) -> str:
    lines: List[str] = [f"## Alphabetical", ""]
    for key in sorted(docs.keys()):
        d = docs[key]
        lines.append(f"- [{d.basename}]({d.filename}) -- {_desc(d.basename, d.title)}")
    lines.append("")
    return "\n".join(lines)


def render_category(docs: Dict[str, DocInfo], categories: Dict[str, List[str]]) -> str:
    lines: List[str] = ["## By category", ""]
    seen: set = set()
    for cat, items in categories.items():
        lines.append(f"### {cat}")
        lines.append("")
        for key in items:
            if key in docs:
                d = docs[key]
                lines.append(f"- [{d.basename}]({d.filename}) -- {_desc(d.basename, d.title)}")
                seen.add(key)
            else:
                lines.append(f"- **{key}** *(MISSING from docs)*")
        lines.append("")
    # Orphans not listed in categories.
    orphans = [k for k in sorted(docs.keys()) if k not in seen]
    if orphans:
        lines.append("### Uncategorized")
        lines.append("")
        for key in orphans:
            d = docs[key]
            lines.append(f"- [{d.basename}]({d.filename}) -- {_desc(d.basename, d.title)}")
        lines.append("")
    return "\n".join(lines)


def build_index(dirname: str, kind_label: str, categories: Dict[str, List[str]]) -> None:
    dirpath = os.path.join(ROOT, dirname)
    docs = scan_dir(dirpath)
    out_lines: List[str] = [
        f"# LIA-Scan {kind_label} -- Index",
        "",
        f"Total: **{len(docs)}** {kind_label.lower()} ingested verbatim from docx sources.",
        "",
        "See `../README.md` for the global landing page, and "
        "`_alire/tracking/LIBRARIAN_QUEUE_OPERATORS_FUNCTIONS_2026-04-11.md` "
        "for the full ingestion queue.",
        "",
        render_category(docs, categories),
        render_alphabetical(docs, kind_label.lower()),
    ]
    out_path = os.path.join(dirpath, "INDEX.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines))
    print(f"wrote {out_path} ({len(docs)} items)")


def main() -> int:
    build_index("operators", "Operators", OPERATOR_CATEGORIES)
    build_index("functions", "Functions", FUNCTION_CATEGORIES)
    build_index("guides", "Guides", GUIDE_CATEGORIES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
