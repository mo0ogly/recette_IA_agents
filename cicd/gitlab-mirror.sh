#!/usr/bin/env bash
# ===========================================================================
# gitlab-mirror.sh -- push a clean mirror of main to the internal GitLab.
#
# This file is the ONLY one that must spell out the internal-tooling tokens
# (in its scrub regex + comments), so it EXCLUDES ITSELF from the mirror it
# builds (see the removal list below). It is sourced by cicd/git.sh, which
# stays free of those tokens.
#
# Operator decision (2026-07-07): GitHub keeps everything; the internal GitLab
# must carry NO internal-tooling reference. Two kinds of the vendor string
# exist in the tree and only ONE is stripped:
#   - KEPT    : the Anthropic LLM *model* ids (product config in the LLM
#               catalog / campaigns) -- removing them breaks the platform.
#   - STRIPPED: the tooling directory, docs/plans/, and every tooling
#               reference in tracked text files (paths + doc mentions).
#
# The mirror is built on top of GitLab `main` (already tooling-free): main's
# tree is overlaid, the tooling is stripped, ONE clean commit is made, then
# pushed as a branch + MR. A verification grep ABORTS the push if any tooling
# reference survives -- the mirror never ships one.
#
# Safety: throwaway worktree (main working tree never touched, R21); token from
# .env (GITLAB_TOKEN, gitignored, R18), masked in output; force-push of a
# derived mirror branch gated by confirm (R1).
# ===========================================================================

GITLAB_URL_HOST="gitlab.cossi.internet"
GITLAB_PROJECT="sdo/desc/siq/cyber_lab_agents_ia"

# Paths removed from the mirror wholesale (dir tokens live here on purpose).
_MIRROR_REMOVE=( ".claude" "docs/plans" "cicd/gitlab-mirror.sh" )

# A line is a TOOLING reference iff it matches this and NOT the model regex.
# Built from fragments so this pattern is the single place the literals appear.
_dot="."
_CLAUDE_TOOLING_RE="${_dot}claude/|CLAUDE${_dot}md|[Cc]laude [Cc]ode|claude${_dot}ai|[Cc]o-[Aa]uthored-[Bb]y: Claude|[Gg]enerated with ${_dot}*Claude"
_CLAUDE_MODEL_RE='claude-(opus|sonnet|haiku|fable)|anthropic/claude'

git_push_gitlab() {
    local target="mirror/main" dry=0 a
    for a in "$@"; do
        case "${a}" in
            --dry-run) dry=1 ;;
            -*) err "flag inconnu: ${a}"; return 1 ;;
            *) target="${a}" ;;
        esac
    done
    # shellcheck disable=SC1091
    [ -f "${REPO_ROOT}/.env" ] && . "${REPO_ROOT}/.env" 2>/dev/null || true
    if [ -z "${GITLAB_TOKEN:-}" ]; then
        err "GITLAB_TOKEN absent de ${REPO_ROOT}/.env (R18)"; return 1
    fi
    local url="https://oauth2:${GITLAB_TOKEN}@${GITLAB_URL_HOST}/${GITLAB_PROJECT}.git"
    hdr "GitLab mirror propre -> ${target}$( [ "${dry}" -eq 1 ] && echo '  [DRY-RUN]')"

    local wt; wt="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "git -C '${REPO_ROOT}' worktree remove --force '${wt}' >/dev/null 2>&1 || true" RETURN
    # Base the mirror on GitLab main (already tooling-free); overlay local main.
    g fetch --quiet "${url}" main 2>/dev/null || { err "fetch gitlab main KO"; return 1; }
    g worktree add --quiet --detach "${wt}" FETCH_HEAD

    local rc=0
    (
        set -e
        cd "${wt}"
        git checkout main -- .
        local p
        for p in "${_MIRROR_REMOVE[@]}"; do
            git rm -r --cached --quiet "${p}" 2>/dev/null || true
            rm -rf "${p}"
        done
        # Line-level scrub: drop tooling-reference lines from tracked TEXT files
        # (model-id lines never match this pattern). -I skips binaries.
        local f
        while IFS= read -r f; do
            [ -f "${f}" ] || continue
            grep -vE "${_CLAUDE_TOOLING_RE}" "${f}" > "${f}.mirror" 2>/dev/null || cp "${f}" "${f}.mirror"
            mv "${f}.mirror" "${f}"
        done < <(git grep -lIE "${_CLAUDE_TOOLING_RE}" 2>/dev/null || true)
        git add -A
        # Verify: no tooling reference may survive (model ids are allowed).
        local residual
        residual="$(git grep -nIE "${_CLAUDE_TOOLING_RE}" 2>/dev/null | grep -vE "${_CLAUDE_MODEL_RE}" || true)"
        if [ -n "${residual}" ]; then
            echo "RESIDUAL_TOOLING_REF_FOUND"; echo "${residual}" | head -20; exit 3
        fi
        git commit --quiet -m "sync: recette platform (inspect_ia_agents)"
        if [ "${dry}" -eq 1 ]; then
            echo "DRY_OK: arbre miroir propre (0 reference outillage), non pousse"; exit 0
        fi
        git push --force "${url}" HEAD:"refs/heads/${target}" \
            -o merge_request.create -o merge_request.target=main \
            -o merge_request.title="sync: recette platform" 2>&1 \
          | sed "s#${GITLAB_TOKEN}#<TOKEN>#g"
    ) || rc=$?
    if [ "${rc}" -eq 0 ]; then
        [ "${dry}" -eq 1 ] && ok "DRY-RUN: miroir verifie propre (non pousse)" \
                           || ok "GitLab a jour (miroir propre) sur ${target}"
    elif [ "${rc}" -eq 3 ]; then
        err "reference outillage residuelle -> push ANNULE (rien pousse)"
    else
        err "mirror KO (rc=${rc})"
    fi
    return "${rc}"
}
