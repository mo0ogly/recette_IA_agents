# inspect_ia_agents recette lab image -- multi-stage.
#
# The recette resolves the corpus relative to the package directory
# (Path(__file__).parent.parent / "corpus"), so the package MUST be installed
# editable with corpus as a sibling of recette at /app. A wheel in site-packages
# would break corpus resolution -- do not switch to a wheel install.
#
# Stages:
#   runtime -- minimal: jsonschema + the editable recette package + corpus only.
#              Non-root. Used by the discovery-mock service and the recette runner.
#   audit   -- runtime + strict-gate tooling (ruff/mypy/bandit/pip-audit/pytest)
#              + tests + scripts. Used by the gates and tests services so CI == local.

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dedicated non-root runtime user (least privilege; binds 8081 which is > 1024).
RUN groupadd --system recette && \
    useradd --system --gid recette --home-dir /app --shell /usr/sbin/nologin recette

# Dependency manifest first for better layer caching.
COPY pyproject.toml ./
COPY recette ./recette
COPY corpus ./corpus

# Runtime dep + editable install (keeps corpus a sibling of recette as required).
# [bundle] brings cryptography so `recette bundle-verify` works and its tests run for real.
# [api] brings fastapi/uvicorn so the Track U API (recette/api) tests run in the lab too.
# NOT installed here by design (R22): heavy/opt-in extras [redteam] (pyrit ~939MB),
# [real], [temporal], [maf], [postgres], [nats]. The red-team CORE (native attacker,
# deterministic gate, recorder, promote, /sim API) needs none of them; add [redteam]
# only to run `recette redteam-record --attacker pyrit` (see docs/runbooks/redteam-recette.md).
RUN pip install "jsonschema>=4.0" && \
    pip install -e ".[bundle,api]" && \
    chown -R recette:recette /app

USER recette

# Default: offline discovery recette (no external service needed).
CMD ["python", "-m", "recette", "discovery", "--adapter", "reference"]

# ---------------------------------------------------------------------------
FROM runtime AS audit

USER root

# Strict-gate + test tooling kept out of the runtime image (smaller attack surface).
# httpx backs fastapi.testclient.TestClient used by the Track U API tests.
RUN pip install ruff mypy bandit pip-audit pytest types-jsonschema httpx

# Tests + scripts are only needed by the gates/tests services.
COPY tests ./tests
COPY scripts ./scripts
RUN chown -R recette:recette /app

USER recette
