# Legal Context -- Why this skill exists

## Audit findings 2026-05-05

LIA-SEC commercial closed-source product imports fingerprint patterns from third-party catalogs:

| LiaProbe subdir | Source license | Risk LIA-SEC commercial |
|-----------------|----------------|--------------------------|
| `patterns/web-signatures/` (~3500) | GPL v3 (snapshot) / proprietary (Aug 2023+) | HIGH copyleft + EU sui generis |
| `patterns/tcp-probes/` (~3000) | NPSL (GPL v2 + clauses) | CRITIQUE OEM $49,980 required |
| `patterns/banner-signatures/` (~700) | BSD 2-Clause | LOW with attribution notice |
| `patterns/service-detectors/` (~190) | MIT | LOW with attribution notice |

## Why GPL/NPSL fail for closed-source LIA-SEC

### GPL v3 catalog
- **Copyleft strong** : derivative work must be GPL v3 too
- LIA-SEC = closed-source commercial product => incompatible
- Sui generis EU 96/9/EC : substantial extraction protected even if patterns individually non-copyrightable

### NPSL catalog
- "Reading the data file makes you derivative work"
- Closed-source commercial = OEM license $49,980+ required
- GPL v2 base + active enforcement
- Debian deemed NPSL non-free (0.92), borderline (0.93)

### MIT / BSD-2 catalogs
- Permissive : commercial use OK
- Attribution required : must include copyright notice in distribution
- Solution : `THIRD_PARTY_NOTICES.md` at repo root

## EU sui generis Database Directive 96/9/EC

Even if individual regex patterns are NOT copyrightable (Feist doctrine + merger doctrine), the EU sui generis right protects against "extraction of substantial part" of databases where there has been "substantial investment in obtaining/verification/presentation".

- ~3500 curated patterns = substantial investment
- ~10000 fingerprints catalog = substantial investment
- Extraction 1000+ patterns into LIA-SEC = unauthorized extraction (independent of copyright license)
- LIA-SEC operating from France/EU = subject to this right

## Doctrine "facts vs creative expression" (US Feist + EU)

| Element | Copyrightable ? | Note |
|---------|----------------|------|
| Banner string raw "Apache/2.4.51" | NO (observable fact) | Feist applies |
| Simple regex `^Apache\/([\d.]+)` | DOUBTFUL (merger doctrine) | One way to express fact |
| Complex regex with named groups + lookaheads | YES thin copyright | Creative choices |
| Selection of 3500 patterns | YES (compilation copyright) | Curatorial judgment |
| Categorization, metadata | YES thin | Creative arrangement |

## Mitigation paths

### Path A : Strip third-party-specific fields (light defensive)

Drop fields that constitute compilation copyright while keeping regex (facts) :
- DROP `categories: [...]` (third-party catalog category IDs)
- DROP `notes: "..."` (third-party catalog descriptions verbatim)
- DROP `source.original_name` and `source.file` (catalog hints)
- KEEP regex (factual)

Coverage : strip compilation copyright, sui generis still applicable.

### Path B (this skill) : Independent re-observation

For each rule :
1. Visit vendor official website
2. Inspect public DOM/cookies/headers
3. Author NEW regex from observation (not copy)
4. Document audit trail (sha256 artifacts + source URL + date)
5. Marker `_lia_independent_authoring.third_party_catalog_references_consulted == "NONE"`

Coverage : defeats both copyright AND sui generis right (factual independent observation, not extraction).

### Path C : Drop subdir + use only safe sources

Move `patterns/web-signatures/` and `patterns/tcp-probes/` to gitignored todo/.
Keep only BSD + MIT + lia (custom) catalogs.
Loss : ~6500 fingerprints (massive coverage drop).

## Decision matrix

| Path | Effort | Legal coverage | Coverage retention |
|------|--------|----------------|---------------------|
| A (strip fields) | 5 min | partial (still sui generis risk) | 100% |
| **B (this skill)** | **3-6 months full** | **complete** | **100%** |
| C (drop) | 5 min | complete | ~15% |

Recommended : Path B for high-value patterns (top 100) + Path A for long-tail + Path C for defunct/niche.

## R13 internal rule vs legal license requirement

**R13** "No Open-Source Attribution in Code" = internal LIA-SEC convention to never reference third-party tool names in code/comments/filenames.

**MIT / BSD licenses** REQUIRE copyright notice in distribution.

**Conflict resolution** :
- R13 stays valid for code comments (no third-party tool name in source files)
- Create `THIRD_PARTY_NOTICES.md` at repo root with copyright notices for retained BSD/MIT-licensed catalogs (Path B doesn't need notices since rules become independent works, but original BSD/MIT-licensed files in repo do)
- This skill's output rules (`lia-fingerprint-v2-independent`) require ZERO attribution since they're independent works

## Reference cases

- *Feist Publications, Inc. v. Rural Telephone Service Co.* 499 U.S. 340 (1991) -- facts not copyrightable
- *Oracle v. Google* (US Supreme Court 2021) -- fair use of API declarations
- EU CJEU *Ryanair Ltd v. PR Aviation BV* (C-30/14, 2015) -- sui generis coexists with contractual terms
- EU Database Directive 96/9/EC implementation in France (CPI Art. L. 341-1)

## When to invoke this skill

- Audit legal demande (CISO, juriste, due-diligence acquéreur)
- Avant release commerciale closed-source comportant ces patterns
- Mise en demeure GPL ou litigation IP
- Projet enterprise high-stakes ou défense contractuelle nécessaire
