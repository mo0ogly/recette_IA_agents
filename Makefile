# AgentRail recette -- local + Docker lab targets.
.PHONY: help install install-check validate run discovery report test gates smoke \
        api docker-build lab lab-down docker-test docker-gates \
        platform-lab platform-e2e platform-down console \
        bnp role-matrix role-matrix-live coverage-guard rag rag-live rag-kb rag-e2e \
        system-recette system-recette-live recette

help:
	@echo "Setup:"
	@echo "  make install      install the platform (native venv + Docker lab, verified)"
	@echo "  make install-check report install status, change nothing"
	@echo "Local (needs python3 + .venv-pyaudit for gates):"
	@echo "  make validate     schema-validate the corpus"
	@echo "  make run          identification recette scorecard"
	@echo "  make discovery    discovery recette (offline reference oracle, all surfaces)"
	@echo "  make report       aggregate report (identification + all discovery surfaces)"
	@echo "  make bnp          run the BNP governed-campaign harness (verdict check)"
	@echo "  make role-matrix  run the role x action matrix harness (every role x every action)"
	@echo "  make role-matrix-live  drive each role over its domain via a live Groq LLM"
	@echo "  make coverage-guard    fail if ANY recette dimension has a gap (single gate)"
	@echo "  make rag          run the RAG poisoning campaigns through the gateway"
	@echo "  make rag-live     drive the poisoned knowledge base against a live Groq LLM"
	@echo "  make rag-kb       list the operator knowledge base (CRUD off the agent path)"
	@echo "  make rag-e2e      deterministic loop: reset -> apply scenario -> gateway blocks -> reset"
	@echo "  make recette      full governed recette: guard + validate + run + discovery + bnp + role-matrix + rag"
	@echo "  make test         full unittest suite"
	@echo "  make gates        strict ruff + mypy + bandit (.venv-pyaudit)"
	@echo "  make api          run the Track U API (uvicorn, needs the [api] extra)"
	@echo "Docker lab:"
	@echo "  make docker-build build the lab image"
	@echo "  make lab          run discovery recette over HTTP vs the mock :8081"
	@echo "  make docker-test  run the test suite in the image"
	@echo "  make docker-gates run the strict gates in the image"
	@echo "  make lab-down     stop the lab"
	@echo "Platform lab (gateway + lab mock + e2e):"
	@echo "  make platform-lab  start lab-mock :8082 + api :8090 (docker)"
	@echo "  make platform-e2e  run the end-to-end governed-flow recette"
	@echo "  make platform-down stop everything"
	@echo "  make console       run the approval console dev server (Vite)"

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

report:
	python3 -m recette report

bnp:
	python3 scripts/run_bnp_scenarios.py

role-matrix:
	python3 scripts/run_role_matrix.py

role-matrix-live:
	python3 scripts/run_role_matrix_live_groq.py

coverage-guard:
	python3 -m unittest tests.test_coverage_guard

rag:
	python3 scripts/run_role_matrix.py --dir campaigns/rag

rag-live:
	python3 scripts/run_rag_poisoning_live_groq.py

rag-kb:
	python3 -m recette rag-kb list

rag-e2e:
	python3 scripts/run_rag_poisoning_e2e.py

system-recette:
	python3 scripts/run_system_recette.py

system-recette-live:
	python3 scripts/run_system_recette.py --live

recette: coverage-guard validate run discovery bnp role-matrix rag system-recette
	@echo "recette: ALL PASS"

test:
	python3 -m unittest discover -s tests

smoke:
	./recette.sh smoke

gates:
	.venv-pyaudit/bin/ruff check recette tests scripts
	.venv-pyaudit/bin/ruff format --check recette tests scripts
	.venv-pyaudit/bin/mypy recette
	.venv-pyaudit/bin/bandit -q -r recette --severity-level medium
	@echo "gates: PASS"

api:
	python3 -m recette.api

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

# --- platform lab (gateway + lab mock + e2e) ---
platform-lab:
	docker compose up -d lab-mock api

platform-e2e:
	docker compose run --rm e2e

platform-down:
	docker compose down

console:
	cd console && npm run dev
