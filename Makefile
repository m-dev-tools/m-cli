.PHONY: install test test-lf watch lint format mypy cov check lint-modern lint-modern-baseline lint-modern-setup push pull hooks seed unseed test-vista engine-up engine-down engine-status

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
PTW    := .venv/bin/ptw
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
PRECOMMIT := .venv/bin/pre-commit

# Default corpus for whole-corpus validation gates (round-trip, canonical,
# lint). Override per-invocation: `make vista CORPUS=/path/to/other/corpus`,
# or via environment: `CORPUS=... make vista`. Defaults to the in-org
# m-modern-corpus so gates work on a fresh clone without VistA access.
CORPUS ?= $(HOME)/projects/m-modern-corpus

# vista-meta client wiring — silently included if the conn.env exists.
# Preserves the maintainer's legacy SSHEngine workflow without erroring
# on fresh clones that don't have vista-meta installed. See
# src/m_cli/engine.py for the multi-transport resolver that picks
# Local / Docker / SSH at runtime.
VISTA_CONN := $(HOME)/data/vista-meta/conn.env
ifneq ($(wildcard $(VISTA_CONN)),)
include $(VISTA_CONN)
export VISTA_HOST VISTA_SSH_PORT VISTA_SSH_USER
export VISTA_HTTP_RPC_PORT VISTA_HTTP_FMQL_PORT VISTA_HTTP_ROCTO_PORT VISTA_HTTP_YDBGUI_PORT
endif

# m-test-engine — local checkout of m-dev-tools/m-test-engine, used by
# `make engine-up` / `engine-down` to start/stop the lightweight YDB
# container. Override if you cloned it elsewhere.
M_TEST_ENGINE ?= $(HOME)/projects/m-test-engine

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

# Whole-corpus validation gates (`vista`, `vista-canonical`, `lint-vista`)
# live in Makefile.vista — opt-in via this silent include. The targets are
# corpus-agnostic; their default corpus is $(CORPUS) (see top of file).
-include Makefile.vista

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

# ── Engine lifecycle (m-test-engine container) ──────────────────────
#
# `engine-up` starts the lightweight YDB container so DockerEngine can
# target it. m-cli's detect_engine() picks up the running container
# automatically. Force the choice with `M_CLI_ENGINE=docker m test`.
#
# `engine-status` shows which transport detect_engine() resolves to
# given the current environment (env vars, conn.env, running container).

engine-up:
	@if [ -d "$(M_TEST_ENGINE)" ]; then \
	    $(MAKE) -C $(M_TEST_ENGINE) up; \
	else \
	    echo "m-test-engine not found at $(M_TEST_ENGINE)."; \
	    echo "Clone it: git clone https://github.com/m-dev-tools/m-test-engine $(M_TEST_ENGINE)"; \
	    echo "Or override: make engine-up M_TEST_ENGINE=/elsewhere"; \
	    exit 1; \
	fi

engine-down:
	@$(MAKE) -C $(M_TEST_ENGINE) down

engine-status:
	@$(PYTHON) -c "from m_cli.engine import detect_engine; e = detect_engine(); print(f'transport: {type(e).__name__}'); print(f'detail: {e!r}')" \
	  || echo "(no engine resolved — see error above; install YDB locally, run \`make engine-up\`, or set up vista-meta)"

# ── Shared vista-meta engine (legacy SSHEngine path) ────────────────
seed:
	@./scripts/seed-vista.sh

unseed:
	@./scripts/unseed-vista.sh

test-vista: seed
	@$(PYTEST) -m vista || (rc=$$?; $(MAKE) unseed; exit $$rc)
	@$(MAKE) unseed
