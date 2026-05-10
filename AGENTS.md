---
# Machine-readable project descriptor.
name: m-cli
kind: [cli, lsp, lint, formatter, test-runner]
status: active
languages: [python]

runtime:
  needs:
    - python>=3.12
    - "tree-sitter-m (parser; loaded as a Python binding via path or release-wheel URL)"
    - "m-standard TSVs (commands/ISVs/functions tables) — sibling checkout"
  optional:
    - "yottadb engine for runtime tools (m test / m coverage). Auto-detected via Local → Docker (m-test-engine) → SSH (vista-meta legacy)."
    - "iris (engine-targetable via --target-engine=iris; source-only, no live engine)"
  excludes: []

distribution:
  pypi: null                                 # clone-and-install
  github: m-dev-tools/m-cli

location: ~/projects/m-cli

exposes:
  cli:
    - m fmt                                  # canonical formatter; identity / canonical / pythonic / pythonic-lower / compact rule sets
    - m lint                                 # 8 profiles (default/modern/pedantic/xindex/vista/sac/pythonic/all); M-XINDX-NN + M-MOD-NN
    - m test                                 # parser-aware discovery; ydb runner; text/TAP/JSON; --changed
    - m watch                                # polling file watcher
    - m coverage                             # YDB view "TRACE"-based; text/json/lcov; --branch; --min-percent gate
    - m lsp                                  # LSP server: diagnostics, fmt, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, find-references, workspace symbol search
    - m doc / m search / m manifest / m examples / m errors  # m-stdlib reference surface
    - m new / m run / m build / m doctor / m ci init         # project scaffolding + helpers
    - m plugins                              # list out-of-tree subcommands registered via m_cli.plugins entry-point group
  pre_commit_hooks: [m-fmt-check, m-fmt, m-lint]
  rule_packs:
    - "M-MOD-NN modernization (engine-neutral, dialect-neutral)"
    - "M-XINDX-NN — engine-neutral subset of the VA Toolkit XINDEX rule set"
    - "vista profile — VA-Kernel-specific rules (opt-in)"
    - "sac profile — VA SAC portable subset"

consumes:
  formats: [".m"]
  upstream_data:
    - "m-standard TSVs (loaded by src/m_cli/lint/_keywords.py)"
    - "tree-sitter-m grammar (Python binding)"
    - "m-stdlib manifest (loaded by m doc / m search / m examples / m errors)"

companions:
  - project: m-standard
    relation: "input — m-cli loads commands/ISVs/functions tables from m-standard's integrated TSVs"
  - project: tree-sitter-m
    relation: "input — parser used for AST-level lint and fmt round-trip checks"
  - project: m-stdlib
    relation: "consumed — `m doc` family surfaces stdlib-manifest.json. Architectural priority: m-cli should consume m-stdlib utilities when implementing new functionality."
  - project: m-test-engine
    relation: "default Docker engine for runtime tools (`docker exec` transport)"
  - project: m-cli-extras
    relation: "out-of-tree subcommand plugins via the m_cli.plugins entry-point group"
  - project: m-modern-corpus
    relation: "validation corpus for the M-MOD-NN rule track; default CORPUS for `make vista` / `make lint-vista` regression scripts"

incompatibilities:
  - "Dialect awareness via `--target-engine=any|yottadb|iris`. GT.M deliberately excluded — won't be added."
  - "DAP debugger integration not on the roadmap — both engines provide ZBREAK at the engine level."

docs:
  primary: README.md
  guide: docs/guide.md
  linting_user_guide: docs/m-linting-user-guide.md
  plugin_contract: docs/plugin-development.md
  pre_commit: docs/pre-commit.md
  evolution: docs/evolution.md
  vista_independence: docs/vista-meta-bootstrap.md
---

# m-cli — Claude Project Context

`m-cli` is the canonical `m <subcommand>` CLI for the M (MUMPS) language —
`m fmt`, `m lint`, `m test`, `m coverage`, `m watch`, `m lsp`, `m doc`, and
project-scaffolding helpers. Source-level tools are engine-neutral; runtime
tools target YottaDB and auto-detect a transport (Local → Docker via
[m-test-engine](https://github.com/m-dev-tools/m-test-engine) → SSH legacy).

For new contributors:

- **As-is reference** — [`README.md`](README.md)
- **Deep user-facing reference** — [`docs/guide.md`](docs/guide.md)
- **History / evolution / phase tracking** — [`docs/evolution.md`](docs/evolution.md). All "Tier N", "Step N", "Phase N", performance-journey, and date-stamped milestone content lives there. Don't reintroduce it into this file.
- **VistA independence verification** — [`docs/vista-meta-bootstrap.md`](docs/vista-meta-bootstrap.md). Read once if you wonder why the repo has a `vista` lint profile / SSH transport / `make seed` target despite being engine-neutral by default.

**Foundations:**

- [`tree-sitter-m`](https://github.com/m-dev-tools/tree-sitter-m) — parser used for AST-level lint and fmt round-trip
- [`m-standard`](https://github.com/m-dev-tools/m-standard) — language reference; commands/ISVs/functions loaded from its TSVs via `src/m_cli/lint/_keywords.py`
- [`m-stdlib`](https://github.com/m-dev-tools/m-stdlib) — runtime library; the `m doc` family surfaces its manifest

---

## Setup

```bash
make install         # uv sync --extra dev + pre-commit hooks
```

Python 3.12 + `uv`. Virtual env at `.venv/` (auto-activated via direnv + `.envrc`).

## Test

```bash
make test            # pytest — stops at first failure, random order
make test-lf         # rerun only last-failed tests
make watch           # TDD mode: auto-rerun on save
```

TDD is mandatory: write the test first, confirm RED, implement to GREEN.

## Build / generate

```bash
make manifest        # rebuild every dist/*.json (commands, lint-rules, fmt-rules)
make dist/commands.json     # m capabilities --json   → dist/commands.json
make dist/lint-rules.json   # m lint --list-rules --json → dist/lint-rules.json
make dist/fmt-rules.json    # m fmt  --list-rules --json → dist/fmt-rules.json
```

`dist/repo.meta.json` is the tier-1 contract manifest, hand-authored, validated against `https://raw.githubusercontent.com/m-dev-tools/.github/main/profile/repo.meta.schema.json`.

## Verify

```bash
make check           # lint + mypy + cov (full CI gate)
make check-manifest  # regenerate dist/*.json and assert no drift vs source
m doctor             # environment self-check ($ydb_dist, parser, m-standard TSVs, ydb)
```

Matches `verification_commands` in `dist/repo.meta.json`.

## Guardrails

- Do **not** edit `dist/*.json` by hand — every file under `dist/` is regenerated by `make manifest` from the argparse / Rule / FmtRule registries. Hand edits are erased.
- Do **not** introduce `y*`-named tools; the `m <subcommand>` namespace is canonical (see `docs/evolution.md` for the y\*→m migration history).
- Do **not** bypass TDD. Write the test first; confirm RED before implementing.
- Use `.venv/bin/` prefixes in every Makefile target — never bare `python` / `pytest` / `ruff` / `mypy`. Parent direnv hijacks bare names and runs against the wrong packages.
- Library code uses `logging`, never `print()`.
- No mocks unless unavoidable — fixtures are real `.m` source strings.
- Lint and fmt rules are registered via `register(Rule(...))` / `_register(FmtRule(...))` in `src/m_cli/lint/rules.py` and `src/m_cli/fmt/rules.py`. New rules ship in their own module-level `register(...)` block; the `m capabilities` / `m lint --list-rules --json` / `m fmt --list-rules --json` outputs read from the same registries — never hand-curate the JSON.

---

## Dev workflow

```bash
make install         # uv sync --extra dev + pre-commit hooks
make test            # pytest — stops at first failure, random order
make test-lf         # rerun only last-failed tests
make watch           # TDD mode: auto-rerun on save
make lint            # ruff check
make mypy            # mypy src/
make cov             # pytest --cov
make check           # lint + mypy + cov (full CI gate)
make format          # ruff format
make push            # full check then git push
make vista           # corpus round-trip — defaults CORPUS=m-modern-corpus; override per-invocation
make vista-canonical # canonical-layout idempotency + AST-shape gate
make lint-vista      # lint baseline against the configured CORPUS
```

The `make vista*` targets are corpus-agnostic; the historical name reflects
the original calibration substrate. Default `CORPUS` is the in-org
`m-modern-corpus`, so the gates work on a fresh clone with no VistA access.

## Environment

- Python 3.12, managed via `uv`
- Virtual env: `.venv/` (auto-activated via direnv + `.envrc`)
- Deps declared in `pyproject.toml`; lockfile `uv.lock` — commit both together
- Remote: `github.com/m-dev-tools/m-cli` · default branch `main`

## Project structure

```
src/m_cli/
├── cli.py                  # `m` dispatcher (argparse subcommands)
├── parser.py               # tree-sitter-m wrapper, lru-cached Language/Parser
├── config.py               # .m-cli.toml / [tool.m-cli] loader
├── engine.py               # LocalEngine / DockerEngine / SSHEngine + detect_engine()
├── workspace.py            # cross-routine label index (definitions + refs)
├── plugins.py              # entry-point discovery for m_cli.plugins
├── fmt/
│   ├── cli.py              # `m fmt` argparse + file orchestration
│   └── formatter.py        # round-trip pretty-printer + rule pipeline
├── lint/
│   ├── cli.py              # `m lint` argparse (--rules, --format, --error-on, --threshold, --target-engine, --jobs)
│   ├── runner.py           # select_rules(), lint_source() with rule isolation
│   ├── profiles.py         # Profile registry — design separation point
│   ├── rules.py            # XINDEX rule implementations + Rule/register()
│   ├── _modern.py          # M-MOD-NN rule implementations
│   ├── _vista_kernel.py    # vista profile (VA-Kernel-specific opt-in rules)
│   ├── context.py          # LintContext — thresholds + target engine + workspace + config
│   ├── thresholds.py       # KNOWN_THRESHOLDS defaults + validate()
│   ├── diagnostic.py       # Diagnostic dataclass + Severity + Category enums
│   ├── output.py           # text / json / tap formatters
│   ├── _index.py           # NodeIndex — single-pass AST walk, bucket by node.type
│   └── _keywords.py        # loads command/ISV/function sets from m-standard
├── test/
│   ├── cli.py              # `m test` argparse (--list, --filter, --format, --changed, --timeout, --seed, --env, --update-snapshots, --timings)
│   ├── discovery.py        # tree-sitter-based suite + label discovery; protocol detection
│   ├── runner.py           # ydb subprocess + TESTRUN/STDASSERT output parser
│   ├── changed.py          # git status / diff → suite resolution
│   └── output.py           # text / tap / json / junit formatters
├── watch/
│   ├── cli.py              # `m watch` argparse (--interval, --once, --filter)
│   ├── affinity.py         # changed-file → suite resolution (FOO.m → FOOTST.m)
│   └── poller.py           # mtime-based change detection
├── coverage/
│   ├── cli.py              # `m coverage` argparse (--lines, --branch, --format, --min-percent)
│   ├── runner.py           # YDB view "TRACE" driver + per-line/per-label decode
│   ├── branches.py         # AST branch-point detection
│   └── output.py           # text / json / lcov formatters
├── lsp/
│   ├── server.py           # pygls-based stdio server; lint/fmt/code-action/hover/completion/symbols/lenses/folding/signature/highlight/definition handlers
│   ├── symbols.py          # token_at, lookup_keyword (m-standard-backed)
│   └── structure.py        # find_labels, find_dot_blocks
├── doc/                    # m doc / search / manifest / examples / errors — manifest-driven
├── doctor/                 # m doctor — environment self-check
├── new/                    # m new — project scaffolder
├── ci/                     # m ci init — CI workflow scaffolding
├── run/                    # m run — ad-hoc routine execution
└── build/                  # m build — compile / package
tests/                      # one test file per source module
scripts/                    # corpus-validation drivers + benches + opt-in vista-meta loaders
```

## Testing conventions

- **TDD** — write the test first, confirm RED, implement to GREEN.
- Tests live in `tests/`, one file per source module.
- `conftest.py` handles sys.path and stubs the engine connection so tests don't need a live ydb / vista-meta.
- Coverage minimum enforced in `make check`.

## Code style

- Formatter + linter: `ruff` only (no black).
- Line length: 88.
- Pre-commit hooks enforce style on every commit.
- All Makefile targets use `.venv/bin/` prefixes — never bare `python` / `pytest` / `ruff` / `mypy`.

## Test-runner conventions (project-specific)

- **Discovery is parser-aware.** Suites are `.m` files whose stem matches `[A-Z][A-Z0-9]*TST`; test labels match `t[A-Z]…` and have formals `(pass,fail)`. The first label in a file (the routine entry) is never a test, even if it accidentally matches.
- **Runner is YottaDB-specific.** Whole-suite runs use `ydb -run ^SUITE`; single-label runs use `ydb -run %XCMD "new pass,fail … do tCase^SUITE(.pass,.fail) … do report^STDASSERT"`. The runner shells out via an injectable `RunnerFn` so unit tests don't need a live ydb.
- **Assertion-library detection.** `detect_protocol(src)` records the routine each suite calls into (typically `^STDASSERT`); `run_case` invokes `do start^{protocol}` / `do report^{protocol}` — no hard-coded library name.
- **Output dialects.** `text` (human), `tap` (TAP v13 — one point per parsed assertion), `json` (CI-friendly), `junit` (Jenkins-style XML).
- **Env composition.** `m_cli.test.runner._build_env` honours an existing `ydb_routines` if exported; otherwise it derives one from the suite's parent dir + a sibling `routines/` if present. `$YDB` overrides binary location, falling back to `$ydb_dist/ydb`, then plain `ydb` on PATH.
- **Diff-driven runs.** `m test --changed` filters discovered suites to those affine with git-modified `.m` files via `git status --porcelain` (default) or `git diff --name-only <REV>` (`--changed-base REV`). Reuses `m_cli.watch.affinity.resolve_affinity` so source→suite mapping matches `m watch`.
- **Per-test isolation flags.** `--seed PATH` (load fixtures via `^STDSEED`), `--env PATH` (load `.env` via `^STDENV`), `--update-snapshots` (rewrite `^STDSNAP` baselines), `--timings` (per-suite wall-clock + slowest-first breakdown), `--no-isolation` (opt out of inline tstart/trollback rollback per test).
- **Timeout semantics.** `--timeout SECONDS` (default 600, 0 disables). `RunResult.timed_out` distinguishes timeout from a real `0/0` failure across all four output formats.

## Watch conventions (project-specific)

- **Polling, not inotify.** `m watch` uses periodic `os.stat` (default 0.5 s) — keeps deps minimal at the cost of latency. Pure-Python; no `watchdog` / `entr` / `inotify` dependency.
- **Affinity rule.** `<X>.m` source change → suite `<X.upper()>TST.m` if it exists; otherwise every suite re-runs (defensive default). Suite-file edits map to themselves only.
- **Discovery dedup.** When the user passes overlapping paths (e.g. `routines/` and `routines/tests/`), each suite is discovered once via `Path.resolve()` so symlinks count as the same file.
- **`--once`.** Runs the initial pass and exits — used by tests and as a manual smoke check before starting a long-running watch session.

## Formatter conventions (project-specific)

- **Rule-selector forms.** `--rules=canonical` (SAC hygiene: trim-trailing-whitespace + uppercase-command-keywords) is the default opt-in. `--rules=pythonic`, `--rules=pythonic-lower`, and `--rules=compact` are translation presets between VistA-compact and canonical-name forms. `--rules=all` returns *every* registered rule and is **diagnostic-only** — never use it as a formatter pipeline because `expand-*` / `compact-*` / `uppercase-*` / `lowercase-*` rules race when applied together. `--rules=none` (or omitting the flag) is identity.
- **Translation rules.** Six AST-preserving, case-preserving, idempotent expand/compact rules: `expand-command-keywords` (`S→SET`), `compact-command-keywords` (`SET→S`), `expand-intrinsic-functions` (`$L→$LENGTH`), `compact-intrinsic-functions`, `expand-special-variables` (`$T→$TEST`), `compact-special-variables`. Each walks the parse tree, finds nodes of one type (`command_keyword` / `intrinsic_function_keyword` / `special_variable_keyword`), looks up the uppercase token in m-standard's abbrev↔canonical map, applies edits right-to-left. Maps are built lazily from `keyword_records()` and lru-cached.
- **Case-folding rules.** Three companions force a single case across every node of the relevant type (regardless of canonical/abbrev): `lowercase-command-keywords`, `lowercase-intrinsic-functions`, `lowercase-special-variables`. They share the engine `_rewrite_node_case(src, node_type, transform)` with `uppercase-command-keywords`. Used by the `pythonic-lower` preset for all-lowercase output (`set X=1 write $length(X),$test`). Lowercase rules must run *before* expand rules in the pipeline so case-preserving expand sees a lowercase abbreviation and emits a lowercase canonical.
- **Case preservation (in expand/compact).** All-lowercase reference (`s`) → all-lowercase replacement (`set`). Anything else (`S`, `Set`, `SET`) → uppercase replacement. The unusual mixed-case form is rare in M and unlikely deliberate, so we don't try to mirror it.
- **Translation is *normalizing*, not *invertible*.** Mixed-form input (some `NEW`, some `N`) collapses to one form. Round-trip property holds on already-normalized input only: `compact(pythonic(compact(src))) == compact(src)`. This is the intended behavior.
- **Why no operator spacing or one-command-per-line.** PEP-8-style `S X = 1` breaks the M parser (whitespace is M's argument terminator). Statement splitting (one command per line) violates the AST-shape-preservation contract. Both are out of scope for fmt rules; the lint rule `M-MOD-009` flags multi-command lines for manual fix.

## Linter conventions (project-specific)

- **Engine vs profiles — design separation.** The lint engine (`runner`, `rules`, `diagnostic`) is engine- and dialect-neutral. Opinionated rule sets ride on top as named **profiles** registered in [`src/m_cli/lint/profiles.py`](src/m_cli/lint/profiles.py). XINDEX is *one profile*, not the canonical baseline. New rule families (IRIS-style, ANSI-strict, YDB-best-practice, …) get their own profile and ID prefix; they do not need to be tagged `xindex`.
- **Tags = provenance + policy.** Two distinct concerns ride on the rule's `tags` tuple. `xindex` is *provenance* — the rule was ported from VA's `^XINDEX` scanner. `sac` is *policy* — the rule maps to a documented section of the VA SAC. Most rules carry both; the sets are not identical. Classification is pinned by `tests/test_lint_profiles.py::TestSacClassification` and documented in [`src/m_cli/lint/rules.py`](src/m_cli/lint/rules.py)'s module docstring.
- **Rule IDs.** `M-XINDX-NN` mirrors XINDEX's numeric error codes 1:1 — use the same number when porting an XINDEX rule. `M-MOD-NN` is the greenfield modernization track (engine- and dialect-neutral, derived from contemporary M idioms). When an `M-MOD` rule supersedes an `M-XINDX` rule, declare the relationship via `Rule.replaces=("M-XINDX-NN", ...)`. Future engine- or standard-specific prefixes (`M-IRIS-NN`, `M-YDB-NN`, `M-ANSI-NN`) ship under their own profile and tag.
- **Engine targeting.** `[lint] target_engine = "yottadb" | "iris" | "any"` in `.m-cli.toml`, or `--target-engine`. Default `any` keeps the linter portable; the named engines unlock engine-aware rules ($Z* allowlists, Z-command sets) once those rules ship.
- **Configurable thresholds.** `[lint.thresholds]` config table or `--threshold KEY=VAL` CLI flag (repeatable). Known keys: `line_length` (200), `code_line_length` (1000), `routine_lines` (1000), `label_lines` (50), `cyclomatic` (15), `cognitive` (20), `dot_block_depth` (5), `argument_count` (7), `commands_per_line` (3), `comment_density_pct` (10). Defaults live in [`src/m_cli/lint/thresholds.py`](src/m_cli/lint/thresholds.py); unknown keys are rejected at config-load time (catches typos).
- **`LintContext` (single dispatch path).** Rules opt into a richer signature via `needs_context=True` and receive a `LintContext` carrying `thresholds`, `target_engine`, `workspace`, and `config`. Built once at lint-command entry and threaded through to every context-aware rule. Cross-routine rules read `ctx.workspace`.
- **Default profile.** `default` is the curated M-MOD daily-lint subset (26 rules) — the M-MOD-NN modernization track *minus* the four pedantic style rules (M-MOD-009 commands-per-line, M-MOD-028 label-docstring, M-MOD-031 magic-numbers, M-MOD-032 single-letter-vars) which fire ~90% of noise on real M code. The full M-MOD set is opt-in via `--rules=modern`; the pedantic-only view via `--rules=pedantic`. VA shops use `--rules=xindex` (engine-neutral legacy XINDEX) or `--rules=xindex,vista` for the full VistA-flavoured rule set. Python-influenced developers get `--rules=pythonic` (same rules as `modern` plus tighter thresholds: `line_length=100`, `commands_per_line=1`, `cyclomatic=10`, etc.).
- **Profile presets.** Profiles can bundle threshold defaults via `Profile.default_thresholds`. The `pythonic` profile is the only one that uses this today. Threshold resolution layers profile preset → `[lint.thresholds]` config → `--threshold KEY=VAL` CLI (CLI wins). Other profiles carry empty `default_thresholds` and rely on the system-wide defaults in `m_cli.lint.thresholds.KNOWN_THRESHOLDS`.
- **Keyword sets.** Never hardcode command/ISV/function lists in `rules.py`. Use `_keywords.py` (`standard_commands()`, `standard_isvs()`, `standard_functions()`), which loads from m-standard's TSVs with ANSI fallback.
- **Severity (actionability).** ERROR (must fix; CI fails) · WARNING (should fix) · STYLE (auto-fix preferred; LSP `Hint`) · INFO (informational; no action). The dividing line between actionable and not is `Severity.is_actionable` — only INFO is not. Compact summary uses E/W/S/I letters.
- **Category (kind, orthogonal to severity).** `bug` · `security` · `concurrency` · `performance` · `style` · `complexity` · `documentation` · `portability` · `modernization`. Every Rule declares both severity AND category at registration. Filter by either dimension.
- **Per-rule isolation.** `runner.lint_source` wraps each rule in try/except so one buggy rule can't crash a lint pass — it emits an `M-INTERNAL-RULE-CRASH` diagnostic instead.
- **Inline disable directives.** `; m-lint: disable=RULE` (same line) / `disable-next-line=RULE` / `disable-file=*` (`*` wildcard supported). Lets users tame noisy rules without a config file.
- **Wild-corpus gates.** `make lint-vista` over the configured `CORPUS` is the regression gate for VA-flavoured rules (`xindex`, `vista` profiles). Default `CORPUS=m-modern-corpus` calibrates the M-MOD-NN rule track against contemporary idioms.

## LSP server

`m lsp` starts the m-cli Language Server over stdio. Editors invoke it as a
subprocess and exchange LSP messages on stdin/stdout. Optional dependency:
`pip install 'm-cli[lsp]'` adds `pygls` + `lsprotocol`. The dispatcher
reports a friendly install hint if a user runs `m lsp` without the extra.

**Capabilities advertised:**

- `textDocument/{didOpen,didChange,didSave,didClose}` — push diagnostics on open/change/save; clear on close.
- `textDocument/formatting` — full-document `TextEdit` running `format_source(src, rules=canonical_rules())`. Empty list when source is already canonical or has parse errors.
- `textDocument/codeAction` — Quick Fixes grouped by `fixer_id`. Each action's `WorkspaceEdit` runs the single fmt rule file-wide; duplicates collapse into one click. Skips no-op fixers and parse-error sources.
- `textDocument/hover` — resolves the M token under the cursor (commands, ISVs, intrinsic functions — case-insensitive, abbreviation or canonical) against m-standard's TSVs and returns Markdown (canonical name, abbreviation, syntax format, standard status). Local labels and user routines return None.
- `textDocument/completion` — universe of M commands, ISVs, and intrinsic functions as `CompletionItem`s (kind = Keyword / Constant / Function; detail = the syntax format from m-standard). `isIncomplete: false` — the client filters by typed prefix.
- `textDocument/documentSymbol` — one `SymbolKind.Function` per label; range covers the body until the next label or EOF; selection range covers just the name; formals appended to display name (`INNER(a,b)`).
- `textDocument/codeLens` — `▶ Run test <label>` above each `t<UpperCase>(pass,fail)` test label. Lens carries a `m-cli.runTest` command with `[uri, label]` args; the VS Code extension registers that command and shells out to `m test FILE.m::tLabel`.
- `textDocument/foldingRange` — folds each multi-line label body and each contiguous dot-block run.
- `textDocument/signatureHelp` — inside `$FN(...)` parens (trigger chars `(` and `,`), returns the m-standard syntax format as a single signature. ISV-only / user-label calls return None.
- `textDocument/documentHighlight` — same-file occurrences of the identifier under the cursor with strict word-boundary matching. Single-character tokens skipped (noisy); longer names case-sensitive (M variables are case-sensitive).
- `textDocument/definition` — cross-routine resolution via `WorkspaceIndex`; label-only refs (`D LBL`) fall back to a same-document scan.

**Rule-filter override.** `m lsp --rules <filter>` overrides the default
`default` profile at startup. Accepts the same forms as `m lint --rules`
(profile name, comma list mixing profiles + rule IDs). Wired by stashing
the filter on the `LanguageServer` instance and read inside
`lint_document`. The full LSP `workspace/configuration` round-trip is
intentionally not implemented — the CLI flag covers the same need without
async plumbing.

**Workspace symbol index.** `m_cli.workspace.WorkspaceIndex` maps
`routine_name (uppercased) → list[LabelLocation]` for every `.m` file in
the workspace. Backs `textDocument/definition`, `textDocument/references`,
`workspace/symbol`. Stays fresh via `didChangeWatchedFiles` + `didSave`.
Same index backs cross-routine lint rules. Routine name comes from the
file stem (uppercased) — same convention ydb uses; avoids depending on
the first-label-equals-routine-name M idiom.

**Reference parsing** (`m_cli.workspace.reference_at`). Recognises
`LABEL^ROUTINE`, `^ROUTINE`, `LABEL`, `$$LABEL^ROUTINE`, `$$LABEL`. Cursor
on the label half OR the routine half resolves the same full reference.

**Token resolution and keyword metadata** live in `m_cli.lsp.symbols`
(`token_at`, `lookup_keyword`, `all_keywords`). The structured loader is
`m_cli.lint._keywords.keyword_records()`. When a token (e.g. `$HOROLOG`)
appears as both ISV and intrinsic function in ANSI, the function wins —
that's a real ambiguity in M itself; tests pin unambiguous tokens
(`$JOB` for ISV, `$LENGTH` for function).

**Document-structure helpers** (`m_cli.lsp.structure.find_labels`,
`find_dot_blocks`) walk the tree-sitter tree once and return pure Python
dataclasses. The CodeLens path reuses
`m_cli.test.discovery.find_test_cases` so the LSP and the `m test` runner
agree on what a test label is.

**Editor wiring — VS Code.**
[`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode)
carries a `vscode-languageclient` integration that spawns `m lsp` on
activation. Settings: `m-cli.enabled`, `m-cli.path` (defaults to `m` on
PATH; set to `~/projects/m-cli/.venv/bin/m` for venv installs),
`m-cli.args` (e.g. `["--rules", "xindex,vista"]` to broaden diagnostics),
`m-cli.trace.server`.

**Testable inner helpers** for tests that don't need a pygls runtime:
`m_cli.lsp.server.lint_document`, `format_document`,
`code_actions_for_uri`, `hover_at`, `completion_at`,
`document_symbols_at`, `code_lenses_at`, `folding_ranges_at`,
`signature_help_at`, `document_highlights_at`. Tests use a `FakeServer`
stub.

## Library API for tooling consumers

The LSP wrapper, IDE plugins, pre-commit integrations, and other
out-of-tree tooling import a stable surface from the top-level package:

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

Anything in `__all__` is locked: future internal refactors keep these
importable. Internal helpers (rule check fns, AST walkers, registry
internals) are not part of the public surface and may move.
`tests/test_library_api.py` is the smoke gate that enforces this.

## Lint → fmt fixer linkage

Each lint `Rule` carries an optional `fixer_id` pointing to an `m fmt`
rule that auto-fixes the diagnostic. Today: `M-XINDX-013 ↔
trim-trailing-whitespace` and `M-XINDX-047 ↔ uppercase-command-keywords`.
The link surfaces in `--format=json` output (`"fixer_id": ...` per
diagnostic) and via the `m_cli.lint.fixer_for(rule_id)` helper. The LSP
wrapper uses this to expose Quick Fix code actions; new pairings are
pinned by `tests/test_lint_fixer_linkage.py`.

## Project configuration (`.m-cli.toml` / `[tool.m-cli]`)

`m fmt`, `m lint`, and `m lsp` all read project config on startup.
Discovery walks up from the working directory looking for `.m-cli.toml`
first, then a `pyproject.toml` containing a `[tool.m-cli]` table. Walking
stops at a `.git` boundary so configs in unrelated parent projects don't
leak in. The LSP spawns with `cwd = workspace folder` (VS Code default),
so the same lookup finds the project's config without needing the
`initialize` rootUri.

Schema:

```toml
[lint]
rules = "default"              # profile name or comma-list of rule IDs
                               # (e.g. "xindex" for the VA VistA Toolkit profile)
disable = ["M-XINDX-013"]      # rule ids to skip after selection
target_engine = "yottadb"      # "yottadb" | "iris" | "any"

[lint.severity]
"M-XINDX-019" = "warning"      # remap per-rule severity
                               # values: "fatal" | "standard" | "warning" | "info"

[lint.thresholds]
line_length = 100
commands_per_line = 1
cyclomatic = 10

[lint.taint]                   # M-MOD-036 taint analysis
formals_tainted = true         # treat public-label formals as untrusted input.
                               # set to false for purely-internal helper labels.
extra_sanitizers = ["$E"]      # additional intrinsic-function keywords
                               # whose output is treated as clean. Defaults
                               # cover $L/$LENGTH/$A/$ASCII; add $E for
                               # $EXTRACT, $TR for $TRANSLATE, etc.

[fmt]
rules = "canonical"            # canonical | none (identity) | comma-separated rule ids
```

Resolution order: defaults → config → CLI flag (CLI always wins). Unknown
keys are ignored silently to keep forward compatibility cheap. Invalid
values (bad severity name, `disable` not a list) raise on load.
Implementation lives in `m_cli.config` (`Config` dataclass + `find_config`
+ `load_config`); lint and fmt CLIs apply disable as a post-`select_rules`
filter; severity overrides via `dataclasses.replace` on each `Diagnostic`.
`m lsp` stashes the loaded `Config` on the `LanguageServer` instance and
`lint_document` reads it on every push.

## Engine support

`m test` and `m coverage` need a YottaDB engine.
[`m_cli.engine.detect_engine`](src/m_cli/engine.py) auto-resolves a
transport in this order:

1. **Explicit override** via `M_CLI_ENGINE=local|docker|ssh`.
2. **Local YottaDB** — `mumps` on `$PATH`.
3. **Docker (m-test-engine)** — a running container named `m-test-engine`.
4. **SSH (vista-meta legacy)** — only if `~/data/vista-meta/conn.env` exists.

Pure-source tools (`m fmt`, `m lint`) don't touch this module. Unit tests
stub the engine connection at the import boundary in `conftest.py`, so
the test suite runs without any engine resolved.

## Pre-commit integration

Downstream M projects opt into `m fmt --check` and
`m lint --error-on=fatal` via the [pre-commit
framework](https://pre-commit.com):

- Hook declarations live in [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml). Three hooks: `m-fmt-check`, `m-fmt` (write), `m-lint`.
- Schema integrity is gated by `tests/test_pre_commit_hooks.py` — every hook's `entry` must invoke a real `m` subcommand, and the `files` regex must match `.m` paths.
- See [`docs/pre-commit.md`](docs/pre-commit.md) for downstream usage. Downstream projects install m-cli locally (clone + venv) and use the `language: system` style.

## Performance

The lint perf budget per
[m-tooling-tier1.md §3.5](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tooling-tier1.md#35-validation-gates)
is 120 s for the full VistA corpus (39,330 routines). m-cli meets it with
comfortable headroom:

- **Single-pass dispatcher.** `m_cli.lint._index.NodeIndex` walks each parse tree exactly once and groups nodes by `node.type`; rules consume `index.of("X")` instead of running their own `_walk(tree.root_node)`.
- **Multiprocessing.** `m lint --jobs N` (default `os.cpu_count()`) runs `lint_source` in a `ProcessPoolExecutor`. Each routine is independent. On a 16-core host the full VistA corpus lints in ~22 s — comfortably under the 120 s budget.
- Findings are byte-identical to the serial single-rule walk.

## Plugin extension

Out-of-tree subcommands register against m-cli via the `m_cli.plugins`
Python entry-point group. `src/m_cli/plugins.py` walks the group at
dispatcher startup; each plugin's `register(subparsers)` callable adds
its subcommand using the same argparse pattern built-ins use. Built-ins
always win on name collisions; plugin failures are isolated (a
`register()` that raises is reported, not fatal). `m plugins` prints the
discovered plugins (text or `--json`).

`PLUGIN_API_VERSION = 1` is the bump knob for breaking-change releases.
Reference plugin:
[`m-cli-extras`](https://github.com/m-dev-tools/m-cli-extras) (ships
`m corpus-stats`). Contract:
[`docs/plugin-development.md`](docs/plugin-development.md).

## Git conventions

- Default branch: `main`. Remote: `github.com/m-dev-tools/m-cli`.
- Pre-push hook runs `pytest` — push fails if tests fail.
- `make push` runs full `check` before pushing.
- Commit messages: descriptive, multi-line; first line under 70 chars.

## Claude guidelines

- Prefer editing existing files over creating new ones.
- Keep rules small and independently testable; one rule per module-level `register(Rule(...))` block.
- Use `logging` not `print()` in library code.
- No mocks unless unavoidable — fixtures are real `.m` source strings.
- This is a focused project — keep solutions simple and direct.
- The `m <subcommand>` naming convention is universal — do NOT introduce `y*` names for new tools.
- For history, evolution, phase tracking, or development milestones: add to [`docs/evolution.md`](docs/evolution.md), not this file. CLAUDE.md is the as-is project context.
