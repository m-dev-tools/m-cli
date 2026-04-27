# m-cli — Claude Project Context

## What this project is

`m-cli` is the canonical implementation of the **`m <subcommand>`** CLI for the M (MUMPS) language — the Tier 1 deliverable from `~/projects/m-tools/docs/m-tooling-tier1.md`. It replaces the legacy `y*` shell scripts in `~/projects/m-tools/bin/`, which are kept only as references and templates. Source-level tools (`m fmt`, `m lint`) are engine-neutral; runtime tools (`m test`, coverage, trace) target YottaDB primarily.

**Foundations:**
- [`tree-sitter-m`](https://github.com/rafael5/tree-sitter-m) — parser (99.06% clean on VistA's 39,330 routines)
- [`m-standard`](https://github.com/rafael5/m-standard) — language reference; commands/ISVs/functions are loaded from its TSVs via `src/m_cli/lint/_keywords.py`
- VistA at `~/vista-meta/vista/vista-m-host/Packages` (39,330 .m files) — the validation gate via `make vista` and `make lint-vista`

## Current state (2026-04-27)

| Step | Tool | Status |
|------|------|--------|
| 1 | `m fmt` | **Shipped.** Identity round-trip; 99.04% (38,954/39,330) byte-for-byte; ~26 s |
| 2 | `m lint --rules=xindex` | **Step 2.1 shipped.** 36 of XINDEX's 66 rules; 28 fire on VistA → 62,806 findings across 24,877 routines (63.9%); 42 fatal call-to-missing-label findings are real bugs |
| 3 | `m test` | **Next.** Parser-aware port of legacy `ytest` |
| 4 | Single-test selection | Folded into Step 3 |
| 5 | `m watch` | Planned |

See [`TODO.md`](TODO.md) for the punch list to pick up from.

## Dev workflow
```bash
make install    # uv sync --extra dev + pre-commit hooks
make test       # pytest — stops at first failure, random order
make test-lf    # rerun only last-failed tests
make watch      # TDD mode: auto-rerun on save
make lint       # ruff check
make mypy       # mypy src/
make cov        # pytest --cov
make check      # lint + mypy + cov (full CI gate)
make format     # ruff format
make vista      # full VistA round-trip gate for `m fmt` (39,330 routines)
make lint-vista # full VistA lint baseline for `m lint --rules=xindex`
```

## Environment
- Python 3.12, managed via `uv`
- Virtual env: `.venv/` (auto-activated via direnv + `.envrc`)
- Deps declared in `pyproject.toml`; lockfile `uv.lock` — commit both together
- Local-only git repo (no remote) — pushing is not currently configured

## Project structure
```
src/m_cli/
├── cli.py                  # `m` dispatcher (argparse subcommands)
├── parser.py               # tree-sitter-m wrapper, lru_cached Language/Parser
├── fmt/
│   ├── cli.py              # `m fmt` argparse + file orchestration
│   └── formatter.py        # round-trip pretty-printer (identity for now)
└── lint/
    ├── cli.py              # `m lint` argparse (--rules, --format, --error-on)
    ├── runner.py           # select_rules(), lint_source() with rule isolation
    ├── rules.py            # all M-XINDX-NN rule implementations + register()
    ├── diagnostic.py       # Diagnostic dataclass + Severity enum
    ├── output.py           # text / json / tap formatters
    └── _keywords.py        # loads command/ISV/function sets from m-standard

tests/                      # one test file per source module
scripts/
├── vista_round_trip.py     # `make vista` driver
└── vista_lint.py           # `make lint-vista` driver
```

## Testing conventions
- Write the test first (TDD) — confirm RED, then implement to GREEN
- Tests live in `tests/`, one file per source module
- `conftest.py` handles sys.path — no install needed to run tests
- Coverage minimum enforced in `make check`

## Code style
- Formatter + linter: `ruff` only (no black)
- Line length: 88
- Pre-commit hooks enforce style on every commit
- All Makefile targets use `.venv/bin/` prefixes — never bare `python`/`pytest`/`ruff`/`mypy`

## Linter conventions (project-specific)

- **Rule IDs:** `M-XINDX-NN` mirrors XINDEX's numeric error codes 1:1. When porting a new rule, use the same number.
- **Keyword sets:** never hardcode command/ISV/function lists in `rules.py`. Use `_keywords.py` (`standard_commands()`, `standard_isvs()`, `standard_functions()`), which loads from m-standard's TSVs with ANSI fallback.
- **Severity:** FATAL / STANDARD / WARNING / INFO map to XINDEX's F / S / W / I.
- **Per-rule isolation:** `runner.lint_source` wraps each rule in try/except so one buggy rule can't crash a lint pass — it emits an `M-INTERNAL-RULE-CRASH` diagnostic instead.
- **VistA is the gate:** every rule should be sanity-checked with `make lint-vista` to catch wild-corpus surprises before commit.

## Performance status (known follow-up)

`m lint` over the VistA corpus runs in ~1458 s with 36 rules — **12× over the §3.5 budget of 120 s**. Each new rule is currently a separate AST walk. Optimisation work (parallelism via multiprocessing on routines, single-pass rule scheduling, selective rule activation by node type) is sequenced **after** XINDEX rule-set parity. **Correctness first.**

## Git conventions
- Main branch: `master` (this repo) — note this differs from `main` elsewhere
- Pre-push hook runs `pytest` — push fails if tests fail
- `make push` runs full `check` before pushing (no remote configured yet — push is a no-op)
- Commit messages: descriptive, multi-line; recent style is `Tier 1 Step N.M: <what shipped>` for milestone commits

## Claude guidelines
- Prefer editing existing files over creating new ones
- Keep rules small and independently testable; one rule per module-level `register(Rule(...))` block
- Use `logging` not `print()` in library code
- No mocks unless unavoidable — fixtures are real .m source strings
- This is a small focused project — keep solutions simple and direct
- The `m <subcommand>` naming convention is universal — do NOT introduce `y*` names for new tools
