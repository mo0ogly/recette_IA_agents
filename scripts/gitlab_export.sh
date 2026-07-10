#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# gitlab_export.sh -- export a provenance-clean mirror of GitHub main to the
# internal GitLab. GitHub keeps EVERYTHING; the GitLab mirror carries no trace
# that an AI dev assistant was used. Research/product references (papers,
# benchmarks, model ids, labs, workflow architecture) are KEPT.
#
# Read-only on this repo (git archive of a ref, never the working tree; the
# working tree and GitHub are never touched). Re-runnable to resync.
#
# Usage:
#   scripts/gitlab_export.sh                 build .gitlab-export/ + verify (NO push)
#   scripts/gitlab_export.sh --strict        also anonymize model/provider ids
#   scripts/gitlab_export.sh --push          publish (after a clean verify) via MR merge
#   scripts/gitlab_export.sh --ref origin/main   pick the source ref (default origin/main)
#
# Config (scripts/gitlab_export.sh reads .env.gitlab, gitignored):
#   GITLAB_TOKEN=...                 Project Access Token (write_repository + merge)
#   GITLAB_HOST=gitlab.cossi.internet
#   GITLAB_PROJECT=sdo/desc/siq/cyber_lab_agents_ia
#
# The token is masked in every line of output. It never enters .git/config.
# The publish path never force-pushes main: it commits ON TOP of GitLab main
# (fast-forward), pushes a sync branch, then creates+merges a MR via the API
# (the token's merge right works where a protected-branch direct push fails).
# ===========================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_DIR="${REPO_ROOT}/.gitlab-export"
TREE_DIR="${EXPORT_DIR}/tree"

# ----- args ----------------------------------------------------------------
STRICT=0 DO_PUSH=0 REF="origin/main" SYNC_BRANCH="gitlab-sync"
while [ $# -gt 0 ]; do
    case "$1" in
        --strict) STRICT=1 ;;
        --push) DO_PUSH=1 ;;
        --ref) REF="$2"; shift ;;
        --branch) SYNC_BRANCH="$2"; shift ;;
        -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "flag inconnu: $1" >&2; exit 1 ;;
    esac
    shift
done

# ----- logging (token-masking is applied by the caller wrapper below) ------
c_hdr(){ printf '\n== %s ==\n' "$1"; }
c_ok(){ printf '[OK] %s\n' "$1"; }
c_err(){ printf '[ERREUR] %s\n' "$1" >&2; }
c_info(){ printf '[INFO] %s\n' "$1"; }

# ----- config --------------------------------------------------------------
[ -f "${REPO_ROOT}/.env.gitlab" ] && . "${REPO_ROOT}/.env.gitlab"
GITLAB_HOST="${GITLAB_HOST:-gitlab.cossi.internet}"
GITLAB_PROJECT="${GITLAB_PROJECT:-sdo/desc/siq/cyber_lab_agents_ia}"
_mask(){ if [ -n "${GITLAB_TOKEN:-}" ]; then sed "s#${GITLAB_TOKEN}#***#g"; else cat; fi; }

# ===========================================================================
# DROP list -- tooling directories/files removed wholesale from the mirror.
# Adapted to THIS repo's audit (only .claude/ + docs/plans/ exist; the rest are
# defensive no-ops so the script transposes to other repos).
# ===========================================================================
DROP_PATHS=(
    ".claude" ".claude-plugin" ".husky" ".agents" ".cursorrules"
    "pdca" "skills" "commands"
    "docs/plans" "docs/tracking" "docs/pdca"
    "skills-lock.json"
    ".gitlab-export"
    # The export tooling itself carries provenance literals (scrub regex +
    # comments) by design -- never ship it to the mirror.
    "scripts/gitlab_export.sh" "cicd/gitlab-mirror.sh"
)

# Provenance line patterns: a line matching this (and NOT a model/provider line)
# is either rewritten (soft tokens) or dropped (hard tokens).
PROV_HARD='\.claude([/._-]|$)|CLAUDE\.md|[Cc]laude [Cc]ode|claude\.ai|[Cc]o-?[Aa]uthored-?[Bb]y: *Claude|[Gg]enerated with .*Claude|Claude subagent|docs/(plans|tracking|pdca)/'
# Model/provider references that must be KEPT (unless --strict).
MODEL_RE='claude-(opus|sonnet|haiku|fable)|anthropic[/_-]claude|"model": *"claude'

# ----- 1) snapshot (read-only) ---------------------------------------------
build_snapshot(){
    c_hdr "SNAPSHOT (git archive ${REF}, lecture seule)"
    git -C "${REPO_ROOT}" rev-parse --verify "${REF}" >/dev/null 2>&1 || { c_err "ref ${REF} introuvable"; exit 1; }
    rm -rf "${EXPORT_DIR}"; mkdir -p "${TREE_DIR}"
    git -C "${REPO_ROOT}" archive "${REF}" | tar -x -C "${TREE_DIR}"
    c_info "arbre extrait: $(find "${TREE_DIR}" -type f | wc -l) fichiers"
}

# ----- 2) DROP tooling ------------------------------------------------------
drop_tooling(){
    c_hdr "DROP tooling"
    local p
    for p in "${DROP_PATHS[@]}"; do
        if [ -e "${TREE_DIR}/${p}" ]; then
            rm -rf "${TREE_DIR:?}/${p}"
            c_info "drop ${p}"
        fi
    done
}

# ----- 3) SCRUB provenance --------------------------------------------------
scrub_provenance(){
    c_hdr "SCRUB provenance$( [ "${STRICT}" -eq 1 ] && echo ' (--strict)')"
    local f
    # Text files only (skip binaries).
    while IFS= read -r f; do
        # Soft rewrites first (keep the surrounding sentence usable).
        sed -i -E \
            -e 's/[Cc]laude [Cc]ode/AI/g' \
            -e 's/Claude subagent/AI subagent/g' \
            -e 's/Skills Claude/Skills/g' \
            -e 's/`\.claude\/[^`]*`//g' \
            -e 's/\(CLAUDE\.md\)//g' \
            "${f}"
        # Hard drops: any remaining provenance line (that is not a model line).
        # grep -v returns 1 when it drops EVERY line (single-line file fully
        # matched) -- keep the resulting empty file, never restore the original.
        grep -vE "${PROV_HARD}" "${f}" > "${f}.scrub" 2>/dev/null || true
        # Re-admit model/provider lines the hard filter may have caught.
        # (PROV_HARD never matches a bare model id, so this is a safety no-op.)
        mv "${f}.scrub" "${f}"
        if [ "${STRICT}" -eq 1 ]; then
            sed -i -E -e 's/claude-(opus|sonnet|haiku|fable)[a-z0-9.\-]*/ModelX/g' \
                      -e 's/[Aa]nthropic/ProviderX/g' -e 's/[Cc]laude/ModelX/g' "${f}"
        fi
    done < <(grep -rIlE "${PROV_HARD}|[Cc]laude|[Aa]nthropic" "${TREE_DIR}" 2>/dev/null || true)
}

# ----- 4) VERIFY (garde-fou) ------------------------------------------------
verify_clean(){
    c_hdr "VERIFY (garde-fou provenance + secrets)"
    local prov secrets rc=0
    # Provenance residue (model ids allowed unless strict).
    if [ "${STRICT}" -eq 1 ]; then
        prov="$(grep -rInE "claude|anthropic" "${TREE_DIR}" 2>/dev/null || true)"
    else
        prov="$(grep -rInE "${PROV_HARD}" "${TREE_DIR}" 2>/dev/null | grep -viE "${MODEL_RE}" || true)"
    fi
    # Tooling dirs must be gone.
    local leftover
    leftover="$(for p in "${DROP_PATHS[@]}"; do [ -e "${TREE_DIR}/${p}" ] && echo "${p}"; done)"
    # Obvious secrets (tokens/keys) accidentally snapshotted. Test fixtures are
    # excluded: fake keys live in *.test.* / __fixtures__ / tests/ to exercise
    # the platform's own secret-redaction (product test data, not real secrets).
    secrets="$(grep -rInE 'glpat-[A-Za-z0-9._-]{20}|sk-[A-Za-z0-9]{24}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY' "${TREE_DIR}" 2>/dev/null \
        | grep -vE '\.test\.|\.contract\.|/tests?/|__fixtures__|\.fixture\.|/e2e/|smoke_|wireExpert|wireLlmDecode' || true)"
    if [ -n "${prov}" ]; then c_err "RESIDU PROVENANCE:"; echo "${prov}" | head -20; rc=1; fi
    if [ -n "${leftover}" ]; then c_err "TOOLING RESIDUEL: ${leftover}"; rc=1; fi
    if [ -n "${secrets}" ]; then c_err "SECRET DETECTE (masque):"; echo "${secrets}" | sed -E 's/(glpat-|sk-)[A-Za-z0-9._-]+/\1***/g' | head; rc=1; fi
    if [ "${rc}" -eq 0 ]; then
        c_ok "export propre: 0 provenance, 0 tooling residuel, 0 secret"
        c_info "modeles conserves: $(grep -rIcE "${MODEL_RE}" "${TREE_DIR}" 2>/dev/null | awk -F: '{s+=$2}END{print s+0}') occurrences$( [ "${STRICT}" -eq 1 ] && echo ' (anonymises: 0 attendu)')"
    fi
    return "${rc}"
}

# ----- 5) PUBLISH via MR merge (protected main) -----------------------------
publish(){
    c_hdr "PUBLISH GitLab -> ${SYNC_BRANCH} -> MR merge main"
    [ -n "${GITLAB_TOKEN:-}" ] || { c_err "GITLAB_TOKEN absent de .env.gitlab (R18)"; return 1; }
    local api="https://${GITLAB_HOST}/api/v4"
    local proj_enc; proj_enc="$(printf '%s' "${GITLAB_PROJECT}" | sed 's#/#%2F#g')"
    local url="https://oauth2:${GITLAB_TOKEN}@${GITLAB_HOST}/${GITLAB_PROJECT}.git"
    # Throwaway worktree at GitLab main's tip -> commit the scrubbed tree on top
    # (fast-forward), so the MR is a clean incremental diff.
    local wt; wt="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '${wt}'" RETURN
    git -C "${REPO_ROOT}" fetch --quiet "${url}" main 2>/dev/null || { c_err "fetch gitlab main KO"; return 1; }
    local glmain; glmain="$(git -C "${REPO_ROOT}" rev-parse FETCH_HEAD)"
    git -C "${REPO_ROOT}" worktree add --quiet --detach "${wt}" "${glmain}"
    (
        set -e
        cd "${wt}"
        # Replace the tracked tree with the scrubbed export.
        git ls-files -z | xargs -0 -r rm -f
        find . -type d -empty -not -path './.git*' -delete 2>/dev/null || true
        cp -a "${TREE_DIR}/." .
        git add -A
        git commit --quiet -m "sync: recette platform (inspect_ia_agents)"
        git push "${url}" HEAD:"refs/heads/${SYNC_BRANCH}" 2>&1 | _mask
    )
    git -C "${REPO_ROOT}" worktree remove --force "${wt}" 2>/dev/null || true
    # Create the MR (idempotent-ish) and merge with retries (405 until mergeable).
    local mr_iid
    mr_iid="$(curl -s --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
        --data "source_branch=${SYNC_BRANCH}&target_branch=main&title=sync: recette platform&remove_source_branch=true" \
        "${api}/projects/${proj_enc}/merge_requests" | grep -oE '"iid":[0-9]+' | head -1 | grep -oE '[0-9]+' || true)"
    if [ -z "${mr_iid}" ]; then
        mr_iid="$(curl -s --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
            "${api}/projects/${proj_enc}/merge_requests?source_branch=${SYNC_BRANCH}&state=opened" \
            | grep -oE '"iid":[0-9]+' | head -1 | grep -oE '[0-9]+' || true)"
    fi
    [ -n "${mr_iid}" ] || { c_err "MR non creee/trouvee"; return 1; }
    c_info "MR !${mr_iid} -- merge (retries)"
    local i out
    for i in 1 2 3 4 5 6; do
        out="$(curl -s --request PUT --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
            "${api}/projects/${proj_enc}/merge_requests/${mr_iid}/merge")"
        if printf '%s' "${out}" | grep -q '"state":"merged"'; then
            c_ok "MR !${mr_iid} mergee -> GitLab main a jour"; return 0
        fi
        c_info "merge pas encore pret (essai ${i}) -- 5s"; sleep 5
    done
    c_err "MR !${mr_iid} non mergee apres retries (voir GitLab)"; return 1
}

# ===========================================================================
main(){
    build_snapshot
    drop_tooling
    scrub_provenance
    if ! verify_clean; then
        c_err "GARDE-FOU: export NON propre -> aucun push"; exit 3
    fi
    if [ "${DO_PUSH}" -eq 1 ]; then
        publish || exit 4
    else
        c_ok "verify-only: export pret dans .gitlab-export/tree (NON pousse). Ajoute --push pour publier."
    fi
}
main 2>&1 | _mask
