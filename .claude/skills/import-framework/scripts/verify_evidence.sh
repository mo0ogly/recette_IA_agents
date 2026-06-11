#!/usr/bin/env bash
# verify_evidence.sh -- forcing control for /import-framework evidence gates.
#
# The agent CANNOT self-assert "done". This script computes every gate boolean
# from the live DB + the committed files, writes the result to
# sources/EVIDENCE.json, and exits non-zero unless EVERY boolean is true.
# evidence_verified is flipped to true ONLY when reality satisfies all gates.
#
# Why this exists: incident 2026-05-23 (user re-insisted multiple times) --
# PT shipped questions as a JSON object (unanswerable survey, total_controls=0),
# and DK/HR/RO shipped a manifest sha256 with NO committed raw source file
# (not replay-verifiable). Both classes of defect are now machine-blocked.
#
# Usage:
#   verify_evidence.sh <CODE>            # verify one framework, write EVIDENCE.json
#   verify_evidence.sh --all             # verify every import-frameworks/<CODE>
# Exit: 0 = all gates pass | 1 = at least one gate failed | 2 = usage/env error
#
# R5/R8/R10/R12/R18 compliant. DATABASE_URL read live from systemd, never cached.

set -uo pipefail

ROOT="/opt/lia-sec/dev"
TRACK_BASE="$ROOT/_alire/tracking/import-frameworks"

resolve_dburl() {
  systemctl cat lia-backend 2>/dev/null | awk -F'Environment=DATABASE_URL=' 'NF>1{print $2}'
}

usage() { echo "usage: verify_evidence.sh <CODE> | --all" >&2; exit 2; }
[ $# -ge 1 ] || usage

DBURL="$(resolve_dburl)"
[ -n "$DBURL" ] || { echo "ERROR: cannot resolve DATABASE_URL from systemd" >&2; exit 2; }

# verify_one CODE -> echoes a one-line status, returns 0 if all gates pass.
verify_one() {
  local CODE="$1"
  local dir="$TRACK_BASE/$CODE"
  local srcdir="$dir/sources"
  local fail=0
  local reasons=()

  # --- Gate 1: 4 mandatory tracking files present ---
  local tracking_ok=true
  for f in PLAN.md PROOF_OF_RESEARCH.md ARTICLES_VERBATIM.md INVENTORY.md; do
    [ -f "$dir/$f" ] || { tracking_ok=false; reasons+=("missing tracking $f"); }
  done
  [ "$tracking_ok" = true ] || fail=1

  # --- Gate 2: framework active in DB ---
  local active parts sumarr badrows maps
  active=$(psql "$DBURL" -tA -c "SELECT is_active FROM compliance_frameworks WHERE code='$CODE';" 2>/dev/null)
  parts=$(psql "$DBURL" -tA -c "SELECT COUNT(*) FROM framework_surveys fs JOIN compliance_frameworks cf ON fs.framework_id=cf.id WHERE cf.code='$CODE';" 2>/dev/null)
  sumarr=$(psql "$DBURL" -tA -c "SELECT COALESCE(SUM(jsonb_array_length(CASE WHEN jsonb_typeof(questions)='array' THEN questions ELSE '[]'::jsonb END)),0) FROM framework_surveys fs JOIN compliance_frameworks cf ON fs.framework_id=cf.id WHERE cf.code='$CODE';" 2>/dev/null)
  badrows=$(psql "$DBURL" -tA -c "SELECT COUNT(*) FROM framework_surveys fs JOIN compliance_frameworks cf ON fs.framework_id=cf.id WHERE cf.code='$CODE' AND jsonb_typeof(questions)<>'array';" 2>/dev/null)
  maps=$(psql "$DBURL" -tA -c "SELECT COUNT(*) FROM smsi_framework_mappings WHERE source_framework='$CODE';" 2>/dev/null)

  local active_ok=false; [ "$active" = "t" ] && active_ok=true || { fail=1; reasons+=("framework not active"); }
  local parts_ok=false;  [ "${parts:-0}" -gt 0 ] 2>/dev/null && parts_ok=true || { fail=1; reasons+=("zero survey parts"); }

  # --- Gate 3: questions ARRAY gate (anti-PT) ---
  local array_ok=false
  if [ "${badrows:-1}" = "0" ] && [ "${sumarr:-0}" -gt 0 ] 2>/dev/null; then array_ok=true; else fail=1; reasons+=("non-array questions rows=$badrows arr_q=$sumarr"); fi

  # --- Gate 4: source evidence replay-verifiable ---
  # Every manifest sources[] sha256 must map to a committed file whose sha256 matches.
  local source_ok=true
  local manifest="$srcdir/manifest.json"
  if [ ! -f "$manifest" ]; then
    source_ok=false; fail=1; reasons+=("no manifest.json")
  else
    # extract (sha256, filename) pairs; tolerate note files (SOURCE_NOTE.md) for drift
    while IFS=$'\t' read -r sha fname; do
      [ -z "$sha" ] && continue
      case "$sha" in NOT_DOWNLOADED*|TODO*|n/a|N/A|"") continue;; esac
      # find a committed file in sources/ whose sha256 matches
      local matched=false
      for cand in "$srcdir"/*; do
        [ -f "$cand" ] || continue
        case "$(basename "$cand")" in manifest.json|SOURCE_NOTE.md) continue;; esac
        local got
        got=$(sha256sum "$cand" 2>/dev/null | cut -d' ' -f1)
        if [ "$got" = "$sha" ]; then matched=true; break; fi
      done
      if [ "$matched" != true ]; then
        # allow a documented drift via SOURCE_NOTE.md
        if [ -f "$srcdir/SOURCE_NOTE.md" ] && grep -q "$sha" "$srcdir/SOURCE_NOTE.md" 2>/dev/null; then
          : # drift documented, accepted
        else
          source_ok=false; reasons+=("sha256 $sha:not replay-verifiable (no committed file, no SOURCE_NOTE)")
        fi
      fi
    done < <(python3 - "$manifest" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
def walk(o):
    if isinstance(o,dict):
        s=o.get('sha256'); f=o.get('filename') or o.get('file') or ''
        if s: print(f"{s}\t{f}")
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
walk(m)
PY
)
    [ "$source_ok" = true ] || fail=1
  fi

  # --- Gate 5: mapping/cross_reference targets resolve to a loaded framework ---
  # (anti-dangling, via canonical framework_code_alias). Non-fatal if the validator
  # script is absent (older checkout); fatal only on a real dangling target.
  local dangling_ok=true
  local validator="$ROOT/scripts/validate_framework_mappings.py"
  if [ -f "$validator" ]; then
    if ! python3 "$validator" --code "$CODE" >/dev/null 2>&1; then
      dangling_ok=false; fail=1; reasons+=("mapping target(s) dangling -- run: python3 scripts/validate_framework_mappings.py --code $CODE")
    fi
  fi

  # --- Gate 6: coverage ratio (new_count vs max(legacy, reference)) ---
  # RETEX 2026-05-26 (W2A-W2E.1 incident): 8 frameworks shipped with 40-76%
  # coverage of legacy assessable count. Coverage gate now BLOQUE on FAIL.
  # Honors --justified flag recorded in coverage_report.json (PASS_JUSTIFIED /
  # WARN_JUSTIFIED are accepted, FAIL / WARN without justified are rejected).
  local coverage_ok=true
  local cov_report="$dir/data/coverage_report.json"
  if [ -f "$cov_report" ]; then
    local verdict
    verdict=$(python3 -c "import json,sys; print(json.load(open('$cov_report')).get('verdict',''))" 2>/dev/null)
    case "$verdict" in
      PASS|PASS_JUSTIFIED|WARN_JUSTIFIED) : ;;  # accepted
      WARN) coverage_ok=false; fail=1; reasons+=("coverage WARN without --justified -- enrich or record justification") ;;
      FAIL) coverage_ok=false; fail=1; reasons+=("coverage FAIL -- re-author with Phase 2.4 STRONG_SPLIT or pass --justified") ;;
      *)    coverage_ok=false; fail=1; reasons+=("coverage_report.json present but verdict unrecognized: $verdict") ;;
    esac
  else
    # No coverage report yet: WARN if PLAN.md declares a baseline, else skip silently
    if [ -f "$dir/PLAN.md" ] && grep -qE 'assessables_(legacy|reference)' "$dir/PLAN.md"; then
      coverage_ok=false; fail=1
      reasons+=("PLAN.md declares baseline but data/coverage_report.json missing -- run: bash .claude/skills/import-framework/scripts/coverage_gate.sh $CODE")
    fi
  fi

  # --- Gate 7: AUDITOR VOICE STRICT v2 (Phase 2.3bis, RETEX GDPR 2026-05-26) ---
  # Block 3 known FAIL patterns: wrapper ("Has ... implemented the following requirement"),
  # description normative ("The X shall ..."), dump verbatim (title ~= requirement_text).
  local voice_ok=true
  local voice_out
  voice_out=$(python3 - "$CODE" "$ROOT" <<'PY' 2>&1
import json, glob, re, sys, os
code = sys.argv[1]; root = sys.argv[2]
wrapper_re = re.compile(r'(implemented|complied with|met|satisfied|addressed)\s+the\s+following\s+(requirement|control|obligation)', re.I)
desc_re = re.compile(r'^\s*(the\s+(organi[sz]ation|controller|processor|entity|supervisor|provider|operator|member\s+states)\s+shall|l\'?organisation\s+doit|personal\s+data\s+shall)', re.I)
def dump_ratio(t, r):
    if not r: return 0
    tw = set(x.lower() for x in re.findall(r'\w+', t))
    rw = set(x.lower() for x in re.findall(r'\w+', r))
    return (len(tw & rw) / len(rw)) if rw else 0
tot = 0; w = 0; d_ = 0; dump = 0
patterns = [
    f"{root}/config/survey/frameworks/{code}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.lower()}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.upper()}/*_part*.json",
]
seen = set()
for pat in patterns:
    for p in sorted(glob.glob(pat)):
        if p in seen: continue
        seen.add(p)
        try: d = json.load(open(p))
        except Exception: continue
        qs = d.get('questions', []) if isinstance(d.get('questions'), list) else []
        for s in d.get('sections', []): qs += s.get('questions', [])
        for q in qs:
            tot += 1
            t = (q.get('title') or '').strip()
            r = (q.get('requirement_text') or '').strip()
            if wrapper_re.search(t): w += 1
            if desc_re.search(t): d_ += 1
            if r and dump_ratio(t, r) >= 0.80: dump += 1
fails = w + d_ + dump
print(f"tot={tot} wrapper={w} desc={d_} dump={dump} fails={fails}")
sys.exit(1 if fails else 0)
PY
)
  if [ $? -ne 0 ]; then
    voice_ok=false; fail=1; reasons+=("auditor_voice FAIL: $voice_out")
  fi

  # --- Gate 8: COMPOSITE DECOMPOSITION (Phase 2.3bis) ---
  # composite_audit.json must exist and have no missing splits + no over-plafond without justification.
  local composite_ok=true
  local comp_audit="$dir/data/composite_audit.json"
  if [ -f "$comp_audit" ]; then
    if ! python3 - "$comp_audit" <<'PY' >/dev/null 2>&1
import json, sys
d = json.load(open(sys.argv[1]))
if not isinstance(d, list): sys.exit(1)
bad = [e for e in d if e.get('n_obligations', 0) >= 2 and e.get('n_questions', 0) < 2]
ceil = [e for e in d if e.get('n_questions', 0) > 3 and not e.get('justification')]
sys.exit(1 if (bad or ceil) else 0)
PY
    then
      composite_ok=false; fail=1; reasons+=("composite_decomposition FAIL: bad splits or over-plafond items in $comp_audit")
    fi
  else
    # require composite_audit.json once Phase 2.3bis adopted (i.e. when questions exist)
    if [ "${sumarr:-0}" -gt 0 ] 2>/dev/null; then
      composite_ok=false; fail=1
      reasons+=("composite_decomposition FAIL: data/composite_audit.json missing -- run Phase 2.3bis audit")
    fi
  fi

  # --- Gate 9: MAPPING 5-TARGETS COVERAGE (Phase 3.1) ---
  # 5 mandatory targets: ISO_27001_2022, NIS2_DIRECTIVE, HIPAA, NIST_CSF_2_0, ANSSI.
  # absence_justified accepted in metadata.{target}.absence_justified.
  local five_ok=true
  local mfile_lc="$ROOT/config/mappings/$(echo "$CODE" | tr '[:upper:]' '[:lower:]')_unified_mappings.json"
  local mfile_uc="$ROOT/config/mappings/${CODE}_unified_mappings.json"
  local mfile=""
  [ -f "$mfile_lc" ] && mfile="$mfile_lc"
  [ -z "$mfile" ] && [ -f "$mfile_uc" ] && mfile="$mfile_uc"
  if [ -n "$mfile" ]; then
    local five_out
    five_out=$(python3 - "$mfile" <<'PY' 2>&1
import json, sys
m = json.load(open(sys.argv[1]))
required = {'ISO_27001_2022','NIS2_DIRECTIVE','HIPAA','NIST_CSF_2_0','ANSSI'}
found = set()
for fm in m.get('framework_mappings', []):
    for t in fm.get('target_frameworks', {}).keys(): found.add(t)
missing = required - found
meta = m.get('metadata', {})
unjustified = [t for t in missing if not meta.get(t, {}).get('absence_justified')]
if unjustified: print(f"missing 5-target (no justification): {unjustified}"); sys.exit(1)
print(f"5-targets ok: present={sorted(found & required)} absent_justified={sorted(missing)}")
PY
)
    if [ $? -ne 0 ]; then
      five_ok=false; fail=1; reasons+=("five_targets_coverage FAIL: $five_out")
    fi
  else
    # mappings file required once maps>0 already loaded
    if [ "${maps:-0}" -gt 0 ] 2>/dev/null; then
      five_ok=false; fail=1; reasons+=("five_targets_coverage FAIL: unified_mappings.json not found for $CODE")
    fi
  fi

  # --- Gate 10bis: QUESTION QUALITY (Phase 2.4ter, per-question rigor) ---
  # Each question must carry: composite_obligation, source_paragraph, evidence_expected[>=2],
  # cross_reference with 5 targets (each having source_type+confidence+rationale OR absence_justified),
  # control_reference.
  local qual_ok=true
  local qual_out
  qual_out=$(python3 - "$CODE" "$ROOT" <<'PY' 2>&1
import json, glob, sys, os
code = sys.argv[1]; root = sys.argv[2]
REQUIRED_TARGETS = {'ISO_27001_2022','NIS2_DIRECTIVE','HIPAA','NIST_CSF_2_0','ANSSI'}
ALLOWED_SRC = {'official_crosswalk','authoritative_derived','inference'}
tot = 0
miss_composite = miss_para = miss_ev = miss_ref = 0
miss_xref = miss_xref_targets = bad_xref_struct = 0
patterns = [
    f"{root}/config/survey/frameworks/{code}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.lower()}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.upper()}/*_part*.json",
]
seen = set()
for pat in patterns:
    for p in sorted(glob.glob(pat)):
        if p in seen: continue
        seen.add(p)
        try: d = json.load(open(p))
        except Exception: continue
        qs = d.get('questions', []) if isinstance(d.get('questions'), list) else []
        for s in d.get('sections', []): qs += s.get('questions', [])
        for q in qs:
            tot += 1
            if not q.get('composite_obligation'): miss_composite += 1
            if not q.get('source_paragraph'): miss_para += 1
            if not q.get('control_reference'): miss_ref += 1
            ev = q.get('evidence_expected') or []
            if not isinstance(ev, list) or len(ev) < 2: miss_ev += 1
            xref = q.get('cross_reference')
            if not xref or not isinstance(xref, dict):
                miss_xref += 1; continue
            present = set(xref.keys())
            if not REQUIRED_TARGETS.issubset(present):
                missing = REQUIRED_TARGETS - present
                miss_xref_targets += 1
                continue
            for tgt in REQUIRED_TARGETS:
                blk = xref.get(tgt, {})
                if not isinstance(blk, dict):
                    bad_xref_struct += 1; break
                if blk.get('absence_justified'):
                    continue
                st = blk.get('source_type')
                cf = blk.get('confidence', 0) or 0
                rationale = blk.get('rationale', '')
                targets = blk.get('targets', [])
                if st not in ALLOWED_SRC or not rationale or not targets:
                    bad_xref_struct += 1; break
                if cf > 0.7 and st not in {'official_crosswalk','authoritative_derived'}:
                    bad_xref_struct += 1; break
                if cf > 0.7 and not blk.get('source_url'):
                    bad_xref_struct += 1; break
                if st == 'inference' and (cf < 0.5 or cf > 0.7 or not blk.get('thematic_domain')):
                    bad_xref_struct += 1; break
fails = miss_composite + miss_para + miss_ref + miss_ev + miss_xref + miss_xref_targets + bad_xref_struct
print(f"tot={tot} composite={miss_composite} source_para={miss_para} ctrl_ref={miss_ref} evidence<2={miss_ev} xref_absent={miss_xref} xref_5targets_missing={miss_xref_targets} xref_bad_struct={bad_xref_struct}")
sys.exit(1 if fails else 0)
PY
)
  if [ $? -ne 0 ]; then
    qual_ok=false; fail=1; reasons+=("question_quality FAIL: $qual_out")
  fi

  # --- Gate 12: ANTI-PARAPHRASE + INTELLIGENCE (Phase 2.4ter, RETEX 2026-05-26) ---
  # Detects: paraphrase (lemma_overlap title vs requirement_text > 0.70),
  # generic evidence ("documentation for X"), generic rationale (<60 chars or
  # starts with "covers/maps/equivalent/similar").
  local intel_ok=true
  local intel_out
  intel_out=$(python3 - "$CODE" "$ROOT" <<'PY' 2>&1
import json, glob, re, sys
code = sys.argv[1]; root = sys.argv[2]
STOP = set("a an the of for to in on at by and or with from as is are be been being shall must should may any all such this that these those it which who whom what when where why how".split())
def lemmas(s):
    return [w.lower() for w in re.findall(r'[a-zA-Z]+', s) if w.lower() not in STOP and len(w) > 2]
def overlap(t, r):
    tw = set(lemmas(t)); rw = set(lemmas(r))
    if not rw: return 0.0
    return len(tw & rw) / len(rw)
GENERIC_EV = re.compile(r'documentation\s*(/|or)?\s*evidence\s+for\s+requirement|evidence\s+for\s+requirement|documentation\s+for\s+requirement', re.I)
GENERIC_RAT_PREFIX = re.compile(r'^\s*(covers?|maps?|equivalent|partial|similar|same|related)\s', re.I)
REQUIRED_TARGETS = {'ISO_27001_2022','NIS2_DIRECTIVE','HIPAA','NIST_CSF_2_0','ANSSI'}
para = ev_gen = rat_gen = rat_short = 0
tot = 0
patterns = [
    f"{root}/config/survey/frameworks/{code}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.lower()}/*_part*.json",
    f"{root}/config/survey/frameworks/{code.upper()}/*_part*.json",
]
seen = set()
for pat in patterns:
    for p in sorted(glob.glob(pat)):
        if p in seen: continue
        seen.add(p)
        try: d = json.load(open(p))
        except Exception: continue
        qs = d.get('questions', []) if isinstance(d.get('questions'), list) else []
        for s in d.get('sections', []): qs += s.get('questions', [])
        for q in qs:
            tot += 1
            t = q.get('title') or ''
            r = q.get('requirement_text') or ''
            if r and overlap(t, r) > 0.70: para += 1
            for e in (q.get('preuves_attendues') or []) + (q.get('evidence_expected') or []):
                if GENERIC_EV.search(e or ''): ev_gen += 1; break
            xref = q.get('cross_reference') or {}
            for tgt in REQUIRED_TARGETS:
                blk = xref.get(tgt)
                if not isinstance(blk, dict): continue
                if blk.get('absence_justified'): continue
                rat = blk.get('rationale') or ''
                if len(rat) < 60: rat_short += 1; break
                if GENERIC_RAT_PREFIX.match(rat): rat_gen += 1; break
fails = para + ev_gen + rat_gen + rat_short
print(f"tot={tot} paraphrase>70%={para} generic_evidence={ev_gen} generic_rationale={rat_gen} short_rationale<60={rat_short}")
sys.exit(1 if fails else 0)
PY
)
  if [ $? -ne 0 ]; then
    intel_ok=false; fail=1; reasons+=("intelligence_anti_paraphrase FAIL: $intel_out")
  fi

  # --- Gate 10: MAPPING RELIABILITY (Phase 3.1bis) ---
  # source_type in {official_crosswalk, authoritative_derived, inference}.
  # confidence>0.7 requires official_crosswalk or authoritative_derived.
  # inference requires justification or thematic_domain.
  local reliab_ok=true
  if [ -n "$mfile" ]; then
    local reliab_out
    reliab_out=$(python3 - "$mfile" <<'PY' 2>&1
import json, sys
m = json.load(open(sys.argv[1]))
ALLOWED = {'official_crosswalk','authoritative_derived','inference'}
bad_src = bad_conf = bad_inf = 0
for fm in m.get('framework_mappings', []):
    for tgt, blk in fm.get('target_frameworks', {}).items():
        for x in blk.get('mappings', []):
            st = x.get('source_type'); cf = x.get('confidence', 0) or 0
            if st not in ALLOWED: bad_src += 1
            if cf > 0.7 and st not in {'official_crosswalk','authoritative_derived'}: bad_conf += 1
            if st == 'inference' and not x.get('justification') and not x.get('thematic_domain'): bad_inf += 1
total = bad_src + bad_conf + bad_inf
print(f"bad_src={bad_src} bad_conf={bad_conf} bad_inf={bad_inf}")
sys.exit(1 if total else 0)
PY
)
    if [ $? -ne 0 ]; then
      reliab_ok=false; fail=1; reasons+=("mapping_reliability FAIL: $reliab_out")
    fi
  fi

  # --- write EVIDENCE.json (booleans computed from reality, not asserted) ---
  local verified=false; [ "$fail" = "0" ] && verified=true
  mkdir -p "$srcdir"
  python3 - "$srcdir/EVIDENCE.json" "$CODE" "$tracking_ok" "$active_ok" "$parts_ok" "$array_ok" "$source_ok" "$dangling_ok" "$coverage_ok" "$voice_ok" "$composite_ok" "$five_ok" "$reliab_ok" "$qual_ok" "$intel_ok" "$verified" "${sumarr:-0}" "${parts:-0}" "${maps:-0}" "${badrows:-0}" <<'PY'
import json,sys,datetime
(out,code,trk,act,prt,arr,src,dng,cov,voice,comp,five,rel,qual,intel,ver,sumarr,parts,maps,bad)=sys.argv[1:21]
b=lambda x:x=="true"
json.dump({
  "schema":"import-evidence-v4",
  "code":code,
  "verified_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "gates":{
    "tracking_files_present":b(trk),
    "framework_active":b(act),
    "survey_parts_present":b(prt),
    "questions_are_array":b(arr),
    "source_replay_verifiable":b(src),
    "mapping_targets_resolve":b(dng),
    "coverage_ratio_ok":b(cov),
    "auditor_voice_strict_v2":b(voice),
    "composite_decomposition":b(comp),
    "five_targets_coverage":b(five),
    "mapping_reliability":b(rel),
    "question_quality":b(qual),
    "intelligence_anti_paraphrase":b(intel),
  },
  "metrics":{"array_questions":int(sumarr),"parts":int(parts),"mappings":int(maps),"non_array_rows":int(bad)},
  "evidence_verified":b(ver),
}, open(out,"w"), indent=2)
print()
PY

  if [ "$fail" = "0" ]; then
    echo "PASS  $CODE  parts=$parts q=$sumarr maps=$maps  EVIDENCE.json evidence_verified=true"
    return 0
  else
    echo "FAIL  $CODE  -> ${reasons[*]}"
    return 1
  fi
}

rc=0
if [ "$1" = "--all" ]; then
  for d in "$TRACK_BASE"/*/; do
    c=$(basename "$d")
    case "$c" in _AUDIT*) continue;; esac
    [ -f "$d/sources/manifest.json" ] || continue
    verify_one "$c" || rc=1
  done
else
  verify_one "$1" || rc=1
fi
exit $rc
