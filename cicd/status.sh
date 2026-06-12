#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# status.sh - one-shot snapshot of the recette platform
#
# Shows: git state, python venvs, docker images, lab containers, API server.
# ===========================================================================

CICD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${CICD_DIR}/lib/common.sh"

hdr "GIT"
branch="$(git -C "${REPO_ROOT}" branch --show-current 2>/dev/null || echo '?')"
head="$(git -C "${REPO_ROOT}" log --oneline -1 2>/dev/null || echo '?')"
ahead="$(git -C "${REPO_ROOT}" rev-list --count @{u}..HEAD \
    2>/dev/null || echo '?')"
info "branche : ${branch}"
info "HEAD    : ${head}"
info "commits non pousses : ${ahead}"

hdr "PYTHON"
for v in .venv .venv-pyaudit; do
    if [ -d "${REPO_ROOT}/${v}" ]; then
        ok "${v} present"
    else
        warn "${v} absent"
    fi
done

hdr "IMAGES DOCKER"
if command -v docker >/dev/null 2>&1; then
    docker images --filter reference='railgun-recette:*' \
        --format '  {{.Repository}}:{{.Tag}}  {{.Size}}  {{.CreatedSince}}' \
        || warn "aucune image railgun-recette"
else
    warn "docker introuvable"
fi

hdr "CONTENEURS LAB"
if command -v docker >/dev/null 2>&1; then
    ( cd "${REPO_ROOT}" && docker compose ps 2>/dev/null ) || true
else
    warn "docker introuvable"
fi

# API status delegated to api.sh (single source of truth)
"${CICD_DIR}/api.sh" status
