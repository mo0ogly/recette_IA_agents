#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# git.sh - git helpers for the recette repo (status / pull / push / sync)
#
# Usage: git.sh status|pull|push|sync|branches|clean-merged
#   push asks for confirmation (it publishes to origin).
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

g() { git -C "${REPO_ROOT}" "$@"; }

_branch() { g branch --show-current 2>/dev/null || echo '?'; }

git_status() {
    hdr "GIT status (${REPO_ROOT})"
    g status -sb
}

git_pull() {
    local br; br="$(_branch)"
    hdr "PULL ${br} (fast-forward only)"
    g pull --ff-only && ok "a jour" || err "pull KO (divergence ?)"
}

git_push() {
    local br; br="$(_branch)"
    local ahead
    ahead="$(g rev-list --count @{u}..HEAD 2>/dev/null || echo '?')"
    hdr "PUSH ${br} -> origin"
    info "commits a pousser : ${ahead}"
    g log --oneline @{u}..HEAD 2>/dev/null | sed 's/^/    /' || true
    echo
    if confirm "Pousser ${br} vers origin ?"; then
        g push origin "${br}" && ok "pousse" || err "push KO"
    else
        info "Annule."
    fi
}

git_sync() {
    hdr "SYNC (fetch + etat)"
    g fetch --all --prune
    local br; br="$(_branch)"
    local ahead behind
    ahead="$(g rev-list --count @{u}..HEAD 2>/dev/null || echo '?')"
    behind="$(g rev-list --count HEAD..@{u} 2>/dev/null || echo '?')"
    info "branche : ${br}"
    info "en avance : ${ahead}   en retard : ${behind}"
}

git_branches() {
    hdr "Branches locales"
    g branch -vv
}

# push-gitlab: clean GitLab mirror. The scrubber lives in a separate file that
# excludes itself from the mirror (it is the only file that must spell out the
# internal-tooling tokens). See cicd/gitlab-mirror.sh.
_load_gitlab_mirror() {
    local f="${CICD_DIR}/gitlab-mirror.sh"
    [ -f "${f}" ] || { err "cicd/gitlab-mirror.sh introuvable"; return 1; }
    # shellcheck disable=SC1090
    . "${f}"
}

git_clean_merged() {
    hdr "Branches mergees dans main (hors main)"
    local merged
    merged="$(g branch --merged main | grep -vE '^\*| main$' \
        | tr -d ' ' || true)"
    if [ -z "${merged}" ]; then
        info "aucune branche mergee a nettoyer"
        return 0
    fi
    echo "${merged}" | sed 's/^/    /'
    echo
    if confirm "Supprimer ces branches locales ?"; then
        echo "${merged}" | xargs -r -n1 git -C "${REPO_ROOT}" branch -d
        ok "branches nettoyees"
    else
        info "Annule."
    fi
}

action="${1:-status}"
case "${action}" in
    status)       git_status ;;
    pull)         git_pull ;;
    push)         git_push ;;
    push-gitlab)  shift; _load_gitlab_mirror && git_push_gitlab "$@" ;;
    sync)         git_sync ;;
    branches)     git_branches ;;
    clean-merged) git_clean_merged ;;
    *) err "action inconnue: ${action}"; \
       echo "  status|pull|push|push-gitlab|sync|branches|clean-merged"; exit 1 ;;
esac
