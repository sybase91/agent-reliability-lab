.PHONY: setup format format-check lint typecheck test test-cov smoke check app app-test mvp-check

PYTHON ?= python
PIP ?= $(PYTHON) -m pip

setup:
	$(PIP) install -e ".[dev,ui]"

format:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest -q

test-cov:
	$(PYTHON) -m pytest -q --cov=src/agent_reliability_lab --cov-report=term-missing --cov-fail-under=85

smoke:
	$(PYTHON) -c "import agent_reliability_lab; print('Package import successful')"
	$(PYTHON) -m agent_reliability_lab.cli --help

check: format-check lint typecheck test

format-check:
	ruff format --check .

app:
	streamlit run app/streamlit_app.py

app-test:
	$(PYTHON) -m pytest -q tests/ui

mvp-check: format-check lint typecheck test-cov smoke app-test
	@echo "mvp-check passed"
