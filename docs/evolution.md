---
created: 2026-05-10
last_modified: 2026-05-10
revisions: 1
doc_type: [HISTORY, BUILD-LOG]
---

# m-cli — evolution

How m-cli was built, in chronological order. This is **archaeology** — read the
[README](../README.md) for the as-is, and [`docs/guide.md`](guide.md) for the
comprehensive user-facing reference. This document exists so that decisions
remain auditable and so future contributors can understand *why* things are
shaped the way they are without having to reverse-engineer commit history.

## Contents

- [Origin: the four-tier strategy](#origin-the-four-tier-strategy)
- [Tier 1 — closing the inner-loop gaps](#tier-1--closing-the-inner-loop-gaps)
- [Tier 2 — quality gates and team scaling](#tier-2--quality-gates-and-team-scaling)
- [Cross-cutting — LSP, scaffolding, plugins](#cross-cutting--lsp-scaffolding-plugins)
- [Performance milestones](#performance-milestones)
- [Deferred items and known quirks](#deferred-items-and-known-quirks)
- [Retirements](#retirements)
- [Renames / namespace moves](#renames--namespace-moves)
- [Engine refactor follow-ups](#engine-refactor-follow-ups)
- [Bootstrap substrate](#bootstrap-substrate)

## Origin: the four-tier strategy

m-cli grew out of [`m-tools`](https://github.com/m-dev-tools/m-tools) — the
archived seed of the entire m-dev-tools organization. The driving documents
([gap-analysis-and-remediation-strategy.md](https://github.com/m-dev-tools/m-tools/blob/main/docs/gap-analysis-and-remediation-strategy.md),
[m-tool-gap-analysis.md](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tool-gap-analysis.md),
[m-tooling-tier1.md](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tooling-tier1.md))
ranked the missing developer-experience capabilities for the M (MUMPS) language
across both major engines (IRIS and YottaDB), validated against DORA /
*Accelerate* research, and produced four prioritised tiers:

| Tier | Theme | Capabilities |
|------|-------|--------------|
| 1 | Inner loop | test runner · lint (logic) · format · single-test selection · watcher |
| 2 | Quality gates / team scaling | CI script · coverage · style lint · pre-commit hooks · debugger |
| 3 | Project scaffolding | `new` · `run` · `build` · `doc` · `doctor` |
| 4 | Library ecosystem | versioning · dependency management · package registry |

m-cli is the executor. The naming convention (`m <subcommand>`, mirroring
`go`/`cargo`/`git`) and the breakdown by subcommand both come from that
strategy.

## Tier 1 — closing the inner-loop gaps

### Step 1: `m fmt` — formatter

Shipped: identity round-trip first, then layered hygiene + translation rules.

- **Step 1.0 — identity round-trip.** Full parse → emit cycle that produces
  byte-identical output for already-canonical input. Validation gate: VistA
  round-trip 38,954 / 39,330 routines (99.04%) — the residual 0.96% match the
  [tree-sitter-m corpus boundary](https://github.com/m-dev-tools/tree-sitter-m).
- **Canonical hygiene rules.** `--rules=canonical` adds `trim-trailing-whitespace`
  + `uppercase-command-keywords`. Idempotent and AST-shape-preserving over the
  full VistA corpus.
- **Phase A translation rules.** Six AST-preserving, case-preserving
  expand/compact rules ride alongside canonical hygiene:
  `expand-command-keywords` (`S`→`SET`), `compact-command-keywords` (`SET`→`S`),
  `expand-intrinsic-functions` (`$L`→`$LENGTH`), `compact-intrinsic-functions`,
  `expand-special-variables` (`$T`→`$TEST`), `compact-special-variables`. Three
  case-folding companions (`lowercase-command-keywords`,
  `lowercase-intrinsic-functions`, `lowercase-special-variables`). Bundled
  into three presets — `pythonic`, `pythonic-lower`, `compact` — that
  translate between VistA-compact and canonical-name forms for developers
  coming from Python or other modern languages without the M tradition of
  one-/two-character abbreviations. All three are *normalizing* (idempotent
  on already-normalized input) rather than fully invertible.

### Step 2: `m lint` — linter

Shipped breadth-first then deepened with cross-routine analysis, control-flow
rules, and the M-MOD modernization track.

- **Step 2.0 — engine-neutral lint engine.** Rules register against a profile
  registry; opinionated rule sets ship as named profiles (not as a fixed
  baseline). The dividing line between the engine and the rule packs is
  formalized in [`src/m_cli/lint/profiles.py`](../src/m_cli/lint/profiles.py)
  so adding a non-VA-flavoured rule family doesn't require renaming any
  config.
- **Step 2.1 — XINDEX port.** 42 of XINDEX's 66 rules ported to engine-neutral
  AST checks (`M-XINDX-NN`). Validation gate: full VistA corpus lint baseline.
- **Step 2.x — M-MOD modernization track.** 30 engine-neutral, dialect-neutral
  rules derived from contemporary M idioms (`M-MOD-NN`). Includes
  length/complexity, concurrency, transactions, control-flow correctness,
  engine-aware portability, docs/style polish. Calibration corpus:
  [`m-modern-corpus`](https://github.com/m-dev-tools/m-modern-corpus). On a
  4 K-routine non-VA corpus the curated `default` profile (M-MOD minus four
  pedantic rules) produces ~3 findings/routine — usable daily; the full
  `modern` profile produces ~57 findings/routine, mostly from the four
  pedantic rules now split into `pedantic`.
- **Profile split.** The default lint profile changed from `xindex` to the
  curated M-MOD subset after modern-corpus validation showed XINDEX's SAC
  legacy rules generate ~62 K findings on non-VA modern code — mostly from
  SAC mandates around lowercase variables/commands that aren't followed
  outside the VA. VA shops opt back in via `--rules=xindex` or
  `--rules=xindex,vista`.
- **`pythonic` profile.** Same rules as `modern` plus tighter thresholds
  (`line_length=100`, `commands_per_line=1`, `cyclomatic=10`,
  `cognitive=15`, `dot_block_depth=3`, `label_lines=30`). Preset for
  Python-influenced developers.
- **Cross-routine + control-flow + engine-targeting.** Workspace context
  (`LintContext`) flowed through to context-aware rules; `--target-engine`
  silences engine-portability false positives on engine-specific code.

### Step 3: `m test` — test runner

Shipped: parser-aware discovery, YottaDB runner, three output formats.

- Discovery walks `*TST.m` files and `t<UpperCase>(pass,fail)` labels via
  the tree-sitter parse tree. The first label in a file (the routine entry)
  is never a test even if it accidentally matches.
- Runner shells out to `ydb -run ^SUITE` (whole suite) or `ydb -run %XCMD`
  (single label). The runner is injected via `RunnerFn` so unit tests don't
  need a live engine.
- Output dialects: `text` (human), `tap` (TAP v13, one point per assertion),
  `json` (CI-friendly).
- TESTRUN protocol: parser keys off `  PASS  desc` / `  FAIL  desc` lines,
  the `Results: N tests P passed F failed` summary, and the
  `All tests passed.` / `<n> test(s) FAILED.` banner.

### Step 4: single-test selection

Folded into Step 3. `m test FILE.m::tLabel` invokes `^%XCMD` with a
synthesised driver that calls just the requested label.

### Step 5: `m watch` — TDD watcher

Shipped: polling watcher with source→suite affinity.

- **Polling, not inotify.** `os.stat`-based change detection at 0.5 s default
  interval. Pure-Python; no `watchdog` / `entr` / `inotify` dependency.
- **Affinity rule.** `<X>.m` source change → `<X>TST.m` suite if it exists;
  otherwise every suite re-runs (defensive default). Suite-file edits map
  to themselves only.
- **Discovery dedup.** Overlapping path arguments (e.g. `routines/` and
  `routines/tests/`) discover each suite exactly once via `Path.resolve()`.

**Tier 1 closure: 2026-04-27.** All four §3.5 validation gates pass (VistA
round-trip, single-engine smoke, CI dogfooding, performance under budget).

## Tier 2 — quality gates and team scaling

### Coverage (`m coverage`)

YDB built-in `view "TRACE"` instead of N ZBREAKs per label — one trace pass
covers the whole run. Trace third-subscript decoded: offset N from a label
maps to absolute line `label_decl_line + N`, so per-line hit counts are
precise. Output: `text` (default), `text --lines` (per-routine label + line
columns), `json`, `lcov` (genhtml / Codecov / Coveralls compatible).
`--branch` flag adds AST-driven branch-point identification (IF/ELSE/FOR
keywords + postconditionals); branches collected only when caller opts in
so default payloads stay byte-stable.

### Pre-commit hooks

[`.pre-commit-hooks.yaml`](../.pre-commit-hooks.yaml) exposes `m-fmt-check`,
`m-fmt`, and `m-lint`. Schema gated by tests. Downstream usage in
[`docs/pre-commit.md`](pre-commit.md).

### Style lint

Style rules ride alongside logic rules in `m lint`. `--rules=sac` selects
the SAC-tagged subset; severity overrides via `[lint.severity]` config.

### Debugger — deferred

DAP integration is its own engineering project; both engines ship `ZBREAK`
at the engine level. Not on the near-term roadmap.

## Cross-cutting — LSP, scaffolding, plugins

### `m lsp` — Language Server

Built incrementally in stages over a single foundation (`pygls`-based stdio
server, optional `[lsp]` extra). Per
[m-tooling-tier1.md §5.4](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tooling-tier1.md#54-editor-integration-cadence)
the stage cadence was:

| Stage | Capability |
|-------|-----------|
| 1     | Diagnostics push (didOpen/didChange/didSave/didClose) |
| 2     | Document formatting (`textDocument/formatting`) |
| 3     | Code actions (Quick Fix from `fixer_id`) |
| 4     | Hover + completion + `--rules` filter |
| 4b    | Document symbols, code lenses (▶ Run test), folding, signature help, document highlight |
| B     | Workspace symbol index + go-to-definition |

Editor wiring lives in
[`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode)
which spawns `m lsp` on activation and registers `m-cli.runTest` for
code-lens click-to-run.

### Project config — Phase A

`.m-cli.toml` (preferred) and `[tool.m-cli]` in `pyproject.toml` (fallback)
drive `m fmt`, `m lint`, and `m lsp`. Discovery walks up from the working
directory; stops at `.git`. Schema: `[lint] rules / disable / severity`,
`[fmt] rules`, `[lint.thresholds]`, `[lint.taint]`. CLI flags override
config; unknown keys ignored; invalid values raise.

### Workspace symbol index — Phase B

`m_cli.workspace.WorkspaceIndex` maps `routine_name (uppercased) →
list[LabelLocation]` for every `.m` file in the workspace. Backs
`textDocument/definition`, `textDocument/references`, `workspace/symbol`.
Stays fresh via `didChangeWatchedFiles` + `didSave`. Cross-routine lint
rules consume the same index.

### Project scaffolding (Tier 3 capabilities)

- `m new` — project scaffolder (Makefile, `.m-cli.toml`, `tests/`, CI)
- `m run` — ad-hoc routine execution
- `m build` — compile / package *(retired 2026-05-11 — see "Retirements" below; the M runtime auto-compiles on first call, so this was redundant with `m test` and named after compile-mandatory toolchains that don't fit MUMPS)*
- `m doctor` — environment self-check (ydb, parser, m-standard, manifests)
- `m doc` / `m search` / `m manifest` / `m examples` / `m errors` —
  m-stdlib documentation surface, manifest-driven

### Plugin extension

`m plugins` lists out-of-tree subcommands registered via the
`m_cli.plugins` entry-point group.
[`m-cli-extras`](https://github.com/m-dev-tools/m-cli-extras) is the first
consumer (ships `m corpus-stats`). Contract documented in
[`docs/plugin-development.md`](plugin-development.md).

## Performance milestones

The lint perf budget per
[m-tooling-tier1.md §3.5](https://github.com/m-dev-tools/m-tools/blob/main/docs/m-tooling-tier1.md#35-validation-gates)
is 120 s for the full VistA corpus. Three optimisation passes:

| Phase | Time on full VistA corpus | Speedup vs prior | Notes |
|-------|--------------------------|------------------|-------|
| Original (Step 2.1, naive walk per rule) | ~1458 s | — | 12× over budget |
| Single-pass `NodeIndex`                   | 166 s   | 8.7×  | Walk once per file; bucket by node type; dispatch off the bucket |
| `--jobs N` ProcessPool                    | 22.6 s  | 5.3×  | 16-core host; 5.3× *under* budget; 64.5× faster than the original |

Findings byte-identical at every step (62,806 total / 42 fatal / 24,877
flagged). Cached parsed trees for incremental lint are deferred until the
LSP daemon makes them meaningful.

## Deferred items and known quirks

### Open items

1. **More data-flow lint rules.** The remaining ~24 deferred XINDEX rules
   (uninitialized variable read, naked references, kill of read-only var,
   etc.) need data-flow / scope tracking. The infrastructure shipped with
   `LintContext` makes each easier to add incrementally.
2. **`m test --watch` / JUnit XML / per-label results in whole-suite mode.**
   Per-label whole-suite reporting is blocked on `TESTRUN.m` not emitting
   per-label headers — either modify TESTRUN or have whole-suite runs
   internally invoke each label separately.
3. **Inotify watcher.** Polling burns CPU on idle for large trees. Swap
   `Poller` for a `watchdog`-based implementation behind the same
   interface — affinity / CLI don't need to change.
4. **Watcher debounce.** Fast saves (editor backups, formatter passes) fire
   several events in a row; today each becomes a separate run. A
   200–300 ms debounce would batch them.
5. **Cross-routine call graph for richer affinity.** When `foo.m` changes,
   re-run any suite whose source calls `^foo`. Needs a simple call-graph
   index; out of scope for Tier 1.
6. **LSP `workspace/configuration` round-trip** — per-rule disable /
   severity remap via the LSP protocol rather than `--rules`. Intentionally
   deferred; the CLI flag covers the immediate need without async plumbing.
7. **CodeLens `resolveProvider`** — lazy command resolution if eager
   populate becomes a perf concern.
8. **`hover-on-diagnostic`** — show rule descriptions in the hover popup
   when over a diagnostic squiggle.

### Known quirks

- **Branch is `master`, not `main`** — different from most repos under
  the org.
- **376 / 39,330 VistA routines fail to parse** — these match the
  tree-sitter-m corpus boundary. Skipped from both round-trip and lint
  gates.
- **8 currently-silent registered XINDEX rules** (M-XINDX-002, 015, 018,
  021, 027, 028, 031, 054) fire on patterns rare in VistA but common in
  other corpora. Left registered for use against more diverse codebases.
- **`scripts/lint_bench.py`** has a hardcoded
  `~/vista-meta/vista/vista-m-host/Packages/...` path. It's a maintainer
  microbenchmark, not part of the user surface; portability across
  machines is not a goal.

## Retirements

Commands that shipped in earlier phases but were later removed
because experience showed they didn't earn their place in the
surface. Recorded here so the history of *why something is no
longer there* is as legible as the history of why something
shipped.

### `m build` — retired 2026-05-11

**What it was.** Shipped in Phase 3a (2026-05-06) as one of the
six quick-win subcommands from [`plans/language-cli-survey.md`
§6.2](plans/language-cli-survey.md) (rank 9). It walked `.m` files
in the given paths and invoked `ydb <file>` on each — YottaDB's
MUMPS compiler, which emits a sibling `.o` object file. A `--check`
mode cleaned up generated `.o` files for CI use.

**Why it was removed.** Honest accounting after the
[`cli-menu-system.md`](cli-menu-system.md) frequency-rating
exercise showed `m build` doesn't earn a slot in the daily-use
surface:

1. **Redundant with `m test`.** YottaDB auto-compiles on first
   reference (`$ZRO`). Every routine your tests touch is compiled
   anyway — a syntax error in a referenced routine surfaces as a
   test-time compile failure, same exit code, same diagnostic. No
   incremental signal from running `m build` separately.
2. **Wrong language analogy.** MUMPS is interpreted (like Python,
   not like Go or Rust). Python's `python -m compileall` parallels
   what `m build` does (bytecode warmup) but it's almost never used
   in daily Python dev. Python's *namespaced* "build" command
   (`python -m build`) is for PEP 517 package distribution — a
   different concept entirely. `m build` sat in a naming-and-frequency
   gap that doesn't exist for an interpreted language.
3. **Tree-sitter-m + `m lint` already catch more.** The parser-driven
   linter flags real problems the YottaDB compiler accepts (style,
   portability, dead code, untested patterns). Compile-rejects are
   a tiny remainder once lint is green.
4. **Narrow remaining use cases don't justify a daily-loop verb.**
   The legitimate scenarios — CI syntax-gate over untested code,
   post-bulk-refactor sanity sweep, pre-deploy `.o` warmup — are
   either rare interactive use (≤ once per quarter) or scripted
   (CI / CD pipelines). For those, `ydb <file>` directly is five
   lines of bash; the m-cli convenience layer was thin.

**What replaces it.** Nothing on the m-cli surface. For the
remaining narrow use cases:

- **CI syntax gate over untested code**: shell into a loop
  (`for f in $(find . -name '*.m'); do ydb "$f" || exit 1; done`)
  or wait for the eventual `m lint --strict` / `m check` proposal
  to integrate the YottaDB compiler as one validator among several.
- **Post-refactor sanity sweep**: same one-liner.
- **Pre-deploy `.o` warmup**: belongs in the deploy pipeline, not
  in the developer-facing CLI.

**Mechanical changes.** `src/m_cli/build/` package removed;
`m build` subparser unwired from `src/m_cli/cli.py`;
`tests/test_build.py` removed; the `m build` row dropped from
`tests/test_cli_ux_contract.py`; `dist/commands.json` regenerated;
references scrubbed from `README.md`, `AGENTS.md`,
`docs/cli-menu-system.md`, `docs/guide.md`,
`docs/worked-example-accsum.md`. The `docs/plans/` historical
documents (language-cli-survey, iris-ydb-portability,
cli-ux-conventions-remediation) are left as-is — they're frozen
plan records, not as-is references.

## Renames / namespace moves

Commands that shipped earlier under one name but were later moved
into a different shape (typically a namespace). The behavior is
preserved; only the invocation changes.

### m-stdlib reference → `m stdlib <verb>` (2026-05-11)

**What changed.** The 5 m-stdlib reference commands were lifted out
of the top-level namespace and grouped under a single `m stdlib`
parent dispatcher:

| Before                  | After                              |
| ----------------------- | ---------------------------------- |
| `m doc SYMBOL`          | `m stdlib doc SYMBOL`              |
| `m search QUERY`        | `m stdlib search QUERY`            |
| `m examples [MODULE]`   | `m stdlib examples [MODULE]`       |
| `m errors`              | `m stdlib errors`                  |
| `m manifest [PATH]`     | `m stdlib manifest [PATH]`         |

**Why.** Cognitive and logical grouping. Five distinct top-level
verbs all served the same purpose (read the m-stdlib manifest in
different views), but their names didn't make that relationship
visible. `m doc` could have meant "doc the project" (m-cli's own
docs), "doc one routine", or "doc m-stdlib" — only the description
disambiguated. Grouping under `m stdlib` mirrors the existing
`m engine <verb>` and `m ci <verb>` patterns: when a cluster of
commands shares a domain, name the domain.

**Mechanical changes.** New `src/m_cli/stdlib_cli.py` registers
the `stdlib` subparser + 5 sub-actions (mirroring
`m_cli.engine_cli.add_engine_arguments` but without the
`required=True` anti-pattern — bare `m stdlib` prints a gh-style
overview). The 5 top-level parsers were removed from
`src/m_cli/cli.py`. Underlying handlers in `m_cli.doc.*` are
unchanged; only the registration site moved. Contract tests
updated: `TestUnknownFlagRoutesToSubparser` now has a separate
parametrize for `m stdlib <verb>`; `TestDomainFailuresExit1`
passes `["stdlib", verb]`; new
`test_stdlib_bare_exits_0_with_overview`. `dist/commands.json`
regenerated.

**No backward-compat shim.** Per project convention (CLAUDE.md
"Don't use feature flags or backwards-compatibility shims when
you can just change the code"), `m doc` etc. now return
argparse's `invalid choice` error. Users who relied on the old
names see a clean error directing them to the new namespace.

**Top-level count.** 14 commands (down from 18). `m stdlib`
adds 5 sub-verbs; total distinct invocations: 28 (unchanged).

## Engine refactor follow-ups

The engine-phase3 work (merged 2026-05-11) introduced
`detect_engine()` as the canonical resolver across local / docker /
SSH, made docker the default, and grew the `m engine` verb family.
But the runtime tools (`m test`, `m coverage`, `m run`) were never
migrated to the new resolver — they continued calling
`read_connection()` directly, which only returns an `SSHEngine`.
On docker-only hosts (the canonical default after `4f4b88c`) this
meant those tools silently worked only if a stale vista-meta
`conn.env` happened to exist; on hosts without one they returned
"vista-meta connection not configured" despite a healthy
`m-test-engine` container.

This section tracks the migration of those tools to
`detect_engine()`.

### `m run` migrated to `detect_engine()` (2026-05-11)

**What changed.** `m run` now resolves its transport via
`detect_engine()` and dispatches through a new
`engine.build_run_cmd(entryref, extras, stage)` method on each
Engine class (LocalEngine / DockerEngine / SSHEngine). Behaviour
is identical for the user: `m run "^FOO" -- arg1 arg2` runs the
routine and feeds `$ZCMDLINE`. What's different is **where** it
runs — host process on a local-YDB box; `docker exec
m-test-engine bash -lc 'mumps -run ^FOO arg1 arg2'` on a
docker-only box; SSH hop on a vista-meta-configured box.

**Mechanics.**
- `LocalEngine.build_run_cmd` returns
  `["env", "ydb_routines=...", "mumps", "-run", entryref, *extras]`.
- `DockerEngine.build_run_cmd` shell-quotes every arg via
  `shlex.quote` so spaces / quotes / dollar signs survive the
  `bash -lc` hop, then wraps in `docker exec <container> bash -lc`.
- `SSHEngine.build_run_cmd` does the same shell-quoting then
  routes through `_ssh_argv` / `_remote_script`.
- `m_cli/run/cli.py` rewritten: drops the legacy
  `resolve_ydb_binary` path, calls `detect_engine()`,
  `engine.stage_routines(cwd)`, then `engine.build_run_cmd(...)`.
  Missing-engine now returns 1 (DOMAIN_FAILURE) per CLI-UX guide
  §3.7 — was 2 (usage error) before; matches the PR-4 pattern.
- Legacy helpers in `m_cli/run/runner.py`
  (`resolve_ydb_binary`, `build_env`, `build_command`) preserved
  for library backcompat — some downstream tooling may still
  import them. Tests cover both surfaces.

**Smoke test.** Live host (docker-only, m-test-engine running)
ran `m run "^HELLO" -- arg1 "two words"` successfully — output
"`hello from m run via docker, $ZCMDLINE=arg1 two words`",
exit 0. The shell-quoting hop preserved the spaces in
"two words" through `docker exec → bash -lc → mumps -run`.

**Pre-existing tests.** All 19 `test_run.py` tests rewritten to
inject a `FakeEngine` via `monkeypatch.setattr` on
`m_cli.run.cli.detect_engine` instead of a fake ydb binary. The
pure-helper tests (parse_entryref, resolve_ydb_binary,
build_env, build_command) are kept untouched as library-API
regression gates.

### Still open: `m test` and `m coverage`

Same pattern — both currently call `read_connection()` directly,
both lock the user to SSH. On docker-only hosts these commands
silently fail (or worse, silently produce zero output and report
"0/0 passed" as a `m test` "failure"). Migration is mechanically
similar: replace `read_connection()` with `detect_engine()`,
replace `build_xcmd_ssh_cmd(conn, ...)` / `build_suite_ssh_cmd(conn,
...)` with the polymorphic dispatcher wrappers, and update
`seed_for_paths` to take any Engine. Not done in the same commit
as the `m run` migration to keep blast radius small and the smoke
test focused.

## Bootstrap substrate

m-cli's parser, formatter, and lint rules were calibrated during initial
development against the VistA corpus running on the `vista-meta` YottaDB
container. That bootstrap relationship is now historical — the default
test substrate is [`m-test-engine`](https://github.com/m-dev-tools/m-test-engine)
(a minimal Docker YottaDB container), and the calibration corpus is
[`m-modern-corpus`](https://github.com/m-dev-tools/m-modern-corpus). The
vista-meta SSH path remains as an opt-in fallback for the maintainer's
existing setup.

For the full bootstrap account and the explicit independence verification,
see [`vista-meta-bootstrap.md`](vista-meta-bootstrap.md).
