.PHONY: install test test-lf watch lint format mypy cov check vista vista-canonical lint-vista lint-modern lint-modern-baseline lint-modern-setup push pull hooks seed unseed test-vista

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
PTW    := .venv/bin/ptw
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
PRECOMMIT := .venv/bin/pre-commit

# vista-meta client wiring — see ~/claude/templates/m-vista-client/
VISTA_CONN := $(HOME)/data/vista-meta/conn.env
ifneq ($(wildcard $(VISTA_CONN)),)
include $(VISTA_CONN)
export VISTA_HOST VISTA_SSH_PORT VISTA_SSH_USER
export VISTA_HTTP_RPC_PORT VISTA_HTTP_FMQL_PORT VISTA_HTTP_ROCTO_PORT VISTA_HTTP_YDBGUI_PORT
endif

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

# Run the full VistA round-trip validation gate for `m fmt` (39,330 routines)
vista:
	$(PYTHON) scripts/vista_round_trip.py /home/rafael/vista-meta/vista/vista-m-host/Packages

# Run the canonical-layout gate: idempotency + AST shape preserved across the corpus
vista-canonical:
	$(PYTHON) scripts/vista_canonical.py /home/rafael/vista-meta/vista/vista-m-host/Packages

# Run the full VistA lint baseline (xindex + vista profiles, since the
# corpus *is* VistA — both apply).
lint-vista:
	$(PYTHON) scripts/vista_lint.py /home/rafael/vista-meta/vista/vista-m-host/Packages --top 10

# Run the modern (non-VistA) lint regression gate. Walks the corpora
# at $$HOME/projects/m-modern-corpus/ (set up via `make lint-modern-setup`)
# and compares per-corpus finding counts against the checked-in baseline.
lint-modern:
	$(PYTHON) scripts/lint_modern.py

# Refresh the modern-corpus baseline (after a deliberate rule change).
lint-modern-baseline:
	$(PYTHON) scripts/lint_modern.py --update-baseline

# One-time corpus clone. Idempotent; skips repos already present.
lint-modern-setup:
	bash scripts/setup_modern_corpus.sh

check: lint mypy cov

pull:
	git pull origin main

push: check
	git push origin main

# ── Shared vista-meta engine (see vista-meta/Makefile reseed-all) ───
seed:
	@./scripts/seed-vista.sh

unseed:
	@./scripts/unseed-vista.sh

test-vista: seed
	@$(PYTEST) -m vista || (rc=$$?; $(MAKE) unseed; exit $$rc)
	@$(MAKE) unseed
