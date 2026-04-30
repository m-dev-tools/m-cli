# m-cli — Claude Project Context

## What this project is

`m-cli` is the canonical implementation of the **`m <subcommand>`** CLI for the M (MUMPS) language — the Tier 1 deliverable from `~/projects/m-tools/docs/m-tooling-tier1.md`. It replaces the legacy `y*` shell scripts in `~/projects/m-tools/bin/`, which are kept only as references and templates. Source-level tools (`m fmt`, `m lint`) are engine-neutral; runtime tools (`m test`, coverage, trace) target YottaDB primarily.

**Foundations:**
- [`tree-sitter-m`](https://github.com/rafael5/tree-sitter-m) — parser (99.06% clean on VistA's 39,330 routines)
- [`m-standard`](https://github.com/rafael5/m-standard) — language reference; commands/ISVs/functions are loaded from its TSVs via `src/m_cli/lint/_keywords.py`
- VistA at `~/vista-meta/vista/vista-m-host/Packages` (39,330 .m files) — the validation gate via `make vista` and `make lint-vista`

## Current state (2026-04-28)

### Tier 1 — DONE

All five Tier 1 capabilities from [m-tooling-tier1.md](../m-tools/docs/m-tooling-tier1.md) ship; all four §3.5 validation gates pass (VistA round-trip, single-engine smoke, CI dogfooding, performance under budget). See [docs/guide.md §3.2](docs/guide.md#32-coverage-matrix) for the full coverage matrix.

| Step | Tool | Status |
|------|------|--------|
| 1 | `m fmt` | **Done + Phase A translation.** Identity (default) round-trips 99.04% byte-for-byte. `--rules=canonical` adds trim-trailing-whitespace + uppercase-command-keywords; idempotent + AST-preserving over 38,954 VistA routines. **Phase A translation rules** (`--rules=pythonic` / `--rules=pythonic-lower` / `--rules=compact`) translate between VistA-compact (`S X=1 W $L(X),$T`) and canonical-name (`SET X=1 WRITE $LENGTH(X),$TEST`) or lowercase canonical (`set X=1 write $length(X),$test`) for Python-style readability. 9 case-preserving rules + 3 presets; idempotent normalizers (mixed-form input collapses to one canonical form). |
| 2 | `m lint` | **Done (breadth-first) + cross-routine + control-flow + M-MOD modernization track + profile split.** Engine- and dialect-neutral lint engine; opinionated rule sets ship as named **profiles** (`default`/26, `modern`/30, `pedantic`/4, `xindex`/34, `vista`/8, `sac`/23, `all`/72) registered in `m_cli.lint.profiles`. **`default` is now the curated daily-lint subset of M-MOD** (the 4 pedantic rules — M-MOD-009/028/031/032 — that fire 90% of noise on real M code are split into a separate `pedantic` profile, opt-in via `--rules=modern` for the strict review pass). VA shops use `--rules=xindex` (engine-neutral XINDEX) or `--rules=xindex,vista`. The 42 XINDEX-derived rules cover legacy VA conventions; M-MOD-001..035 (24 shipped) cover modern idioms across length/complexity, concurrency, transactions, control-flow correctness, engine-aware portability, docs/style polish. Validation on a 4K-routine non-VA corpus: `default` produces 2,912 findings (3.3/routine — usable daily), `modern` produces 50,284 (mostly from the pedantic style rules). M-MOD-017/024–027/036 deferred to Phase 7 (data-flow infra). VistA legacy gate 22.6 s on 16 cores. |
| 3 | `m test` | **Done.** Parser-aware discovery; ydb runner; text / TAP / JSON output. Smoke gate: 11 m-tools suites / 224 assertions pass. |
| 4 | Single-test selection | **Done** as part of Step 3 (`m test FILE.m::tLabel`). |
| 5 | `m watch` | **Done.** Polling-based file watcher; source→suite affinity. |

### Tier 2 — IN PROGRESS

Per [m-tool-gap-analysis.md §8](../m-tools/docs/m-tool-gap-analysis.md#8-rank-ordered-developer-impact-where-to-invest-first), Tier 2 = quality gates and team scaling. Five categories (rank 6–10):

| # | Tier 2 capability | Status | Implementation |
|---|---|:---:|---|
| 6 | CI script | 🟡 Partial | Project Makefile + pre-commit scaffold. No dedicated `m ci` planned yet. |
| 7 | **Coverage** | ✅ Done | `m coverage` — Phase C. Runner uses YDB's built-in `view "TRACE"` (one trace pass replaces N ZBREAKs per label). Trace third-subscript decoded: offset N from a label maps to absolute line `label_decl_line + N`, so per-line hit counts are now precise. Label-level holds 85/123 = 69.1% on m-tools (byte-identical to ycover); line-level on m-tools is 340/637 (53.4%). Output formats: `text` (default), `text --lines` (per-routine label + line columns), `json`, `lcov` (genhtml / Codecov / Coveralls compatible). |
| 8 | Linter (style) | ✅ Done | Style rules ride alongside logic rules in `m lint`; `--rules=sac` for SAC-tagged subset; severity overrides via config. |
| 9 | Pre-commit hooks | ✅ Done | `.pre-commit-hooks.yaml` exposes `m-fmt-check`, `m-fmt`, `m-lint`. |
| 10 | Debugger | ⏸️ Deferred | DAP integration is its own engineering project; both engines ship `ZBREAK` at the engine level. Not on near-term roadmap. |

### Cross-cutting (post-Tier-1, layered on the same foundation)

- **`m lsp` Stages 1+2+3+4+4b+B** — diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, **find-references, workspace symbol search, incremental index updates** (didChangeWatchedFiles + didSave). Editor design decision per [m-tooling-tier1.md §5.4](../m-tools/docs/m-tooling-tier1.md#54-editor-integration-cadence).
- **VS Code wiring** — sibling repo `tree-sitter-m-vscode` spawns `m lsp` and registers the `m-cli.runTest` command for code-lens click-to-run.
- **Phase A — project config** (`.m-cli.toml` / `[tool.m-cli]`): drives lint / fmt / lsp.
- **Phase B — workspace symbol index** (full slice): the `WorkspaceIndex` indexes both labels (declarations) and inbound `entry_reference` / `extrinsic_function` call sites. Backs `textDocument/definition`, `textDocument/references`, `workspace/symbol`. Stays fresh via `didChangeWatchedFiles` (file-system events) + `didSave` (in-editor saves). Cross-routine lint rules (M-XINDX-004 et al.) are the next consumer of the same index.

See [`TODO.md`](TODO.md) for the punch list to pick up from, and [docs/guide.md](docs/guide.md) for the comprehensive guide.

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
make vista          # full VistA round-trip gate for `m fmt` (identity)
make vista-canonical # full VistA canonical-layout gate (idempotency + AST shape)
make lint-vista     # full VistA lint baseline (xindex + vista profiles)
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
│   ├── cli.py              # `m lint` argparse (--rules, --format, --error-on, --list-profiles, --threshold, --target-engine)
│   ├── runner.py           # select_rules(), lint_source() with rule isolation
│   ├── profiles.py         # Profile registry (default, xindex, vista, sac, modern, all) — design separation point
│   ├── rules.py            # XINDEX rule implementations + Rule/register()
│   ├── _modern.py          # M-MOD-NN rule implementations (greenfield track)
│   ├── context.py          # LintContext — thresholds + target engine + workspace + config
│   ├── thresholds.py       # KNOWN_THRESHOLDS defaults + validate()
│   ├── diagnostic.py       # Diagnostic dataclass + Severity + Category enums (engine-neutral)
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

## Formatter conventions (project-specific)

- **Rule-selector forms.** `--rules=canonical` (SAC hygiene: trim-trailing-whitespace + uppercase-command-keywords) is the default opt-in; `--rules=pythonic`, `--rules=pythonic-lower`, and `--rules=compact` are the Phase A translation presets. `--rules=all` returns *every* registered rule and is **diagnostic-only** — never use it as a formatter pipeline because `expand-*` / `compact-*` / `uppercase-*` / `lowercase-*` rules race when applied together. `--rules=none` (or omitting the flag) is identity.
- **Phase A translation rules.** Six AST-preserving, case-preserving, idempotent expand/compact rules ride alongside the canonical hygiene rules: `expand-command-keywords` (`S→SET`), `compact-command-keywords` (`SET→S`), `expand-intrinsic-functions` (`$L→$LENGTH`), `compact-intrinsic-functions`, `expand-special-variables` (`$T→$TEST`), `compact-special-variables`. Each walks the parse tree, finds nodes of one type (`command_keyword` / `intrinsic_function_keyword` / `special_variable_keyword`), looks up the uppercase token in m-standard's abbrev↔canonical map, applies edits right-to-left. The maps are built lazily from `keyword_records()` and lru-cached.
- **Case-folding rules.** Three companion rules force a single case across every node of the relevant type (regardless of canonical/abbrev): `lowercase-command-keywords`, `lowercase-intrinsic-functions`, `lowercase-special-variables`. They share the engine `_rewrite_node_case(src, node_type, transform)` with `uppercase-command-keywords`. Used by the `pythonic-lower` preset to produce all-lowercase output (`set X=1 write $length(X),$test`) for Python-influenced projects. The lowercase rules must run *before* the expand rules in the pipeline so that case-preserving expand sees a lowercase abbreviation and emits a lowercase canonical.
- **Case preservation (in expand/compact).** All-lowercase reference (`s`) → all-lowercase replacement (`set`). Anything else (`S`, `Set`, `SET`) → uppercase replacement. The unusual mixed-case form is rare in M and unlikely deliberate, so we don't try to mirror it.
- **Translation is *normalizing*, not *invertible*.** Mixed-form input (some `NEW`, some `N`) collapses to one form. The round-trip property holds on already-normalized input only: `compact(pythonic(compact(src))) == compact(src)`. This is the intended behavior.
- **Why no operator spacing or one-command-per-line.** PEP-8-style `S X = 1` breaks the M parser (whitespace is M's argument terminator). Statement splitting (one command per line) violates the AST-shape-preservation contract. Both are out of scope for fmt rules; the lint rule `M-MOD-009` flags multi-command lines for manual fix.

## Linter conventions (project-specific)

- **Engine vs profiles — design separation.** The lint engine (`runner`, `rules`, `diagnostic`) is engine- and dialect-neutral. Opinionated rule sets ride on top as named **profiles** registered in [src/m_cli/lint/profiles.py](src/m_cli/lint/profiles.py). XINDEX is *one profile*, not the canonical baseline. New rule families (IRIS-style, ANSI-strict, YDB-best-practice, ...) get their own profile and ID prefix; they do not need to be tagged `xindex`.
- **Tags = provenance + policy.** Two distinct concerns ride on the rule's `tags` tuple. `xindex` is *provenance* — the rule was ported from VA's `^XINDEX` scanner. `sac` is *policy* — the rule maps to a documented section of the VA SAC (Standards & Conventions). Most rules carry both because XINDEX was VA's automated SAC checker, but the sets are not identical: 31 of m-cli's 42 XINDEX-ported rules are also SAC-tagged; the other 11 (parse errors, dead-code, missing-label, hygiene, etc.) are XINDEX-internal smells with no SAC mandate. The classification is pinned by `tests/test_lint_profiles.py::TestSacClassification` and the rationale lives in [src/m_cli/lint/rules.py](src/m_cli/lint/rules.py) module docstring.
- **Rule IDs:** `M-XINDX-NN` mirrors XINDEX's numeric error codes 1:1 — use the same number when porting an XINDEX rule. `M-MOD-NN` is the greenfield modernization track (engine- and dialect-neutral, derived from contemporary M idioms; see [docs/m-linting-survey.md](docs/m-linting-survey.md) §7). When an `M-MOD` rule supersedes an `M-XINDX` rule, declare the relationship via `Rule.replaces=("M-XINDX-NN", ...)`. Future engine- or standard-specific prefixes (`M-IRIS-NN`, `M-YDB-NN`, `M-ANSI-NN`) ship under their own profile and tag.
- **Engine targeting:** `[lint] target_engine = "yottadb" | "iris" | "any"` in `.m-cli.toml`, or `--target-engine`. Default `any` keeps the linter portable; the named engines unlock engine-aware rules ($Z* allowlists, Z-command sets) once those rules ship.
- **Configurable thresholds:** `[lint.thresholds]` config table or `--threshold KEY=VAL` CLI flag (repeatable). Known keys: `line_length` (200), `code_line_length` (1000), `routine_lines` (1000), `label_lines` (50), `cyclomatic` (15), `cognitive` (20), `dot_block_depth` (5), `argument_count` (7), `commands_per_line` (3), `comment_density_pct` (10). Defaults live in [src/m_cli/lint/thresholds.py](src/m_cli/lint/thresholds.py); unknown keys are rejected at config-load time (catches typos).
- **`LintContext` (single dispatch path):** Rules opt into a richer signature via `needs_context=True` and receive a `LintContext` carrying `thresholds`, `target_engine`, `workspace`, and `config`. Replaces the legacy `needs_workspace` flag — cross-routine rules now read `ctx.workspace`. Built once at lint-command entry and threaded through to every context-aware rule.
- **Wild-corpus gates:** `make lint-vista` over the full VistA corpus is the regression gate for VA-flavoured rules (`xindex`, `vista` profiles). The non-VistA, post-2010, *pure-`.m`* corpora catalogued in [docs/m-corpus-catalog.md](docs/m-corpus-catalog.md) (anchored on `YottaDB/YDBTest`, `chrisemunt/mgsql`, `YottaDB/YDBOcto src/aux/`) seed the future `make lint-modern` gate for `M-MOD-NN` rules. **`.cls` files are out of scope** — ObjectScript class definitions are a superset of MUMPS that `tree-sitter-m` does not parse; the substantial InterSystems `.cls` corpora (ipm, isc-rest, isc-codetidy, etc.) become candidates only if a `tree-sitter-objectscript` ships.
- **Default profile:** `default` is the **curated M-MOD daily-lint subset** (26 rules) — the M-MOD-NN modernization track *minus* the four pedantic style rules (M-MOD-009 commands-per-line, M-MOD-028 label-docstring, M-MOD-031 magic-numbers, M-MOD-032 single-letter-vars) which fire ~90% of noise on real M code. The full M-MOD set is opt-in via `--rules=modern`; the pedantic-only view via `--rules=pedantic`. VA shops use `--rules=xindex` (engine-neutral legacy XINDEX) or `--rules=xindex,vista` for the full VistA-flavoured rule set. Python-influenced developers get `--rules=pythonic` (same rules as `modern` plus tighter thresholds: `line_length=100`, `commands_per_line=1`, `cyclomatic=10`, etc.). The default change from "engine-neutral XINDEX" to "curated M-MOD" was driven by the modern-corpus validation finding that XINDEX legacy rules generate ~62K findings on a non-VA modern corpus (mostly from SAC mandates around lowercase variables/commands that aren't followed in non-VA code).
- **Profile presets:** Profiles can bundle threshold defaults via `Profile.default_thresholds`. The `pythonic` profile is the only one that uses this today. Threshold resolution layers profile preset → `[lint.thresholds]` config → `--threshold KEY=VAL` CLI (CLI wins). Other profiles (`default`, `modern`, `xindex`, etc.) carry empty `default_thresholds` and rely on the system-wide defaults in `m_cli.lint.thresholds.KNOWN_THRESHOLDS`.
- **Keyword sets:** never hardcode command/ISV/function lists in `rules.py`. Use `_keywords.py` (`standard_commands()`, `standard_isvs()`, `standard_functions()`), which loads from m-standard's TSVs with ANSI fallback.
- **Severity (actionability):** ERROR (must fix; CI fails) · WARNING (should fix) · STYLE (auto-fix preferred; LSP `Hint`) · INFO (informational; no action). The dividing line between actionable and not is `Severity.is_actionable` — only INFO is not. Compact summary uses E/W/S/I letters.
- **Category (kind, orthogonal to severity):** `bug` · `security` · `concurrency` · `performance` · `style` · `complexity` · `documentation` · `portability` · `modernization`. Every Rule declares both severity AND category at registration. Filter by either dimension.
- **Per-rule isolation:** `runner.lint_source` wraps each rule in try/except so one buggy rule can't crash a lint pass — it emits an `M-INTERNAL-RULE-CRASH` diagnostic instead.
- **VistA is *a* gate, not *the* gate:** `make lint-vista` runs `xindex,vista` (both profiles) over the VistA corpus and is the wild-corpus regression check for VA-flavoured rules. The forthcoming `make lint-modern` (Phase 1B) runs the `modern` profile over the non-VistA corpora catalogued in [docs/m-corpus-catalog.md](docs/m-corpus-catalog.md).

## LSP server (Stages 1 + 2 + 3 + 4 + 4b + B)

`m lsp` starts the m-cli Language Server over stdio. Editors invoke it as a subprocess and exchange LSP messages on stdin/stdout. Optional dependency: `pip install 'm-cli[lsp]'` adds `pygls` + `lsprotocol`. The dispatcher reports a friendly install hint if a user runs `m lsp` without the extra.

**Stage 1 — diagnostics push.** Handlers: `textDocument/didOpen`, `didChange`, `didSave`, `didClose`. Open/change/save re-lint the document and push diagnostics; close clears them. Each LSP `Diagnostic` carries `code = rule_id`, `source = "m-cli"`, severity mapped from the engine-neutral four-level scheme (Fatal/Standard/Warning/Info), and `data = {"fixer_id": ...}` when the rule is auto-fixable.

**Stage 2 — formatting.** `textDocument/formatting` runs `format_source(src, rules=canonical_rules())` and returns a single `TextEdit` covering the full document. Empty list when the source is already canonical (avoids churning the editor's undo history) or has parse errors (we refuse to reformat broken code). Capability advertised as `documentFormattingProvider: True`.

**Stage 3 — code actions.** `textDocument/codeAction` reads the in-context diagnostics, groups them by `fixer_id`, and returns one Quick Fix per distinct fixer. Each action's `WorkspaceEdit` runs that single fmt rule file-wide — so two diagnostics of the same kind collapse into one click. Actions are skipped when the fixer would be a no-op or the source has parse errors. Capability advertised as `codeActionProvider: True`.

**Stage 4 — hover + completion + rule-filter override.**

- `textDocument/hover` resolves the M token under the cursor (commands, ISVs, intrinsic functions — case-insensitive, abbreviation or canonical) against m-standard's TSVs and returns Markdown with canonical name, abbreviation, syntax format, and standard status. Local labels and user routines return None — m-cli has no cross-routine symbol index. Capability advertised as `hoverProvider: True`.
- `textDocument/completion` returns the universe of M commands, ISVs, and intrinsic functions as `CompletionItem`s (kind = Keyword / Constant / Function; detail = the syntax format from m-standard). The list is `isIncomplete: false` — the set doesn't grow per-keystroke; the client filters by typed prefix. Capability advertised as `completionProvider`.
- `m lsp --rules <filter>` overrides the default `default` profile at startup. Accepts the same forms as `m lint --rules` (single profile name, comma list mixing profiles + rule IDs, e.g. `default`, `xindex,vista`, `sac,M-XINDX-013`). Wired by stashing the filter on the `LanguageServer` instance and read inside `lint_document`. The full LSP `workspace/configuration` round-trip is intentionally not implemented — the CLI flag covers the same need without async plumbing.

**Stage 4b — document structure, navigation, and per-test code lenses.**

- `textDocument/documentSymbol` emits one `SymbolKind.Function` per label, with the symbol range covering the label's body (until the next label or EOF) and the selection range covering just the name. Formals are appended to the display name (`INNER(a,b)`). Editors show this as the Outline / breadcrumbs.
- `textDocument/codeLens` emits a `▶ Run test <label>` lens above each `t<UpperCase>(pass,fail)` label discovered by `m_cli.test.discovery.find_test_cases`. The lens carries a `m-cli.runTest` command with arguments `[document_uri, label_name]`. The VS Code extension is expected to register that command and shell out to `m test FILE.m::tLabel`; editors that don't register it still show the title but the click is a no-op (intentional — non-VS Code editors get the visual breadcrumb without breakage).
- `textDocument/foldingRange` collapses (a) each multi-line label body and (b) each contiguous run of dot-block lines. Ranges carry `kind=Region`. Single-line bodies emit no fold.
- `textDocument/signatureHelp` activates inside `$FN(...)` parens (trigger chars `(` and `,`). Walks back through balanced parens to find the enclosing `(`, reads the token immediately to its left, and — if it resolves to a `kind="function"` keyword via `lookup_keyword` — returns the syntax format from m-standard as a single `SignatureInformation`. ISV-only tokens (`$JOB`) and user labels (`D MYLABEL(...)`) return None.
- `textDocument/documentHighlight` highlights every same-file occurrence of the identifier under the cursor, with strict word-boundary matching on `[A-Za-z0-9$%]`. Single-character tokens (`X`, `Y`) return None to avoid noisy matches; longer names are case-sensitive (M is case-sensitive for variables — only command/function keywords are case-insensitive).

Token resolution and keyword metadata live in `m_cli.lsp.symbols` (`token_at`, `lookup_keyword`, `all_keywords`). The structured loader is `m_cli.lint._keywords.keyword_records()`, which loads commands.tsv / intrinsic-special-variables.tsv / intrinsic-functions.tsv from m-standard. When a token (e.g. `$HOROLOG`) appears as both ISV and intrinsic function in ANSI, the function wins — that's a real ambiguity in M itself; tests pin unambiguous tokens (`$JOB` for ISV, `$LENGTH` for function).

Document-structure helpers (`m_cli.lsp.structure.find_labels`, `find_dot_blocks`) walk the tree-sitter tree once and return pure Python dataclasses. The CodeLens path reuses `m_cli.test.discovery.find_test_cases` so the LSP and the `m test` runner agree on what a test label is.

**Phase B — workspace symbol index + go-to-definition.**

- `m_cli.workspace.WorkspaceIndex` maps `routine_name (uppercased) → list[LabelLocation]` for every `.m` file in the workspace. Routine name comes from the file stem (uppercased) — same convention ydb uses, and avoids depending on the first-label-equals-routine-name M idiom.
- `build_index(roots)` walks each root for `*.m` files, parses each, and pulls every top-level `label` node. OS errors and parse errors are silently skipped — the index is best-effort. `add_file` / `remove_file` allow incremental updates from `didChangeWatchedFiles` (wiring deferred to a follow-up; rebuild-on-spawn is enough for now).
- `m_cli.workspace.reference_at(line, character)` parses the M reference under the cursor: `LABEL^ROUTINE`, `^ROUTINE`, `LABEL`, `$$LABEL^ROUTINE`, `$$LABEL`. Returns a `Reference(label, routine)` (either field optional). Cursor on the label half OR the routine half resolves the same full reference — convenient for users.
- `textDocument/definition` resolves cross-routine references against the index; label-only references (`D LBL`) fall back to a same-document scan since we can't know which other routine is meant. Capability advertised as `definitionProvider: True`.
- The index is built once at LSP startup from `Path.cwd()` (the workspace folder VS Code spawns with). Logged at INFO level so users can see how many labels were picked up. Future work: incremental `didChangeWatchedFiles` updates, `textDocument/references`, `workspace/symbol` (Ctrl+T), and cross-routine lint rules (M-XINDX-004 et al.) all reuse this index.

Testable inner helpers: `m_cli.lsp.server.lint_document`, `format_document`, `code_actions_for_uri`, `hover_at`, `completion_at`, `document_symbols_at`, `code_lenses_at`, `folding_ranges_at`, `signature_help_at`, `document_highlights_at`. Tests use a `FakeServer` stub — no pygls runtime needed.

**Editor wiring — VS Code.** `~/projects/tree-sitter-m-vscode` carries a `vscode-languageclient` integration that spawns `m lsp` on activation. Settings: `m-cli.enabled`, `m-cli.path` (defaults to `m` on PATH; set to `~/projects/m-cli/.venv/bin/m` for venv installs), `m-cli.args` (e.g. `["--rules", "all"]` to broaden diagnostics), `m-cli.trace.server`. Self-install via `npm run package` + `code --install-extension`; full instructions in that repo's `docs/lsp-setup.md`.

## Library API for tooling consumers

The LSP wrapper, IDE plugins, pre-commit integrations, and other out-of-tree tooling import a stable surface from the top-level package:

```python
from m_cli import (
    parse,                                # parse M source bytes -> Tree
    format_source, canonical_rules,       # m fmt
    select_fmt_rules, FmtRule, ParseError,
    lint_source, select_rules, Rule,      # m lint
    Diagnostic, Severity,
)
from m_cli.lint import fixer_for          # rule_id -> fmt rule id (or None)
```

Anything in `__all__` is locked: future internal refactors keep these importable. Internal helpers (rule check fns, AST walkers, registry internals) are not part of the public surface and may move. The `tests/test_library_api.py` smoke gate enforces this.

## Lint → fmt fixer linkage

Each lint `Rule` carries an optional `fixer_id` pointing to an `m fmt` rule that auto-fixes the diagnostic. Today: `M-XINDX-013 ↔ trim-trailing-whitespace` and `M-XINDX-047 ↔ uppercase-command-keywords`. The link surfaces in `--format=json` output (`"fixer_id": ...` per diagnostic) and via the `m_cli.lint.fixer_for(rule_id)` helper. The LSP wrapper uses this to expose Quick Fix code actions; new pairings are pinned by `tests/test_lint_fixer_linkage.py`.

## Project configuration (`.m-cli.toml` / `[tool.m-cli]`)

`m fmt`, `m lint`, and `m lsp` all read project config on startup. Discovery walks up from the working directory looking for `.m-cli.toml` first, then a `pyproject.toml` containing a `[tool.m-cli]` table. Walking stops at a `.git` boundary so configs in unrelated parent projects don't leak in. The LSP spawns with `cwd = workspace folder` (VS Code default), so the same lookup finds the project's config without needing the `initialize` rootUri.

Schema:

```toml
[lint]
rules = "default"              # profile name or comma-list of rule IDs
                               # (e.g. "xindex" for the VA VistA Toolkit profile)
disable = ["M-XINDX-013"]      # rule ids to skip after selection

[lint.severity]
"M-XINDX-019" = "warning"      # remap per-rule severity
                               # values: "fatal" | "standard" | "warning" | "info"

[fmt]
rules = "canonical"            # canonical, none (identity), or comma-separated rule ids
```

Resolution order: defaults → config → CLI flag (CLI always wins). Unknown keys are ignored silently to keep forward compatibility cheap. Invalid values (bad severity name, `disable` not a list) raise on load. The implementation lives in `m_cli.config` (`Config` dataclass + `find_config` + `load_config`); lint and fmt CLIs apply disable as a post-`select_rules` filter, severity overrides via `dataclasses.replace` on each `Diagnostic`. `m lsp` stashes the loaded `Config` on the `LanguageServer` instance and `lint_document` reads it on every push.

## Pre-commit integration

Downstream M projects opt into `m fmt --check` and `m lint --error-on=fatal` via the [pre-commit framework](https://pre-commit.com):

- Hook declarations live in `.pre-commit-hooks.yaml` (top-level). Three hooks: `m-fmt-check`, `m-fmt` (write), `m-lint`.
- Schema integrity is gated by `tests/test_pre_commit_hooks.py` — every hook's `entry` must invoke a real `m` subcommand, and the `files` regex must match `.m` paths.
- See `docs/pre-commit.md` for downstream usage examples (both git-repo and `language: system` styles).
- **Activation prerequisite:** the git-repo style needs `m-cli` published (and `tree-sitter-m` on PyPI or a git URL). Until then, downstream projects use the `language: system` style with a locally-installed `m`.

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
