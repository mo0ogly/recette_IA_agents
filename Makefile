# AgentRail recette -- local + Docker lab targets.
.PHONY: help install install-check validate run discovery test gates \
        docker-build lab lab-down docker-test docker-gates

help:
	@echo "Setup:"
	@echo "  make install      install the platform (native venv + Docker lab, verified)"
	@echo "  make install-check report install status, change nothing"
	@echo "Local (needs python3 + .venv-pyaudit for gates):"
	@echo "  make validate     schema-validate the corpus"
	@echo "  make run          identification recette scorecard"
	@echo "  make discovery    discovery recette (offline reference oracle)"
	@echo "  make test         full unittest suite"
	@echo "  make gates        strict ruff + mypy + bandit (.venv-pyaudit)"
	@echo "Docker lab:"
	@echo "  make docker-build build the lab image"
	@echo "  make lab          run discovery recette over HTTP vs the mock :8081"
	@echo "  make docker-test  run the test suite in the image"
	@echo "  make docker-gates run the strict gates in the image"
	@echo "  make lab-down     stop the lab"

# --- setup ---
install:
	scripts/install.sh

install-check:
	scripts/install.sh --check

# --- local ---
validate:
	python3 -m recette validate

run:
	python3 -m recette run

discovery:
	python3 -m recette discovery --adapter reference

test:
	python3 -m unittest discover -s tests

gates:
	.venv-pyaudit/bin/ruff check recette tests scripts
	.venv-pyaudit/bin/ruff format --check recette tests scripts
	.venv-pyaudit/bin/mypy recette
	.venv-pyaudit/bin/bandit -q -r recette --severity-level medium
	@echo "gates: PASS"

# --- docker lab ---
docker-build:
	docker compose build

lab: docker-build
	docker compose run --rm recette

docker-test: docker-build
	docker compose run --rm tests

docker-gates: docker-build
	docker compose run --rm gates

lab-down:
	docker compose down
