.PHONY: demo test install clean deploy

install:          ## Install dev dependencies
	python3 -m pip install -r requirements-dev.txt

demo:             ## Run the full decision pipeline on seeded data. No GCP, no OAuth, no keys.
	python3 demo/run_demo.py

test:             ## Run the unit suite
	python3 -m pytest tests/ -q

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

deploy:           ## Deploy to Cloud Run (requires gcloud auth + PROJECT_ID)
	./infra/deploy.sh

cycles:           ## Show the intake clarification loop learning across two cycles
	python3 demo/run_cycles.py

console:          ## Render the Gate console to demo/out/console.html
	python3 demo/build_console.py
