.PHONY: setup format format-check lint typecheck test test-cov smoke check

PYTHON ?= python
PIP ?= $(PYTHON) -m pip

setup:
	$(PIP) install -e ".[dev]"

format:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest -q

test-cov:
	pytest -q --cov=agent_reliability_lab --cov-report=term-missing

smoke:
	$(PYTHON) -c "import agent_reliability_lab; print('Package import successful')"
	$(PYTHON) -m agent_reliability_lab.cli --help

check: format-check lint typecheck test

format-check:
	ruff format --check .
