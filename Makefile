.PHONY: demo test install clean deploy cycles console video video-verify video-prepare video-record video-compose

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

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache demo/out

deploy:           ## Deploy to Cloud Run (requires gcloud auth + PROJECT_ID)
	./infra/deploy.sh

video-prepare:    ## Verify facts and render declared video pages/cards (runs tests + gcloud proof)
	$(PYTHON) scripts/video_pipeline.py prepare

video-record:     ## Record all four declared browser/terminal beats
	$(PYTHON) scripts/video_pipeline.py record

video-compose:    ## Normalize the four recordings into final beat footage
	$(PYTHON) scripts/video_pipeline.py compose

video:            ## Rebuild the complete facts-driven narrated submission video
	$(PYTHON) scripts/video_pipeline.py all

video-verify:     ## Verify final dimensions, duration, size, and audio presence
	$(PYTHON) scripts/video_pipeline.py verify
