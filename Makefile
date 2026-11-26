.PHONY: demo test install clean deploy cycles console stage-cycle start-cycle release-check

VENV ?= .venv
PYTHON = $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PYTEST = $(if $(wildcard $(VENV)/bin/pytest),$(VENV)/bin/pytest,python3 -m pytest)

install:          ## Install dev dependencies into virtual environment
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -r requirements.txt -r requirements-dev.txt

demo:             ## Run the full decision pipeline on seeded data. No GCP, no OAuth, no keys.
	$(PYTHON) -m demo.run_demo

cycles:           ## Show the intake clarification loop learning across two cycles
	$(PYTHON) -m demo.run_cycles

console:          ## Render the Gate console to demo/out/console.html
	$(PYTHON) -m demo.build_console

test:             ## Run the unit suite
	$(PYTEST) tests/ -q

release-check:    ## Run ruff lint and full unit suite
	$(PYTHON) -m ruff check src/ scripts/
	$(PYTEST) tests/ -q

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .hypothesis demo/out

deploy:           ## Deploy to Cloud Run (requires gcloud auth + PROJECT_ID)
	./infra/deploy.sh

stage-cycle:      ## Upload SOURCE_DIR as immutable cloud input (no processing)
	$(PYTHON) -m scripts.stage_cycle --source-dir "$(SOURCE_DIR)" --cycle-id "$(CYCLE_ID)" --auction-title "$(AUCTION_TITLE)" --auction-date "$(AUCTION_DATE)" --timezone "$(TIMEZONE_NAME)" --venue "$(VENUE)" --deadline "$(DEADLINE)"

start-cycle:      ## Upload SOURCE_DIR and write READY to start the Cloud Run Job
	$(PYTHON) -m scripts.stage_cycle --source-dir "$(SOURCE_DIR)" --cycle-id "$(CYCLE_ID)" --auction-title "$(AUCTION_TITLE)" --auction-date "$(AUCTION_DATE)" --timezone "$(TIMEZONE_NAME)" --venue "$(VENUE)" --deadline "$(DEADLINE)" --start
