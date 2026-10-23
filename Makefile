PYTHON ?= .venv/bin/python

.PHONY: setup index run test eval demo docker-build docker-run

setup:
	python3.11 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
	cp -n .env.example .env || true

index:
	$(PYTHON) -m troubleshooter.cli --build-index

run:
	$(PYTHON) -m uvicorn troubleshooter.api:app --reload --port 8000

test:
	$(PYTHON) -m pytest

eval:
	$(PYTHON) -m eval.run_eval

demo:
	$(PYTHON) -m troubleshooter.cli --scenario none-sort

docker-build:
	docker build -t agentic-troubleshooter .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env agentic-troubleshooter
