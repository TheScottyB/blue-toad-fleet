.PHONY: demo test install clean deploy cycles console stage-cycle start-cycle video video-verify video-prepare video-record video-compose release-check

VENV ?= .venv
PYTHON = $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PYTEST = $(if $(wildcard $(VENV)/bin/pytest),$(VENV)/bin/pytest,python3 -m pytest)

install:          ## Install dev dependencies into virtual environment
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -r requirements.txt -r requirements-dev.txt

demo:             ## Run the full decision pipeline on seeded data. No GCP, no OAuth, no keys.
	$(PYTHON) demo/run_demo.py

cycles:           ## Show the intake clarification loop learning across two cycles
	$(PYTHON) demo/run_cycles.py

console:          ## Render the Gate console to demo/out/console.html
	$(PYTHON) demo/build_console.py

test:             ## Run the unit suite
	$(PYTEST) tests/ -q

release-check:    ## Non-mutating full release gate; writes docs/evidence/RELEASE.md
	mkdir -p artifacts/release docs/evidence
	$(PYTEST) tests/ -q --junitxml=artifacts/release/pytest.xml
	$(PYTHON) scripts/build_release_report.py --junitxml artifacts/release/pytest.xml --output docs/evidence/RELEASE.md

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache demo/out

deploy:           ## Deploy to Cloud Run (requires gcloud auth + PROJECT_ID)
	./infra/deploy.sh

stage-cycle:      ## Upload SOURCE_DIR as immutable cloud input (no processing)
	$(PYTHON) scripts/stage_cycle.py --source-dir "$(SOURCE_DIR)" --cycle-id "$(CYCLE_ID)" --auction-title "$(AUCTION_TITLE)" --auction-date "$(AUCTION_DATE)" --timezone "$(TIMEZONE_NAME)" --venue "$(VENUE)" --deadline "$(DEADLINE)"

start-cycle:      ## Upload SOURCE_DIR and write READY to start the Cloud Run Job
	$(PYTHON) scripts/stage_cycle.py --source-dir "$(SOURCE_DIR)" --cycle-id "$(CYCLE_ID)" --auction-title "$(AUCTION_TITLE)" --auction-date "$(AUCTION_DATE)" --timezone "$(TIMEZONE_NAME)" --venue "$(VENUE)" --deadline "$(DEADLINE)" --start

video-prepare:    ## Verify facts and render declared video pages/cards (runs tests + gcloud proof)
	$(PYTHON) scripts/build_media.py prepare

video-record:     ## Record all four declared browser/terminal beats
	$(PYTHON) scripts/build_media.py record

video-compose:    ## Normalize the four recordings into final beat footage
	$(PYTHON) scripts/build_media.py compose

video:            ## Rebuild the complete facts-driven narrated submission video
	$(PYTHON) scripts/build_media.py all

video-verify:     ## Verify final dimensions, duration, size, and audio presence
	$(PYTHON) scripts/build_media.py verify
