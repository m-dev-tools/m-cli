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
| 2 | `m lint --rules=xindex` | **37 of XINDEX's 66 rules.** Latest: M-XINDX-057 (lower/mixed case local variable, SAC §3.6). VistA: 64,195 findings / 42 fatal. 22.6 s on 16 cores (5.3× under §3.5 budget). |
| 3 | `m test` | **Shipped.** Parser-aware discovery (`*TST.m` files, `t<UpperCase>(pass,fail)` labels via tree-sitter); ydb runner; text / TAP / JSON output; whole-suite, single-suite, single-label runs. Smoke gate: 11 m-tools suites / 224 assertions pass. |
| 4 | Single-test selection | **Shipped** as part of Step 3 (`m test FILE.m::tLabel`). |
| 5 | `m watch` | **Shipped.** Polling-based file watcher (default 0.5 s); on `*.m` save → re-run affected suites. Affinity: `foo.m` → `FOOTST.m`; suite-file edits re-run only that suite; non-mappable changes re-run all. `--once` runs the initial pass and exits. |

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
├── lint/
│   ├── cli.py              # `m lint` argparse (--rules, --format, --error-on)
│   ├── runner.py           # select_rules(), lint_source() with rule isolation
│   ├── rules.py            # all M-XINDX-NN rule implementations + register()
│   ├── diagnostic.py       # Diagnostic dataclass + Severity enum
│   ├── output.py           # text / json / tap formatters
│   └── _keywords.py        # loads command/ISV/function sets from m-standard
├── test/
│   ├── cli.py              # `m test` argparse (--list, --filter, --format)
│   ├── discovery.py        # tree-sitter-based suite + label discovery
│   ├── runner.py           # ydb subprocess + TESTRUN output parser
│   └── output.py           # text / tap / json formatters
└── watch/
    ├── cli.py              # `m watch` argparse (--interval, --once, --filter)
    ├── affinity.py         # changed-file → suite resolution (FOO.m → FOOTST.m)
    └── poller.py           # mtime-based change detection (no external deps)

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

## Test-runner conventions (project-specific)

- **Discovery is parser-aware.** Suites are `.m` files whose stem matches `[A-Z][A-Z0-9]*TST`; test labels match `t[A-Z]…` and have formals `(pass,fail)`. The first label in a file (the routine entry) is never a test, even if it accidentally matches.
- **Runner is YottaDB-specific.** Whole-suite runs use `ydb -run ^SUITE`; single-label runs use `ydb -run %XCMD "new pass,fail … do tCase^SUITE(.pass,.fail) … do report^TESTRUN"`. The runner shells out via an injectable `RunnerFn` so unit tests don't need a live ydb.
- **Output dialects.** `text` (default, human), `tap` (TAP v13 — one point per parsed assertion), `json` (CI-friendly). All three are smoke-tested against m-tools suites.
- **Env composition.** `m_cli.test.runner._build_env` honours an existing `ydb_routines` if exported; otherwise it derives one from the suite's parent dir + a sibling `routines/` if present. `$YDB` overrides binary location, falling back to `$ydb_dist/ydb`, then plain `ydb` on PATH.
- **TESTRUN protocol.** Output parser keys off `  PASS  desc` / `  FAIL  desc` / `         expected: …` / `         actual:   …` and the `Results: N tests  P passed  F failed` summary, plus the `All tests passed.` / `<n> test(s) FAILED.` banner. Source of truth: `m-tools/routines/tests/TESTRUN.m`.

## Watch conventions (project-specific)

- **Polling, not inotify.** `m watch` uses periodic `os.stat` (default 0.5 s) — keeps deps minimal at the cost of latency. Pure-Python; no `watchdog` / `entr` / `inotify` dependency.
- **Affinity rule.** `<X>.m` source change → suite `<X.upper()>TST.m` if it exists; otherwise every suite re-runs (defensive default). Suite-file edits map to themselves only.
- **Discovery dedup.** When the user passes overlapping paths (e.g. `routines/` and `routines/tests/`), each suite is discovered once. The dedup is via `Path.resolve()` so symlinks count as the same file.
- **`--once`.** Runs the initial pass and exits — used by tests and as a manual smoke check before starting a long-running watch session.

## Linter conventions (project-specific)

- **Rule IDs:** `M-XINDX-NN` mirrors XINDEX's numeric error codes 1:1. When porting a new rule, use the same number.
- **Keyword sets:** never hardcode command/ISV/function lists in `rules.py`. Use `_keywords.py` (`standard_commands()`, `standard_isvs()`, `standard_functions()`), which loads from m-standard's TSVs with ANSI fallback.
- **Severity:** FATAL / STANDARD / WARNING / INFO map to XINDEX's F / S / W / I.
- **Per-rule isolation:** `runner.lint_source` wraps each rule in try/except so one buggy rule can't crash a lint pass — it emits an `M-INTERNAL-RULE-CRASH` diagnostic instead.
- **VistA is the gate:** every rule should be sanity-checked with `make lint-vista` to catch wild-corpus surprises before commit.

## Performance status — under budget

The lint perf budget (120 s for the full VistA corpus per §3.5) is met with comfortable headroom:

- **Single-pass dispatcher.** `m_cli.lint._index.NodeIndex` walks each parse tree exactly once and groups nodes by `node.type`; rules consume `index.of("X")` instead of running their own `_walk(tree.root_node)`. Cut serial lint time from ~1458 s to 166 s (**8.7×**).
- **Multiprocessing.** `m lint --jobs N` (default `os.cpu_count()`) runs `lint_source` in a `ProcessPoolExecutor`. Each routine is independent. On a 16-core host the full VistA corpus lints in **22.6 s** — **5.3× under budget**, **64.5× faster than the original**.
- Findings byte-identical at every step (62,806 total / 42 fatal / 24,877 flagged).

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
