# AgentRail recette lab image.
# Bakes the corpus + recette package so the discovery-mock and the recette runner
# share identical paths (/app/corpus/...). Includes the audit tools so the strict
# gates (ruff/mypy/bandit) run the same way in CI as locally.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first (better layer caching).
COPY pyproject.toml ./
RUN pip install "jsonschema>=4.0"

# Audit tooling for the strict gates (kept in the lab image so CI == local).
RUN pip install ruff mypy bandit pip-audit pytest types-jsonschema

# Source + corpus + tests + scripts (paths must match between services; scripts is
# included so the gates run the same set of files as locally).
COPY recette ./recette
COPY corpus ./corpus
COPY tests ./tests
COPY scripts ./scripts
RUN pip install -e .

# Default: run the offline discovery recette (no service needed).
CMD ["python", "-m", "recette", "discovery", "--adapter", "reference"]
