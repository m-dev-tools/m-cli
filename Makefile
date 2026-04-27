.PHONY: install test test-lf watch lint format mypy cov check vista push pull hooks

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
PTW    := .venv/bin/ptw
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
PRECOMMIT := .venv/bin/pre-commit

install:
	uv sync --extra dev
	$(MAKE) hooks

hooks:
	$(PRECOMMIT) install --hook-type pre-commit --hook-type pre-push

test:
	$(PYTEST)

test-lf:
	$(PYTEST) --lf

watch:
	$(PTW) -- --tb=short

lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

mypy:
	$(MYPY) src/

cov:
	$(PYTEST) --cov --cov-report=term-missing

# Run the full VistA round-trip validation gate (39,330 routines)
vista:
	$(PYTHON) scripts/vista_round_trip.py /home/rafael/vista-meta/vista/vista-m-host/Packages

check: lint mypy cov

pull:
	git pull origin main

push: check
	git push origin main
