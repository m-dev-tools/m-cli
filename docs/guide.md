# m-cli — Comprehensive Guide

**Document type:** Reference + roadmap
**Scope:** Everything a developer or strategic reader needs to understand `m-cli`'s purpose, current state, and place in the M (MUMPS) tooling ecosystem.
**Companion documents:**
- [m-tools / m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md) — vendor-neutral inventory of the M-tooling gap, the strategic justification for `m-cli`'s existence
- [m-tools / m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md) — the focused Tier 1 strategic plan that `m-cli` implements
- [pre-commit.md](pre-commit.md) — downstream pre-commit integration

---

## Table of Contents

- [1. What `m-cli` is](#1-what-m-cli-is)
- [2. Why it exists — the M tooling gap](#2-why-it-exists--the-m-tooling-gap)
- [3. Where `m-cli` fits in the remediation roadmap](#3-where-m-cli-fits-in-the-remediation-roadmap)
  - [3.1 The four-tier framework](#31-the-four-tier-framework)
  - [3.2 Coverage matrix](#32-coverage-matrix)
- [4. Foundations](#4-foundations)
- [5. Architecture](#5-architecture)
- [6. Subcommand reference](#6-subcommand-reference)
  - [6.1 `m fmt`](#61-m-fmt)
  - [6.2 `m lint`](#62-m-lint)
  - [6.3 `m test`](#63-m-test)
  - [6.4 `m watch`](#64-m-watch)
  - [6.5 `m lsp`](#65-m-lsp)
- [7. Project configuration](#7-project-configuration)
- [8. Editor integration (VS Code)](#8-editor-integration-vs-code)
- [9. Library API for downstream tools](#9-library-api-for-downstream-tools)
- [10. Pre-commit integration](#10-pre-commit-integration)
- [11. Validation gates](#11-validation-gates)
- [12. Roadmap & open work](#12-roadmap--open-work)
- [13. Design principles](#13-design-principles)

---

## 1. What `m-cli` is

`m-cli` is a vendor-neutral, source-level developer toolchain for the M (MUMPS) language, exposed as a single `m` binary with subcommands:

```
m fmt    — format M source
m lint   — lint M source (XINDEX-equivalent rule pack + extensions)
m test   — discover and run M test suites against YottaDB
m watch  — auto-rerun affected suites on file save
m lsp    — Language Server (stdio) for editor integration
```

The tools share a parser ([`tree-sitter-m`](https://github.com/rafael5/tree-sitter-m)) and a language reference ([`m-standard`](https://github.com/rafael5/m-standard)). Source-level tools (`fmt`, `lint`) are engine-neutral — they consume `.m` text via the parser regardless of which M engine the code runs on. Runtime tools (`test`, coverage, trace) currently target YottaDB primarily; an IRIS adapter is a deliberate future concern (see §3.4 of [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md)).

`m-cli` is the canonical implementation of the **Tier 1 deliverable** described in [m-tools / m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md), and is the active replacement for the legacy `y*` shell scripts in `~/projects/m-tools/bin/` (kept only as references).

---

## 2. Why it exists — the M tooling gap

[m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md) inventories the developer toolchain that mainstream languages take for granted (Python, JavaScript/TypeScript, Go, Rust, Java) and benchmarks each major M engine — InterSystems IRIS and YottaDB — against it. The §7 consolidated table (the consolidated gap matrix) finds:

> **22 of the 23 applicable gold-standard categories are common gaps** — both engines ship **None** or only **Basic / Minimal** support for MUMPS code. **No category is fully solved on both engines.**

Of those 22:
- **16 are *MAJOR common gaps*** — both engines ship **None** for MUMPS code. These include linter, formatter, test runner, single-test selection, test watcher, coverage, documentation generator, dead code detection, complexity metrics, pre-commit hooks, and others.
- **6 are *PARTIAL common gaps*** — both engines ship something usable but well below the gold standard.

The strategic insight at the heart of the analysis ([§7](../../m-tools/docs/m-tool-gap-analysis.md#7-consolidated-gap-analysis)):

> A single vendor-neutral, source-level tool — built on a shared MUMPS parser foundation — can fill each of these gaps for both engines simultaneously.

`m-cli` is the realisation of that strategy. Each subcommand fills one or more of those major common gaps, runs on `.m` source files via `tree-sitter-m`, and works for any conformant M engine without engine-specific adapters (except for the runtime test execution shim, which is intentionally pluggable).

---

## 3. Where `m-cli` fits in the remediation roadmap

### 3.1 The four-tier framework

The §8 ranking in [m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md#8-rank-ordered-developer-impact-where-to-invest-first) groups gold-standard tooling categories into four tiers by developer impact:

| Tier | Theme | Why |
|------|-------|-----|
| **Tier 1 — The development loop** | Test runner, logic linter, formatter, single-test selection, test watcher | Felt every edit. Empirically validated against DORA / *Accelerate*, Sadowski et al., Vasilescu et al. The single biggest M developer-experience gap. |
| **Tier 2 — Quality gates and team scaling** | CI script, coverage, style linter, pre-commit hooks, debugger | Move quality work from individual discipline to automated guarantee. Foundation of multi-developer collaboration. |
| **Tier 3 — Maintenance and ecosystem** | Documentation, dependency management, dead-code detection, complexity metrics, fixture management | Become important after a project has scale. |
| **Tier 4 — Specialised / quality-of-life** | Snapshot testing, build tasks, REPL, syntax check, profiling, benchmarking, security scan, package publishing | Narrow contexts or polish on top of capabilities already minimally present. |

`m-cli` was designed to deliver **Tier 1 first** (per [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md)), then layer in Tier 2 quality-gate features as they become tractable on the same foundation.

### 3.2 Coverage matrix

The table below mirrors the categories in [§7 of m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md#7-consolidated-gap-analysis), grouped by tier and ordered by developer impact within each tier. Each row records the original gap classification (from the analysis), `m-cli`'s current status, and the responsible subcommand or module.

**Status legend:**
- ✅ **Done** — shipped, validated against the VistA corpus where applicable
- 🟡 **Partial** — shipped but not yet at the breadth/depth expected for full coverage
- ⏳ **Planned** — explicit roadmap item; design known, work not yet started
- ⏸️ **Deferred** — intentionally out of scope or waiting on a prerequisite
- ➖ **N/A** — does not apply to M

| # | Tier | Category | Original gap | m-cli status | Subcommand / module | Notes |
|---|:---:|---|:---:|:---:|---|---|
| 1 | 1 | Test runner | MAJOR | ✅ Done | [`m test`](#63-m-test) | Parser-aware suite + label discovery via tree-sitter; YottaDB runner; text / TAP / JSON output. Smoke gate: 11 m-tools suites / 224 assertions pass. |
| 2 | 1 | Linter (logic) | MAJOR | 🟡 Partial | [`m lint`](#62-m-lint) | 37 of XINDEX's 66 rules implemented. Cross-routine rules (M-XINDX-004 et al.) wait on Phase B of the workspace symbol index. The 30 deferred rules need data-flow / scope tracking — Tier 1 is breadth-first. |
| 3 | 1 | Formatter | MAJOR | ✅ Done | [`m fmt`](#61-m-fmt) | Identity formatter round-trips 99.04% of VistA byte-for-byte. `--rules=canonical` adds two opt-in transformations (trim trailing whitespace, uppercase command keywords). Idempotent + AST-preserving over 38,954 routines. |
| 4 | 1 | Single-test selection | MAJOR | ✅ Done | `m test FILE.m::tLabel` | Folded into Step 3. |
| 5 | 1 | Test watcher | MAJOR | ✅ Done | [`m watch`](#64-m-watch) | Polling-based (no inotify dependency). Source-to-suite affinity: `foo.m` → `FOOTST.m`. |
| 6 | 2 | CI script | PARTIAL | 🟡 Partial | Project Makefile + pre-commit hooks | `m-cli` is dogfooded in its own CI (`make check`). Downstream M projects get a CI starter via [pre-commit hooks](#10-pre-commit-integration). A dedicated `m ci` orchestrator is not yet in the roadmap. |
| 7 | 2 | Coverage | MAJOR | 🟡 First slice shipped | `m coverage` (Phase C) | Label-level coverage via YDB ZBREAK instrumentation; parser-aware label discovery via the workspace index. Live smoke against m-tools matches `ycover` byte-for-byte (85/123 = 69.1%). Line-level via source instrumentation is the next slice. |
| 8 | 2 | Linter (style) | MAJOR | ✅ Done | `m lint --rules=sac` | Style rules ride alongside logic rules. Severity-tagged (FATAL / STANDARD / WARNING / INFO) so projects can gate selectively via `--error-on=...` or [`[lint.severity]` config overrides](#7-project-configuration). |
| 9 | 2 | Pre-commit hooks | MAJOR | ✅ Done | [`.pre-commit-hooks.yaml`](#10-pre-commit-integration) | Three hooks: `m-fmt-check`, `m-fmt`, `m-lint`. Schema gated by `tests/test_pre_commit_hooks.py`. |
| 10 | 2 | Debugger | PARTIAL | ⏸️ Deferred | (none) | DAP-based debug adapter would be a separate, large engineering effort. Both engines ship `ZBREAK` at the engine level (Basic). Not on the near-term roadmap. |
| 11 | 3 | Documentation generator | MAJOR | ⏸️ Deferred | (none) | Tier 3. |
| 12 | 3 | Dependency management | MAJOR | ⏸️ Deferred | (none) | Tier 3. Blocked on a manifest-format design in `m-standard`. |
| 13 | 3 | Dead-code detection | MAJOR | 🟡 Partial | `m lint` (within-file) | Within-file unused-label detection comes free with the existing rule pack. Cross-routine "label not referenced anywhere" awaits Phase B's workspace symbol index. |
| 14 | 3 | Complexity metrics | MAJOR | ⏳ Planned | `m lint --rules=complexity` | Cyclomatic complexity per label is a natural extension of the AST visitor pattern. Not yet on the immediate roadmap. |
| 15 | 3 | Fixture management | MAJOR | ⏸️ Deferred | (TESTRUN library in m-tools) | The TESTRUN assertion library in `m-tools/routines/tests/TESTRUN.m` covers basic test-runner fixtures. A deeper fixture system is out of scope for `m-cli`. |
| 16 | 4 | Snapshot testing | MAJOR | ⏸️ Deferred | (none) | Tier 4. |
| 17 | 4 | Build / tasks | PARTIAL | ⏸️ Deferred | (project Makefile) | Both engines have *Basic* coverage via Makefile; no dedicated `m build` is planned. |
| 18 | 4 | Runtime / REPL | PARTIAL | ➖ Out of scope | (engine concern) | Engine-shipped (`ydb`, `iris terminal`); not a source-level concern. |
| 19 | 4 | Syntax check | PARTIAL | ✅ Done (implicit) | tree-sitter parse + M-XINDX-021 | Parse errors surface as `m lint` diagnostics; the parser is the syntax check. |
| 20 | 4 | Profiling | ENGINE-SPECIFIC | ➖ Out of scope | (engine concern) | IRIS-only (`^%SYS.MONLBL`); YDB lacks it. Not source-level. |
| 21 | 4 | Benchmarking | PARTIAL | ⏸️ Deferred | (none) | `$ZHOROLOG` is the engine primitive both vendors ship. |
| 22 | 4 | Security scan | MAJOR | ⏸️ Deferred | (none) | Tier 4. |
| 23 | 4 | Package publishing | MAJOR | ⏳ Planned (own repo only) | (PyPI for m-cli itself) | Publishing `m-cli` + `tree-sitter-m` to PyPI is a near-term unblocker for downstream pre-commit / CI usage. The broader "M package ecosystem" is aspirational. |
| — | — | Type checking | N/A | ➖ Not applicable | — | M is untyped. |
| — | — | Import analysis | N/A | ➖ Not applicable | — | M has no import system. |
| — | — | Environment check | N/A | ➖ Not applicable | — | No language-level equivalent to `pyenv` / `nvm`. |

**Cross-cutting features beyond the §7 categories** (not in the original gap matrix but explicitly requested by the editor-integration design decision in [§5.4 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#54-editor-integration-cadence)):

| Capability | Status | Module |
|---|:---:|---|
| LSP server (diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition) | ✅ Done | [`m lsp`](#65-m-lsp) — Stages 1+2+3+4+4b+B |
| VS Code extension wiring | ✅ Done | [`tree-sitter-m-vscode`](https://github.com/rafael5/tree-sitter-m-vscode) sibling repo; spawns `m lsp` on activation |
| Project configuration (`.m-cli.toml` / `[tool.m-cli]`) | ✅ Done | [`m_cli.config`](#7-project-configuration) |
| Workspace symbol index | ✅ Done | [`m_cli.workspace`](#5-architecture) — backs go-to-definition, find-references, workspace symbol search; refreshes via `didChangeWatchedFiles` and `didSave` |

---

## 4. Foundations

`m-cli` rests on three pre-existing artefacts described in [§2 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#2-foundation-already-in-place). It does not re-implement any of them.

| Foundation | What it provides | Why `m-cli` depends on it |
|---|---|---|
| **[`m-standard`](https://github.com/rafael5/m-standard)** | Machine-readable cross-vendor inventory of 949 M keyword forms (commands, intrinsic functions, ISVs) with provenance flags (`in_anno`, `in_ydb`, `in_iris`) | The `m_cli.lint._keywords` module loads command / ISV / function sets from m-standard's TSVs. Every linter rule that needs to know "is this a standard command?" reads from m-standard, never hardcoded lists. Hover / completion in the LSP serve m-standard's syntax format strings directly. |
| **[`tree-sitter-m`](https://github.com/rafael5/tree-sitter-m)** | Production tree-sitter grammar for M; 99.06% clean parse on the 39,330-routine VistA corpus | Every `m-cli` subcommand parses `.m` source through this grammar. The fmt round-trip relies on its lossless byte ranges; the linter walks its AST node types; test discovery searches for `label` / `formals` AST nodes; the LSP's structure helpers traverse it. |
| **VistA corpus** (`~/vista-meta/vista/vista-m-host/Packages` — 39,330 routines via [`WorldVistA/VistA-M`](https://github.com/WorldVistA/VistA-M)) | The largest open-source M codebase in the world | The validation gate for every `m-cli` release: `make vista` round-trips every routine through `m fmt`; `make lint-vista` runs the full XINDEX rule pack across the corpus. A tool that doesn't survive VistA isn't ready. |

The reasoning behind this layering (parser-shared, source-level, vendor-neutral) is in [§3.4 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#34-portability-across-m-implementations).

---

## 5. Architecture

```
src/m_cli/
├── cli.py                  # `m` dispatcher (argparse subcommands)
├── config.py               # .m-cli.toml / [tool.m-cli] loader (Phase A)
├── workspace.py            # Workspace symbol index (Phase B foundation)
├── parser.py               # tree-sitter-m wrapper, lru_cached Language/Parser
│
├── fmt/                    # `m fmt` — formatter
│   ├── cli.py              # argparse + file orchestration
│   ├── formatter.py        # round-trip pretty-printer (identity default)
│   └── rules.py            # canonical-layout transformations (opt-in)
│
├── lint/                   # `m lint` — linter
│   ├── cli.py              # argparse (--rules, --format, --error-on, --jobs)
│   ├── runner.py           # select_rules(), lint_source() with rule isolation
│   ├── rules.py            # all M-XINDX-NN rule implementations + register()
│   ├── _index.py           # NodeIndex single-pass dispatcher (perf)
│   ├── diagnostic.py       # Diagnostic dataclass + Severity enum
│   ├── output.py           # text / json / tap formatters
│   └── _keywords.py        # loads command / ISV / function sets from m-standard
│
├── test/                   # `m test` — test runner
│   ├── cli.py              # argparse (--list, --filter, --format)
│   ├── discovery.py        # tree-sitter-based suite + label discovery
│   ├── runner.py           # ydb subprocess + TESTRUN output parser
│   └── output.py           # text / tap / json formatters
│
├── watch/                  # `m watch` — file watcher
│   ├── cli.py              # argparse (--interval, --once, --filter)
│   ├── affinity.py         # changed-file → suite resolution
│   └── poller.py           # mtime-based change detection
│
└── lsp/                    # `m lsp` — Language Server
    ├── cli.py              # argparse + entry point
    ├── server.py           # pygls handlers (Stages 1+2+3+4+4b+B)
    ├── convert.py          # m-cli Diagnostic → LSP wire format
    ├── structure.py        # AST helpers — label + dot-block discovery
    └── symbols.py          # token resolution + keyword lookup
```

**Performance.** The lint VistA-corpus gate is **22.6 s on a 16-core host — 5.3× under the 120 s budget set in [§3.5 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#35-validation-gates)**. Two passes deliver this: the `NodeIndex` single-pass dispatcher (8.7×) and a `ProcessPoolExecutor` parallel runner (5.3× more).

---

## 6. Subcommand reference

Every subcommand exits with conventional codes:

- **0** — success
- **1** — diagnostics found at or above the configured severity threshold (lint), or files would change (`fmt --check`), or tests failed (`test`)
- **2** — usage error, invalid argument, or rule selection error

### 6.1 `m fmt`

Parse and pretty-print `.m` source files.

```bash
m fmt path/to/file.m              # rewrite in place (default)
m fmt --check Routines/           # exit 1 if anything would change (CI gate)
m fmt --diff Routines/            # print unified diff, no writes
m fmt --stdout single.m           # print formatted to stdout (one file)
m fmt --rules=canonical Routines/ # apply opt-in canonical-layout rules
```

**Default mode is identity:** the formatter parses then re-emits each file byte-for-byte where the parser's lossless ranges allow. `--rules=canonical` opts into transformations: `trim-trailing-whitespace`, `uppercase-command-keywords`. Both are validated for AST-preservation across the full VistA corpus before being added.

`make vista` (in the project root) runs the identity gate; `make vista-canonical` runs the canonical idempotency gate.

### 6.2 `m lint`

Run rule predicates over `.m` source.

```bash
m lint Routines/                    # default --rules=xindex
m lint --rules=all Routines/        # everything registered
m lint --rules=sac Routines/        # SAC-tagged rules only
m lint --rules=M-XINDX-013,M-XINDX-019 Routines/  # explicit list
m lint --error-on=warning Routines/ # exit 1 on warning or above
m lint --format=json Routines/      # CI-friendly output
m lint --jobs=8 Routines/           # parallel across 8 worker processes
```

**Rule families.** Rules carry stable IDs `M-XINDX-NN` mirroring XINDEX's numeric error codes 1:1. The 37 rules currently implemented cover the most common XINDEX checks; the 30 not yet ported require deeper analysis (data-flow / scope tracking) and are sequenced for follow-up phases. See [TODO.md](../TODO.md) for the explicit punch list.

**Severity.** Four levels mirror XINDEX's: FATAL / STANDARD / WARNING / INFO. `--error-on` threshold and `[lint.severity]` config overrides ([§7](#7-project-configuration)) let projects tune the gate without forking the rule registry.

**Output formats.** `text` (default), `json`, `tap`. JSON output includes a `fixer_id` field per diagnostic linking it to the `m fmt` rule that auto-fixes it.

### 6.3 `m test`

Discover and run M test suites.

```bash
m test routines/tests/                    # whole directory
m test routines/tests/HELLOTST.m          # single suite file
m test routines/tests/HELLOTST.m::tGreet  # single label
m test --format=tap routines/tests/       # TAP-13 output
m test --list routines/tests/             # list discovered tests, don't run
```

**Discovery is parser-aware.** Suites are `.m` files whose stem matches `[A-Z][A-Z0-9]*TST`; test labels match `t[A-Z][...]` and have formals containing `pass` and `fail` (the m-tools / TESTRUN convention). The first label in a file (the routine entry) is never a test, even when its name accidentally matches. Discovery is tree-sitter-based, not regex.

**Runner is YottaDB-specific.** Whole-suite runs use `ydb -run ^SUITE`; single-label runs use `ydb -run %XCMD ...`. The runner shells out via an injectable `RunnerFn` callable, so unit tests don't need a live ydb.

**Env composition.** `m_cli.test.runner._build_env` honours an existing `ydb_routines` if the shell exports one; otherwise it derives one from the suite's parent directory plus a sibling `routines/` if present. `$YDB` overrides the ydb binary location, falling back to `$ydb_dist/ydb`, then plain `ydb` on PATH.

**Output formats.** `text` (default, human), `tap` (TAP v13 — one point per parsed assertion), `json`.

### 6.4 `m watch`

Auto-rerun affected suites on file save.

```bash
m watch routines/tests/        # poll, re-run on save
m watch --interval=1.0         # custom poll interval (seconds)
m watch --once                 # run the initial pass and exit
```

**Polling, not inotify.** Periodic `os.stat` (default 0.5 s) keeps the dependency tree minimal at the cost of latency. Pure Python — no `watchdog` / `entr` / `inotify` dependency.

**Affinity rule.** `<X>.m` source change → suite `<X.upper()>TST.m` if it exists; otherwise every suite re-runs (defensive default). Suite-file edits map to themselves only.

### 6.5 `m lsp`

Run the m-cli Language Server over stdio.

```bash
m lsp                              # start the server (editors invoke this)
m lsp --rules=all                  # override default xindex rule filter
m lsp --verbose                    # DEBUG-level logging on stderr
```

The server is invoked by editors (VS Code, Vim/Neovim with LSP, Emacs eglot/lsp-mode, …) — humans rarely call `m lsp` directly. Optional dependency: `pip install 'm-cli[lsp]'` adds `pygls` + `lsprotocol`. Without the extra, `m lsp` exits with a friendly install hint.

**Capabilities advertised:**

| Method | Stage | Behaviour |
|---|---|---|
| `textDocument/publishDiagnostics` | 1 | On open / change / save, push linter diagnostics. Severity-mapped. `data.fixer_id` carries the auto-fixer id when a rule has one. |
| `textDocument/formatting` | 2 | Returns a single full-document `TextEdit` from `format_source(canonical_rules())`. Empty list when already canonical or parse errors. |
| `textDocument/codeAction` | 3 | Quick Fix per fixer-id. Multiple diagnostics of the same kind collapse to one click; the fmt rule runs file-wide. |
| `textDocument/hover` | 4 | Markdown for command / ISV / intrinsic function under cursor: canonical name, abbreviation, syntax format, standard status. |
| `textDocument/completion` | 4 | Full M keyword universe (323 items) as `CompletionItem`s. Client filters by prefix. |
| `textDocument/documentSymbol` | 4b | Outline view — one `SymbolKind.Function` per label. |
| `textDocument/codeLens` | 4b | "▶ Run test \<label\>" lens above each `t<UpperCase>(pass,fail)` test label. Lens carries an `m-cli.runTest` command for the editor extension to wire up. |
| `textDocument/foldingRange` | 4b | Fold each label's body and each contiguous dot-block. |
| `textDocument/signatureHelp` | 4b | Inside `$FN(...)`, return the m-standard syntax format. Trigger chars `(` and `,`. |
| `textDocument/documentHighlight` | 4b | Same-file occurrences of the identifier under cursor. |
| `textDocument/definition` | B | Resolve `LABEL^ROUTINE`, `^ROUTINE`, label-only references via the workspace symbol index. |
| `textDocument/references` | B | Find every call site that targets `LABEL^ROUTINE` (works from a reference or from the declaration). Honours `includeDeclaration`. |
| `workspace/symbol` | B | Fuzzy symbol search across the workspace (Ctrl+T in VS Code). Case-insensitive substring match against label or routine name; capped at 1000 results. |
| `workspace/didChangeWatchedFiles` | B | Incremental index updates when files are created / changed / deleted on disk. The workspace symbol index also refreshes per-file on `didSave` for in-editor edits. |

---

## 7. Project configuration

`m fmt`, `m lint`, and `m lsp` all read project config on startup. Discovery walks up from the working directory looking for:

1. **`.m-cli.toml`** — preferred, project-local
2. **`pyproject.toml`** with a `[tool.m-cli]` table — fallback for projects that already use Python packaging conventions

Walking stops at the nearest `.git` boundary so configs in unrelated parent directories don't leak in.

**Schema:**

```toml
[lint]
rules = "xindex"               # rule filter (same syntax as --rules)
disable = ["M-XINDX-013"]      # rule ids to skip after selection

[lint.severity]
"M-XINDX-019" = "warning"      # remap per-rule severity
                               # values: "fatal" | "standard" | "warning" | "info"

[fmt]
rules = "canonical"            # canonical, none (identity), or comma-separated rule ids
```

**Resolution order:** defaults → config → CLI flag (CLI always wins). Unknown keys are ignored silently to keep forward compatibility cheap. Invalid values (bad severity name, `disable` not a list) raise on load.

The LSP loads the config from `Path.cwd()` at spawn time. VS Code spawns subprocesses with `cwd = workspace folder`, so this finds the workspace's project config without needing the `initialize` rootUri.

---

## 8. Editor integration (VS Code)

`m-cli`'s LSP is wired into VS Code via the sibling extension repo [`tree-sitter-m-vscode`](https://github.com/rafael5/tree-sitter-m-vscode) (installed as `rafael5.tree-sitter-m-vscode`). The extension:

- Provides syntax highlighting via TextMate grammar + tree-sitter semantic tokens
- Spawns `m lsp` on activation via `vscode-languageclient` (stdio transport)
- Registers the `m-cli.runTest` command that the LSP's CodeLens uses to run individual tests in a reusable terminal

**User settings:**

| Setting | Default | Purpose |
|---|---|---|
| `m-cli.enabled` | `true` | Master on/off switch for the LSP |
| `m-cli.path` | `m` | Path to the `m` binary. Set to `~/projects/m-cli/.venv/bin/m` for venv installs. |
| `m-cli.args` | `[]` | Extra args passed to `m lsp`. E.g. `["--rules", "all"]` to broaden diagnostics. |
| `m-cli.trace.server` | `off` | Set to `messages` or `verbose` to log LSP wire traffic to the Output panel. |

**Restart command:** "M (MUMPS): Restart Language Server" in the Command Palette respawns `m lsp` after settings changes or m-cli upgrades.

**Detailed self-trial guide:** see the extension's `docs/lsp-setup.md`.

---

## 9. Library API for downstream tools

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
from m_cli.config import Config, load_config, find_config  # project config
from m_cli.workspace import (              # workspace symbol index
    WorkspaceIndex, build_index, reference_at, LabelLocation, Reference,
)
```

Anything in `__all__` is locked: future internal refactors keep these importable. Internal helpers (rule check fns, AST walkers, registry internals) are not part of the public surface and may move. The `tests/test_library_api.py` smoke gate enforces this.

**Lint → fmt fixer linkage.** Each lint `Rule` carries an optional `fixer_id` pointing to an `m fmt` rule that auto-fixes the diagnostic. Today: `M-XINDX-013 ↔ trim-trailing-whitespace` and `M-XINDX-047 ↔ uppercase-command-keywords`. The link surfaces in `--format=json` output (`"fixer_id": ...` per diagnostic) and via `m_cli.lint.fixer_for(rule_id)`. The LSP wrapper uses this to expose Quick Fix code actions; new pairings are pinned by `tests/test_lint_fixer_linkage.py`.

---

## 10. Pre-commit integration

`m-cli` exports a [pre-commit](https://pre-commit.com) hook scaffold so downstream M projects can gate every commit on `m fmt --check` and `m lint --error-on=fatal` without writing any boilerplate.

Hooks: `m-fmt-check`, `m-fmt`, `m-lint`. Schema is gated by `tests/test_pre_commit_hooks.py`.

See [pre-commit.md](pre-commit.md) for downstream usage examples (both `language: repo` style and `language: system` style).

---

## 11. Validation gates

Per [§3.5 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#35-validation-gates), every `m-cli` release passes:

| Gate | Command | What it proves |
|------|---------|----------------|
| Unit tests | `make test` | All source-level invariants hold (rule isolation, parser caching, output formats, etc.) |
| Lint | `make lint` | `ruff check` clean across `src/` and `tests/` |
| Type check | `make mypy` | `mypy src/` clean |
| Coverage threshold | `make cov` | Coverage ≥ 70% (currently ~80%) |
| Full check gate | `make check` | All four above, run together — what CI gates on |
| **VistA round-trip** | `make vista` | `m fmt` (identity) is byte-for-byte clean over 38,954 VistA routines (376 routines fail to parse — same set as `tree-sitter-m`'s known boundary, see `project_tree_sitter_m_vista_corpus.md` memory). |
| **VistA canonical layout** | `make vista-canonical` | `m fmt --rules=canonical` is idempotent + AST-preserving over the corpus. |
| **VistA lint baseline** | `make lint-vista` | Full XINDEX rule pack runs over the corpus in 22.6 s; findings are byte-identical against the prior baseline. |

A change that breaks any of these is a release blocker.

---

## 12. Roadmap & open work

The strategic phases beyond Tier 1 (in dependency order):

| Phase | Capability | Status | Why |
|-------|------------|:---:|---|
| **A** | Project configuration files (`.m-cli.toml` / `[tool.m-cli]`) | ✅ Done | Lets projects tune lint / fmt without touching the rule registry. |
| **B (first slice)** | Workspace symbol index → `textDocument/definition` | ✅ Done | One foundation unlocks go-to-def, references, workspace symbol search, and the deferred cross-routine XINDEX rules (M-XINDX-004 et al.). |
| B (follow-ups) | `textDocument/references`, `workspace/symbol`, incremental `didChangeWatchedFiles` updates | ⏳ Planned | Each is a small handler over the existing index. |
| **C** | `m coverage` and `m trace` | ⏳ Planned | Wraps `m test` with YDB tracing. Closes the testing feedback loop. |
| **D** | The 30 remaining XINDEX rules requiring data-flow analysis | ⏸️ Deferred | Far easier *after* Phase B's index exists. |
| — | Publishing `m-cli` + `tree-sitter-m` to PyPI | ⏳ Planned | Unblocks the `language: repo` pre-commit style and downstream `pip install m-cli`. Held until the library API has had more soak time. |
| — | DAP debugger integration | ⏸️ Deferred | Tier 2 capability; substantial engineering on its own. |

The TODO list in [TODO.md](../TODO.md) tracks the per-session punch list.

---

## 13. Design principles

Drawn from [§3.1 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#31-principles), with `m-cli`-specific elaborations:

1. **Build in dependency order.** Formatter unblocks linter (linter rules can assume canonical layout). Test runner unblocks single-test selection and the watcher. Workspace index unblocks go-to-definition AND cross-routine lint rules.
2. **Ship each tool independently.** No subcommand waits for the next; each is usable on the day it's released. The library API is locked so downstream tooling can integrate any of them in isolation.
3. **Validate against VistA on every release.** A `m-cli` change that doesn't survive `make vista` / `make lint-vista` is unfinished work.
4. **Source-level by construction.** Every subcommand except `m test` is engine-neutral — runs on `.m` text via tree-sitter-m, no dependency on any M engine. `m test`'s engine touchpoint is intentionally pluggable (currently YottaDB; IRIS adapter is a community-contribution path).
5. **Stable JSON output from the first release of each tool.** Editor integration, CI dashboards, and downstream tooling all consume the same wire format.
6. **VS Code is the primary editor target, but every other LSP-aware editor works for free.** All editor integration goes through `m lsp`'s standard stdio LSP — no VS Code-specific surface in `m-cli` proper.
7. **`m <subcommand>` is universal.** Subcommands mirror the `git` / `cargo` / `go` convention. The legacy `y*` shell scripts in `m-tools/bin/` are kept only as references; new tooling does not adopt that prefix.

---

*This guide tracks the state of `m-cli` as of 2026-04-27. For the per-session changelog, see `git log`. For strategic context, the canonical references are [m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md) and [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md).*
