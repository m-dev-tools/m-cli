.PHONY: install bootstrap test test-lf watch lint format mypy cov check lint-modern lint-modern-baseline lint-modern-setup push pull hooks seed unseed test-vista engine-up engine-down engine-status manifest check-manifest check-docs-prose scope-check

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
PTW    := .venv/bin/ptw
RUFF   := .venv/bin/ruff
MYPY   := .venv/bin/mypy
M      := .venv/bin/m
PRECOMMIT := .venv/bin/pre-commit

# Sources that drive each generated dist artifact. The capabilities tree
# is built from every `cli.py` under src/m_cli/ (one per subcommand
# package, plus the dispatcher itself), so any change there should
# regenerate dist/commands.json.
CLI_SOURCES := $(shell find src/m_cli -name cli.py -type f) src/m_cli/cli.py
LINT_SOURCES := $(shell find src/m_cli/lint -name '*.py' -type f) src/m_cli/lint/list_rules.py
FMT_SOURCES  := $(shell find src/m_cli/fmt  -name '*.py' -type f)

# Default corpus for whole-corpus validation gates (round-trip, canonical,
# lint). Override per-invocation: `make vista CORPUS=/path/to/other/corpus`,
# or via environment: `CORPUS=... make vista`. Defaults to the in-org
# m-modern-corpus so gates work on a fresh clone without VistA access.
CORPUS ?= $(HOME)/m-dev-tools/m-modern-corpus

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
M_TEST_ENGINE ?= $(HOME)/m-dev-tools/m-test-engine

install:
	uv sync --extra dev
	$(MAKE) hooks

# ── Bootstrap: one-shot turnkey install for fresh checkouts ─────────
#
# Assumes cwd is m-cli root and that git/docker/python3.12/uv/make
# are already installed (the `setup.sh` script in m-dev-tools/.github
# wraps this with OS-aware pre-flight checks; this target is the
# inside-m-cli half of that flow).
#
# Steps:
#   1. Clone the 3 sibling repos m-cli depends on / works with
#      (tree-sitter-m, m-standard, m-stdlib). Idempotent — skips
#      anything already cloned.
#   2. `make install` — uv sync the venv + pre-commit hooks.
#   3. `m engine install` + `m engine start` — pull and run the
#      m-test-engine Docker container.
#   4. `m doctor` — verify everything is green.
bootstrap:
	@echo ">>> Cloning sibling repos under $$(dirname $$PWD)..."
	@cd .. && for r in tree-sitter-m m-standard m-stdlib; do \
	  if [ -d "$$r/.git" ]; then \
	    echo "    $$r already cloned — skipping"; \
	  else \
	    echo "    cloning $$r..."; \
	    git clone "https://github.com/m-dev-tools/$$r" || exit 1; \
	  fi; \
	done
	@echo ""
	@echo ">>> Installing m-cli into .venv..."
	@$(MAKE) install
	@echo ""
	@echo ">>> Bringing up m-test-engine..."
	@$(M) engine install
	@$(M) engine start
	@echo ""
	@echo ">>> Verifying with m doctor..."
	@$(M) doctor
	@echo ""
	@echo ">>> Bootstrap complete."
	@echo "    PATH suggestion (paste into ~/.bashrc or ~/.zshrc):"
	@echo "      export PATH=\"$$PWD/.venv/bin:\$$PATH\""
	@echo "    Then start with the walkthrough:"
	@echo "      $$PWD/docs/m-cli-tdd-lifecycle-walkthrough.md"

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
# at $$HOME/m-dev-tools/m-modern-corpus/ (set up via `make lint-modern-setup`)
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

# ── Tier-1 manifest artifacts (Phase 0 / Track D) ────────────────────
#
# `make manifest` regenerates every machine-readable view exposed by
# dist/repo.meta.json. Each artifact is derived from a live registry —
# capabilities from the argparse parser tree, lint-rules / fmt-rules
# from the in-process Rule / FmtRule registries — so there is nothing
# to hand-curate.
#
# `make check-manifest` is the drift gate: it regenerates everything
# and asserts the working tree is clean. CI runs this on every push.

dist/commands.json: $(CLI_SOURCES)
	@mkdir -p dist
	$(M) capabilities --json > $@

dist/lint-rules.json: $(LINT_SOURCES)
	@mkdir -p dist
	$(M) lint --list-rules --json > $@

dist/fmt-rules.json: $(FMT_SOURCES)
	@mkdir -p dist
	$(M) fmt --list-rules --json > $@

# Vendored from m-dev-tools/m-test-engine. The source of truth is
# $(M_TEST_ENGINE)/dist/m-test-engine.json — copied here at release
# time so a fresh `pip install m-cli` carries the engine contract
# without needing network access. The drift gate (`git diff --exit-code
# dist/` below) catches missed re-vendoring after an upstream bump.
#
# If M_TEST_ENGINE is not a local checkout, the rule is a no-op — the
# vendored copy already in git is treated as authoritative.
M_TE_MANIFEST := $(wildcard $(M_TEST_ENGINE)/dist/m-test-engine.json)
ifneq ($(M_TE_MANIFEST),)
dist/m-test-engine.json: $(M_TE_MANIFEST)
	@mkdir -p dist
	cp $< $@
	@echo "vendored dist/m-test-engine.json from $(M_TEST_ENGINE)"
endif

manifest: dist/commands.json dist/lint-rules.json dist/fmt-rules.json dist/m-test-engine.json

check-manifest: manifest
	git diff --exit-code dist/



pull:
	git pull origin main

push: check
	git push origin main

# ── Multi-repo scope check ──────────────────────────────────────────
#
# Workspace-wide sanity check before committing. Warns if any sibling
# repo under ~/m-dev-tools/ has pending changes that this session may
# have leaked into, or that another parallel session left dirty. See
# .github/docs/dev-practices/parallel-multi-repo-git-hygiene.md.
.PHONY: scope-check
scope-check:
	@bad=0; \
	for r in $(HOME)/m-dev-tools/m-* $(HOME)/m-dev-tools/tree-sitter-* $(HOME)/m-dev-tools/.github; do \
	  [ -d "$$r/.git" ] || continue; \
	  case "$$(realpath $$r)" in "$(CURDIR)") continue;; esac; \
	  out=$$(git -C "$$r" status --porcelain 2>/dev/null); \
	  if [ -n "$$out" ]; then \
	    echo "PENDING in $$(basename $$r):"; \
	    echo "$$out" | sed 's/^/    /'; \
	    bad=1; \
	  fi; \
	done; \
	if [ $$bad -eq 1 ]; then \
	  echo ""; \
	  echo "A sibling repo has uncommitted edits."; \
	  echo "Confirm those edits are intentional (and owned by a different session)"; \
	  echo "before committing here. See .github/docs/dev-practices/."; \
	fi; \
	echo ""; echo "THIS repo ($(notdir $(CURDIR))):"; \
	git status --porcelain | sed 's/^/    /' || true

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

# Guardrail: docs/ holds only human-readable prose. Non-prose artifacts
# (generated data, JSON/TSV output, copy-paste examples, scaffolding
# templates) belong under dist/, examples/, templates/, or a top-level
# domain-specific directory — not docs/.
check-docs-prose:
	@if [ ! -d docs ]; then echo "check-docs-prose: no docs/ directory ✓"; exit 0; fi; \
	violations=$$(find docs -type f \
	    ! -name '*.md' ! -name '*.markdown' \
	    ! -name '*.png' ! -name '*.jpg' ! -name '*.jpeg' \
	    ! -name '*.gif' ! -name '*.svg' ! -name '*.webp' \
	    ! -name '.gitkeep'); \
	if [ -n "$$violations" ]; then \
	  echo "ERROR: non-prose files under docs/ — move to dist/, examples/, templates/, or a top-level domain dir:" >&2; \
	  echo "$$violations" >&2; \
	  exit 1; \
	fi; \
	echo "check-docs-prose: docs/ is prose-only ✓"
