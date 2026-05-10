# m-cli — Comprehensive Guide

**Document type:** Reference + roadmap
**Scope:** Everything a developer or strategic reader needs to understand `m-cli`'s purpose, current state, and place in the M (MUMPS) tooling ecosystem.
**Companion documents:**
- [m-tools / m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md) — vendor-neutral inventory of the M-tooling gap, the strategic justification for `m-cli`'s existence
- [m-tools / m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md) — the focused Tier 1 strategic plan that `m-cli` implements
- [pre-commit.md](pre-commit.md) — downstream pre-commit integration

---

## Table of Contents

- [1. Introduction](#1-introduction)
  - [1.1 What `m-cli` is](#11-what-m-cli-is)
  - [1.2 How it was built — the dependency sequence](#12-how-it-was-built--the-dependency-sequence)
  - [1.3 Engine support](#13-engine-support)
- [2. Why it exists — the M tooling gap](#2-why-it-exists--the-m-tooling-gap)
- [3. Where `m-cli` fits in the remediation roadmap](#3-where-m-cli-fits-in-the-remediation-roadmap)
  - [3.1 The four-tier framework](#31-the-four-tier-framework)
  - [3.2 Coverage matrix](#32-coverage-matrix)
- [4. Foundations](#4-foundations)
- [5. Architecture](#5-architecture)
- [6. Subcommand reference](#6-subcommand-reference)
  - [6.1 `m fmt`](#61-m-fmt)
  - [6.2 `m lint`](#62-m-lint)
    - [6.2.1 Profiles](#621-profiles)
    - [6.2.2 Two-axis severity + category](#622-two-axis-severity--category)
    - [6.2.3 The XINDEX rule pack (M-XINDX-NN)](#623-the-xindex-rule-pack-m-xindx-nn)
    - [6.2.4 The modernization track (M-MOD-NN)](#624-the-modernization-track-m-mod-nn)
    - [6.2.5 Path-sensitive rules (Phase 7)](#625-path-sensitive-rules-phase-7)
    - [6.2.6 Taint analysis (Phase 9)](#626-taint-analysis-phase-9)
    - [6.2.7 Configurable thresholds](#627-configurable-thresholds)
    - [6.2.8 Engine targeting](#628-engine-targeting)
    - [6.2.9 Inline disable directives](#629-inline-disable-directives)
    - [6.2.10 Baseline mode](#6210-baseline-mode)
    - [6.2.11 Auto-fix linkage with `m fmt`](#6211-auto-fix-linkage-with-m-fmt)
  - [6.3 `m test`](#63-m-test)
  - [6.4 `m coverage`](#64-m-coverage)
  - [6.5 `m watch`](#65-m-watch)
  - [6.6 `m lsp`](#66-m-lsp)
  - [6.7 `m doctor`](#67-m-doctor)
  - [6.8 `m new`](#68-m-new)
  - [6.9 `m ci init`](#69-m-ci-init)
  - [6.10 `m run`](#610-m-run)
  - [6.11 `m build`](#611-m-build)
  - [6.12 `m doc`](#612-m-doc)
- [7. Project configuration](#7-project-configuration)
- [8. Editor integration (VS Code)](#8-editor-integration-vs-code)
- [9. Library API for downstream tools](#9-library-api-for-downstream-tools)
- [10. Pre-commit integration](#10-pre-commit-integration)
- [11. Validation gates](#11-validation-gates)
- [12. Roadmap & open work](#12-roadmap--open-work)
- [13. Design principles](#13-design-principles)

---

## 1. Introduction

### 1.1 What `m-cli` is

`m-cli` is a vendor-neutral, source-level developer toolchain for the M (MUMPS) language, exposed as a single `m` binary with subcommands:

```
m fmt       — format M source
m lint      — lint M source (XINDEX rule pack + modernization track + taint analysis)
m test      — discover and run M test suites against YottaDB
m coverage  — line- and label-level coverage reports
m watch     — auto-rerun affected suites on file save
m lsp       — Language Server (stdio) for editor integration
m doctor    — diagnose the M development environment
m new       — scaffold a new M project (zero-deps starter)
m ci init   — emit a GitHub Actions workflow running the four gates
m run       — thin `ydb -run ENTRYREF` wrapper
m build     — warm-compile a directory of M routines
m doc       — extract `@summary` annotations into Markdown / HTML
```

`m-cli` is the canonical implementation of the **Tier 1 deliverable** described in [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md), now extended with the Tier 2 quality-gate features (`m coverage`, pre-commit hooks, style linting) and an opinionated modernization track (the M-MOD-NN rule family — 35 rules covering complexity, concurrency, transaction integrity, engine portability, code-style, and security/taint). It is the active replacement for the legacy `y*` shell scripts in `~/projects/m-tools/bin/` (kept only as references).

### 1.2 How it was built — the dependency sequence

`m-cli` did not appear in isolation. Each piece rests on a sequence of foundational projects, chosen so the next layer could stay vendor-neutral and source-only. Built in dependency order:

```
gap analysis  →  Tier 1 plan  →  tree-sitter-m  →  m-standard  →  VistA corpus  →  m-cli
   strategy        scope         parsing          semantics      validation       implementation
```

**1. The gap analysis** — [m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md). A vendor-neutral inventory of the developer toolchain that mainstream languages (Python, JavaScript/TypeScript, Go, Rust, Java) take for granted, benchmarked against InterSystems IRIS and YottaDB. The headline finding: **22 of 23 applicable categories are common gaps** — both engines ship None or Basic support for source-level developer tooling. The strategic insight: a **single vendor-neutral, source-level tool** built on a shared parser foundation could fill each gap for both engines simultaneously.

**2. The Tier 1 plan** — [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md). A focused five-tool plan addressing the highest-impact developer-loop gaps: formatter, linter, test runner, single-test selection, file watcher. Defined the architectural principles (vendor-neutral, source-level, validate against VistA on every release) and the validation gates that gate every release.

**3. [`tree-sitter-m`](https://github.com/m-dev-tools/tree-sitter-m)** — the production tree-sitter grammar for M. **99.06% clean parse** on the 39,330-routine VistA corpus. The shared parser. Every `m-cli` subcommand parses `.m` source through this grammar — the formatter relies on its lossless byte ranges; the linter walks its AST node types; the test runner searches for `label` and `formals` AST nodes; the LSP traverses its structure helpers; the Phase 7 control-flow graph builder reads its `command` and `command_sequence` nodes.

**4. [`m-standard`](https://github.com/m-dev-tools/m-standard)** — a machine-readable cross-vendor inventory of **949 M keyword forms** (commands, intrinsic functions, intrinsic special variables) with provenance flags (`in_anno`, `in_ydb`, `in_iris`). Every linter rule that needs to know "is this a standard command?" reads from m-standard, never hardcoded lists. Hover and completion in the LSP serve m-standard's syntax format strings directly. Engine-aware portability rules (M-MOD-021..023) consult its `standard_status` column (`ansi`, `ydb`, `iris`, `ydb-and-iris`, `vista`).

**5. The VistA corpus** — [WorldVistA/VistA-M](https://github.com/WorldVistA/VistA-M). The 39,330-routine open-source M codebase that is the largest in the world. The validation gate for every `m-cli` release: `make vista` round-trips every routine through `m fmt`; `make lint-vista` runs the full XINDEX rule pack across the corpus in 22.6 s on 16 cores. **A tool that doesn't survive VistA isn't ready.** The supplementary `make lint-modern` gate runs the M-MOD-NN track over a curated 4,215-routine non-VistA corpus catalogued in [docs/plans/m-corpus-catalog.md](plans/m-corpus-catalog.md) (YottaDB/YDBTest, mgsql, YDBOcto-aux, EWD, M-Web-Server) — calibrating the modernization rules against contemporary non-VA M code.

**6. `m-cli`** — this project. The Tier 1 deliverable, plus the Tier 2 quality-gate features it laid the groundwork for, plus the M-MOD-NN modernization track (Phases 1–8 of the linting roadmap), plus the Phase 7 data-flow infrastructure (per-label CFG, definite-assignment analyzer, and per-resource state analyzers for LOCK / TSTART / $ETRAP / $TEST), plus the Phase 9 taint-analysis MVP (M-MOD-036 — untrusted data → indirection sinks), plus the LSP server that wraps it all for editor integration.

For per-foundation detail (what each project provides and why `m-cli` depends on it), see §4 below.

### 1.3 Engine support

Source-level tools (`m fmt`, `m lint`, `m lsp`) are **engine-neutral by design** — they consume `.m` text via the shared parser regardless of which M engine the code runs on. Engine-aware lint rules (M-MOD-021..023) read m-standard's allowlists when configured with `--target-engine=yottadb` or `--target-engine=iris`; the default `any` keeps the linter portable.

Runtime tools (`m test`, `m coverage`) currently target **YottaDB**; an IRIS adapter is a deliberate future concern (the runner shells out via an injectable callable, so the IRIS path is a contained extension). See [§3.4 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#34-portability-across-m-implementations) for the layering reasoning.

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
| 2 | 1 | Linter (logic) | MAJOR | ✅ Done | [`m lint`](#62-m-lint) | **77 rules** across two families — 42 from XINDEX (legacy VA Toolkit port) and 35 from the **M-MOD-NN modernization track** (greenfield). Path-sensitive analyzers (Phase 7) graduate the LOCK / TSTART / $ETRAP / $TEST checks to per-path correctness. Phase 9 taint MVP (M-MOD-036) flags untrusted data flowing into `@expr` / `XECUTE` sinks. Seven profiles bundle the rules by audience (`default` / `modern` / `pedantic` / `pythonic` / `xindex` / `vista` / `sac` / `all`). Two-axis severity (ERROR / WARNING / STYLE / INFO) + nine-category enum (bug / security / concurrency / performance / style / complexity / documentation / portability / modernization). Inline `; m-lint: disable=RULE` directives. Configurable thresholds. Engine targeting (`--target-engine=any|yottadb|iris`). Baseline mode for adopting on legacy code. |
| 3 | 1 | Formatter | MAJOR | ✅ Done | [`m fmt`](#61-m-fmt) | Identity formatter round-trips 99.04% of VistA byte-for-byte. `--rules=canonical` adds two hygiene transformations (trim trailing whitespace, uppercase command keywords). `--rules=pythonic` and `--rules=compact` translate between VistA-compact (`S X=1 W $L(X),$T`) and canonical-name (`SET X=1 WRITE $LENGTH(X),$TEST`) forms via 6 case-preserving translation rules. Idempotent + AST-preserving over 38,954 routines. |
| 4 | 1 | Single-test selection | MAJOR | ✅ Done | `m test FILE.m::tLabel` | Folded into Step 3. |
| 5 | 1 | Test watcher | MAJOR | ✅ Done | [`m watch`](#64-m-watch) | Polling-based (no inotify dependency). Source-to-suite affinity: `foo.m` → `FOOTST.m`. |
| 6 | 2 | CI script | PARTIAL | ✅ Done | [`m ci init`](#69-m-ci-init) | Phase 3a: emits `.github/workflows/m-ci.yml` running `m fmt --check` + `m lint --error-on=fatal` + `m test` + `m coverage --format=lcov` against the published YottaDB base image. Downstream M projects also get a pre-commit hook scaffold via [.pre-commit-hooks.yaml](#10-pre-commit-integration). |
| 7 | 2 | Coverage | MAJOR | ✅ Done | `m coverage` (Phase C) | Runner uses YDB's `view "TRACE"`; offset semantics decoded — third subscript N from a label maps to absolute line `label_decl_line + N`. Label-level 85/123 = 69.1% on m-tools (byte-identical to `ycover`); line-level 340/637 = 53.4%. Output: `text` (default), `text --lines`, `json`, `lcov` (genhtml / Codecov / Coveralls). |
| 8 | 2 | Linter (style) | MAJOR | ✅ Done | `m lint --rules=sac` | Style rules ride alongside logic rules. Severity-tagged (FATAL / STANDARD / WARNING / INFO) so projects can gate selectively via `--error-on=...` or [`[lint.severity]` config overrides](#7-project-configuration). |
| 9 | 2 | Pre-commit hooks | MAJOR | ✅ Done | [`.pre-commit-hooks.yaml`](#10-pre-commit-integration) | Three hooks: `m-fmt-check`, `m-fmt`, `m-lint`. Schema gated by `tests/test_pre_commit_hooks.py`. |
| 10 | 2 | Debugger | PARTIAL | ⏸️ Deferred | (none) | DAP-based debug adapter would be a separate, large engineering effort. Both engines ship `ZBREAK` at the engine level (Basic). Not on the near-term roadmap. |
| 11 | 3 | Documentation generator | MAJOR | ✅ Done | [`m doc`](#612-m-doc) | Phase 3a: extracts `LABEL ; @summary <text>` (M-MOD-028) and the VistA version stub (line 2 `;;<v>;<pkg>;;<date>;<build>`) into Markdown or HTML. Reuses `tree-sitter-m`'s label discovery; one entry per routine + per labeled extrinsic / subroutine. |
| 12 | 3 | Dependency management | MAJOR | ⏸️ Deferred | (none) | Tier 3. Blocked on a manifest-format design in `m-standard`. |
| 13 | 3 | Dead-code detection | MAJOR | ✅ Done | `m lint` | M-XINDX-049 (unused-label) cross-routine via the workspace symbol index. M-XINDX-009 (dead-code-after-QUIT) intra-routine. M-MOD-024 (read of local before any SET on every prior path) via Phase 7 definite-assignment. |
| 14 | 3 | Complexity metrics | MAJOR | ✅ Done | `m lint --rules=modern` | M-MOD-005 (cyclomatic), M-MOD-006 (cognitive), M-MOD-007 (dot-block depth), M-MOD-008 (argument count), M-MOD-009 (commands-per-line), all per-label. Configurable thresholds. |
| 15 | 3 | Fixture management | MAJOR | ⏸️ Deferred | (TESTRUN library in m-tools) | The TESTRUN assertion library in `m-tools/routines/tests/TESTRUN.m` covers basic test-runner fixtures. A deeper fixture system is out of scope for `m-cli`. |
| 16 | 4 | Snapshot testing | MAJOR | ⏸️ Deferred | (none) | Tier 4. |
| 17 | 4 | Build / tasks | PARTIAL | ✅ Done | [`m build`](#611-m-build) | Phase 3a: walks `.m` files and runs `ydb <file>` on each — the engine compiles routines to sibling `.o` files. `--check` mode cleans up the `.o` byproducts so CI gates that just want a "does this compile?" check don't pollute the working tree. |
| 18 | 4 | Runtime / REPL | PARTIAL | ➖ Out of scope | (engine concern) | Engine-shipped (`ydb`, `iris terminal`); not a source-level concern. |
| 19 | 4 | Syntax check | PARTIAL | ✅ Done (implicit) | tree-sitter parse + M-XINDX-021 | Parse errors surface as `m lint` diagnostics; the parser is the syntax check. |
| 20 | 4 | Profiling | ENGINE-SPECIFIC | ➖ Out of scope | (engine concern) | IRIS-only (`^%SYS.MONLBL`); YDB lacks it. Not source-level. |
| 21 | 4 | Benchmarking | PARTIAL | ⏸️ Deferred | (none) | `$ZHOROLOG` is the engine primitive both vendors ship. |
| 22 | 4 | Security scan | MAJOR | 🟡 Partial | `m lint --rules=M-MOD-036` | Taint analysis MVP (Phase 9): tracks untrusted data (`READ` input, public-label formals) through assignment chains and flags any flow into an indirection sink (`@expr`, `S @expr=...`, `D @expr`, `G @expr`, `XECUTE`). Cross-routine taint propagation is the remaining stretch piece. |
| 23 | 4 | Package publishing | MAJOR | ➖ Out of scope | (none) | Distribution of `m-cli` and `tree-sitter-m` is git-clone-and-install; no package-registry plan. The broader "M package ecosystem" is aspirational. |
| — | — | Type checking | N/A | ➖ Not applicable | — | M is untyped. |
| — | — | Import analysis | N/A | ➖ Not applicable | — | M has no import system. |
| — | — | Environment check | N/A | ➖ Not applicable | — | No language-level equivalent to `pyenv` / `nvm`. |

**Cross-cutting features beyond the §7 categories** (not in the original gap matrix but explicitly requested by the editor-integration design decision in [§5.4 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#54-editor-integration-cadence)):

| Capability | Status | Module |
|---|:---:|---|
| LSP server (diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition) | ✅ Done | [`m lsp`](#65-m-lsp) — Stages 1+2+3+4+4b+B |
| VS Code extension wiring | ✅ Done | [`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode) sibling repo; spawns `m lsp` on activation |
| Project configuration (`.m-cli.toml` / `[tool.m-cli]`) | ✅ Done | [`m_cli.config`](#7-project-configuration) |
| Workspace symbol index | ✅ Done | [`m_cli.workspace`](#5-architecture) — backs go-to-definition, find-references, workspace symbol search; refreshes via `didChangeWatchedFiles` and `didSave` |
| Environment diagnostics (Phase 3a) | ✅ Done | [`m doctor`](#67-m-doctor) — `$ydb_dist`, `$ydb_routines`, parser, m-standard TSVs, `ydb` binary; OK / WARN / FAIL with actionable hints |
| Project scaffolder (Phase 3a) | ✅ Done | [`m new`](#68-m-new) — produces a self-contained project that passes `m fmt --check && m lint && m test && m coverage` on a clean clone |
| Run wrapper (Phase 3a) | ✅ Done | [`m run`](#610-m-run) — thin `ydb -run ENTRYREF` invocation with `$ydb_routines` composition and rc passthrough |

---

## 4. Foundations

`m-cli` rests on three pre-existing artefacts described in [§2 of m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md#2-foundation-already-in-place). It does not re-implement any of them.

| Foundation | What it provides | Why `m-cli` depends on it |
|---|---|---|
| **[`m-standard`](https://github.com/m-dev-tools/m-standard)** | Machine-readable cross-vendor inventory of 949 M keyword forms (commands, intrinsic functions, ISVs) with provenance flags (`in_anno`, `in_ydb`, `in_iris`) | The `m_cli.lint._keywords` module loads command / ISV / function sets from m-standard's TSVs. Every linter rule that needs to know "is this a standard command?" reads from m-standard, never hardcoded lists. Hover / completion in the LSP serve m-standard's syntax format strings directly. |
| **[`tree-sitter-m`](https://github.com/m-dev-tools/tree-sitter-m)** | Production tree-sitter grammar for M; 99.06% clean parse on the 39,330-routine VistA corpus | Every `m-cli` subcommand parses `.m` source through this grammar. The fmt round-trip relies on its lossless byte ranges; the linter walks its AST node types; test discovery searches for `label` / `formals` AST nodes; the LSP's structure helpers traverse it. |
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
m fmt --rules=canonical Routines/      # SAC hygiene: trim + uppercase
m fmt --rules=pythonic Routines/       # expand abbreviations: S→SET, $L→$LENGTH
m fmt --rules=pythonic-lower Routines/ # same but lowercase: set, $length
m fmt --rules=compact Routines/        # compact canonical names: SET→S, $LENGTH→$L
```

**Default mode is identity:** the formatter parses then re-emits each file byte-for-byte where the parser's lossless ranges allow.

**`--rules=canonical`** is the SAC hygiene preset: `trim-trailing-whitespace` + `uppercase-command-keywords`. Both validated for AST-preservation across the full VistA corpus.

**`--rules=pythonic` / `--rules=pythonic-lower` / `--rules=compact`** are the Phase A translation presets. `pythonic` expands abbreviations to canonical names (`S X=1 W $L(X),$T` → `SET X=1 WRITE $LENGTH(X),$TEST`) for readers coming from Python or other modern languages. `pythonic-lower` is the same but produces lowercase output (`set X=1 write $length(X),$test`) for projects that prefer PEP-8-style keyword casing. `compact` is the inverse of `pythonic`. Nine rules ship under these presets:

| Rule ID | Direction | Example |
|---------|-----------|---------|
| `expand-command-keywords` | abbrev → canonical | `S` → `SET`, `Q` → `QUIT` |
| `compact-command-keywords` | canonical → abbrev | `SET` → `S`, `QUIT` → `Q` |
| `lowercase-command-keywords` | upper → lower | `SET` → `set`, `S` → `s` |
| `expand-intrinsic-functions` | abbrev → canonical | `$L` → `$LENGTH`, `$E` → `$EXTRACT` |
| `compact-intrinsic-functions` | canonical → abbrev | `$LENGTH` → `$L`, `$EXTRACT` → `$E` |
| `lowercase-intrinsic-functions` | upper → lower | `$LENGTH` → `$length` |
| `expand-special-variables` | abbrev → canonical | `$T` → `$TEST`, `$H` → `$HOROLOG` |
| `compact-special-variables` | canonical → abbrev | `$TEST` → `$T`, `$HOROLOG` → `$H` |
| `lowercase-special-variables` | upper → lower | `$TEST` → `$test` |

Expand/compact rules are case-preserving (`s` → `set`); lowercase rules unconditionally fold the keyword bytes (`SET` → `set`, `S` → `s`). The `pythonic-lower` preset chains lowercase-then-expand: lowercase first so the case-preserving expand sees a lowercase token and emits a lowercase canonical. All rules are idempotent, AST-shape-preserving, and load their abbrev↔canonical mappings from m-standard's `keyword_records()`. Translation is *normalizing* — mixed-form input (some `NEW`, some `N`) collapses to one form. The round-trip property holds on already-normalized input only: `compact(pythonic(compact(src))) == compact(src)`.

PEP-8-style operator spacing (`S X = 1`) and one-command-per-line splitting are intentionally *not* offered as fmt rules: the first breaks the M parser (whitespace is M's argument terminator), the second violates the AST-shape-preservation contract. The lint rule `M-MOD-009` flags multi-command lines for manual fix.

`make vista` (in the project root) runs the identity gate; `make vista-canonical` runs the canonical idempotency gate.

### 6.2 `m lint`

Run rule predicates over `.m` source. The lint engine is **engine- and dialect-neutral**; opinionated rule sets ride on top as named **profiles**.

```bash
m lint Routines/                          # default profile (curated daily lint)
m lint --rules=modern Routines/           # full M-MOD modernization track
m lint --rules=xindex,vista Routines/     # legacy VistA Toolkit checks
m lint --rules=pythonic Routines/         # Python-style strict review
m lint --rules=M-MOD-024,M-MOD-036 Routines/  # explicit list
m lint --error-on=warning Routines/       # exit 1 on warning or above
m lint --format=json Routines/            # CI-friendly output
m lint --jobs=8 Routines/                 # parallel across 8 worker processes
m lint --target-engine=yottadb Routines/  # unlock YDB-specific allowlists
m lint --threshold cyclomatic=10 Routines/  # tune a complexity ceiling
m lint --list-profiles                    # show the live profile list
```

**Output formats.** `text` (default, human), `json` (CI / downstream tooling — stable schema, includes `fixer_id` linkage), `tap` (TAP-13 for test-runner pipelines).

#### 6.2.1 Profiles

| Profile | Rules | Use when |
|---------|------:|----------|
| `default` | 28 | **Daily-lint baseline.** The curated M-MOD subset minus the four loud pedantic rules and minus rules superseded by Phase 7 path-sensitive variants. ~9 findings per routine on the 4K-routine non-VA corpus. This is what `m lint` runs when no `--rules` flag is given. |
| `modern` | 35 | **Strict review pass.** Full M-MOD-NN track including the four pedantic style rules. Heavy on legacy code; appropriate when reviewing one routine carefully. |
| `pedantic` | 4 | M-MOD-009 (commands-per-line), M-MOD-028 (label-docstring), M-MOD-031 (magic-numbers), M-MOD-032 (single-letter-vars). Use to focus a style sweep. |
| `pythonic` | 35 | Same selection as `modern` plus tighter thresholds (line=100, commands-per-line=1, cyclomatic=10, …) for projects coming from PEP-8 conventions. |
| `xindex` | 34 | **Engine-neutral subset of VA's `^XINDEX` Toolkit.** Mirrors XINDEX's numeric error codes 1:1. Use this for VistA-style discipline. |
| `vista` | 8 | **VA Kernel-specific** (OPEN→`^%ZIS`, HALT→`^XUSCLEAN`, banner format). Pure false positives outside VistA — opt in only when linting VistA. |
| `sac` | 23 | Portable VA SAC subset minus the VistA-Kernel mandates. |
| `all` | 67 | Everything registered, with replaces-suppression applied so legacy ↔ modern pairs don't double-report. Diagnostic-only. |

**Combining:** `--rules` takes a comma-separated list mixing profiles and rule IDs:

```bash
m lint --rules=xindex,vista Routines/         # VA shops — full VistA flavour
m lint --rules=default,M-XINDX-013 Routines/  # daily set + one extra rule
m lint --rules=sac,modern Routines/           # union of both profiles
```

When a rule R declares `replaces=("S",)` and both R and S end up selected, S is suppressed automatically — no double-reporting.

#### 6.2.2 Two-axis severity + category

Every rule declares **both** a severity (how strictly to enforce) and a category (what kind of issue it catches). The two are orthogonal — filter by either.

**Severity** (CI gate threshold via `--error-on`):

| Severity | Code | LSP map | Meaning |
|----------|:----:|---------|---------|
| `error` | E | Error | Must fix; CI fails. Real bugs or undefined behavior. |
| `warning` | W | Warning | Should fix. Likely-but-not-certain issues, complexity ceilings. |
| `style` | S | Hint | Auto-fix preferred. Hygiene, casing, formatting. |
| `info` | I | Information | Informational; no action expected. |

**Category** (orthogonal taxonomy):

| Category | Rules | Covers |
|----------|------:|--------|
| `bug` | 21 | Real defects: dead code, undefined references, control-flow holes |
| `style` | 13 | Casing, spacing, line length, naming |
| `complexity` | 9 | Cyclomatic / cognitive complexity, nesting, argument counts |
| `concurrency` | 6 | LOCK / TSTART / $ETRAP / OPEN-CLOSE pairing |
| `portability` | 8 | Engine-specific `Z*` / `$Z*` use without an allowlist |
| `documentation` | 6 | Missing comments, label docstrings, TODO ownership |
| `modernization` | 8 | Idioms with a better post-1990 replacement |
| `security` | 1 | Untrusted data → indirection / `XECUTE` (M-MOD-036, taint analysis) |

#### 6.2.3 The XINDEX rule pack (M-XINDX-NN)

42 rules ported from VA's `^XINDEX` Toolkit, with stable IDs mirroring XINDEX's numeric error codes 1:1 (`M-XINDX-013` ↔ XINDEX error 13, etc.). Engine-neutral subset (34 rules) ships in the `xindex` profile; the 8 VistA-Kernel-specific rules (banner mandates, `OPEN`→`^%ZIS`, etc.) live in the `vista` profile to avoid false positives outside VistA.

5 XINDEX rules remain registered but intentionally silent (M-XINDX-015 / 021 / 027 / 031 / 054) — patterns the tree-sitter parser already catches via its ERROR nodes. Pinned by `tests/test_xindex_inactive.py`.

**Cross-routine** (workspace-aware): M-XINDX-007 (call to undefined routine), M-XINDX-008 (call to undefined label in another routine), M-XINDX-049 (label declared but never referenced). Backed by `m_cli.workspace.WorkspaceIndex`.

#### 6.2.4 The modernization track (M-MOD-NN)

A greenfield rule family designed against contemporary M idioms (post-2010), engine- and dialect-neutral, **independent of the legacy XINDEX baseline** but with most rules supersesing one or more XINDEX rules via `Rule.replaces=...` metadata. Validated against the 4,215-routine non-VA corpus catalogued in [docs/plans/m-corpus-catalog.md](plans/m-corpus-catalog.md).

**Length / complexity (M-MOD-001..009)** — configurable thresholds:
- 001 line length, 002 code-line length, 003 routine LOC, 004 label-body LOC
- 005 cyclomatic complexity, 006 cognitive complexity, 007 dot-block depth, 008 argument count, 009 commands-per-line

**Concurrency / transactions (M-MOD-010..014)** — intra-label heuristics:
- 010 LOCK without timeout, 011 LOCK acquire/release imbalance, 012 TSTART/TCOMMIT pairing, 013 SET $ETRAP without preceding NEW, 014 OPEN/CLOSE imbalance

**Control-flow (M-MOD-015..020)** — single-pass AST checks:
- 015 $SELECT without default arm, 016 side-effecting postconditional, 018 argumentless FOR without conditional exit, 019 broad `?.E` pattern, 020 by-reference parameter unused intra-routine

**Engine-aware (M-MOD-021..023)** — consult m-standard's allowlists. Default `--target-engine=any` flags every `$Z*` token; setting `=yottadb` or `=iris` unlocks the engine's documented set.
- 021 Z-command, 022 $Z* ISV, 023 $Z* function

**Documentation / style (M-MOD-028..035)**:
- 028 label-docstring, 029 comment-density, 030 TODO/FIXME ownership, 031 magic-numbers, 032 single-letter vars, 033 argumentless NEW, 034 `SET X=X+1` → `$INCREMENT`, 035 $Z* function abbreviation → canonical

**Path-sensitive (Phase 7)** — see §6.2.5.

**Security / taint (Phase 9)** — see §6.2.6.

#### 6.2.5 Path-sensitive rules (Phase 7)

The largest research subproject in the linting roadmap, shipped as five rules built on a shared data-flow infrastructure (`m_cli.lint.flow`):

| Module | Lattice | Meet | What it tracks |
|--------|---------|------|----------------|
| `flow.cfg` | n/a | n/a | Per-label control-flow graph (entry / command / exit blocks; fall / branch / skip / if-skip / exit edge kinds) |
| `flow.vars` | n/a | n/a | Per-command variable extraction (defs / kills / uses + by-reference def handling for DO/JOB and `$$F(.X)` calls) |
| `flow.reaching` | set of names | intersection | Definite-assignment (forward MUST analysis): "is X defined on every path entering B?" |
| `flow.lock_state` | set of names | union | Held LOCKs (forward MAY): "may a LOCK on X be held entering B?" |
| `flow.transaction_state` | int (max=32) | max | Transaction nesting depth (forward MAY): "what's the worst-case TSTART depth entering B?" |
| `flow.etrap_state` | bool | AND | $ETRAP protection (forward MUST): "has NEW $ETRAP run on every path entering B?" |
| `flow.dollar_test` | bool | AND | $TEST freshness (forward MUST): "has a $T-setter (IF/OPEN/LOCK/READ/JOB) run on every prior path?" |

**The five Phase 7 rules:**

| Rule | Severity | Replaces | What it catches |
|------|:--------:|----------|-----------------|
| **M-MOD-024** | ERROR | — | Read of a local variable before any SET on every prior path. Sources include formals (always defined). Suppresses `$GET(X)` / `$DATA(X)` defensive-read intrinsics; recognizes the `IF $G(X)="" SET X=...` test+default-set idiom. |
| **M-MOD-025** | ERROR | M-MOD-011 | Path-sensitive LOCK leak: at least one path from label entry to exit leaves a LOCK held. Tracks globals (`^V`), indirection (`@expr` → sentinel `@`), and the incremental `+`/`-`/plain forms. |
| **M-MOD-026** | ERROR | M-MOD-012 | Path-sensitive TSTART leak: max transaction depth at exit > 0 on at least one path. |
| **M-MOD-027** | ERROR | M-MOD-013 | Path-sensitive $ETRAP leak: SET $ETRAP without preceding NEW $ETRAP on every prior path. |
| **M-MOD-017** | WARNING | — | Stale $TEST read: reading `$TEST` / `$T` without a $T-setting command on every prior path. |

The CFG over-approximates indirection (`@var` GOTO) as exit; FOR loops are straight-line in this slice (back-edge is a Phase 7+ refinement). Argumentless `Q` inside a dot-block correctly falls through to the dot-block's continuation rather than terminating the label.

#### 6.2.6 Taint analysis (Phase 9)

The differentiating security feature of the lint suite. Forward MAY-analysis with union meet over a set-of-names lattice, tracking which local variables hold *untrusted* data.

**Sources** — variables a tainted attribute attaches to:
- `READ X` (terminal input)
- Formal parameters of every label (configurable via `[lint.taint] formals_tainted = false`)

**Propagation** — strong-update SET semantics:
- `SET Y = expr` taints Y iff any var in `expr` is tainted (with sanitizer subtree skipping)
- `KILL X` / `NEW X` removes X from tainted set
- `D LBL(.X)` / `S R=$$F(.X)` taints X (callee may write any value through by-reference)

**Sanitizers** (default + user-configurable additions):
- Built-in: `$L` / `$LENGTH` / `$A` / `$ASCII` (return numeric values that can't carry code)
- Configurable: `[lint.taint] extra_sanitizers = ["$E", "$TR"]` adds `$EXTRACT` / `$TRANSLATE` etc.

**Sinks** (where M-MOD-036 fires):
- Any `indirection` AST node (`@expr` anywhere — `D @X`, `S @X=...`, `S Y=@X`, `G @X`, …)
- `XECUTE` command's argument

**M-MOD-036** flags the first tainted local that flows into a sink, dedup'd per (label, variable). Severity ERROR, category `security`. On the modern corpus: 276 findings dominated by the M-API idiom of "label takes a name parameter and indirects on it" — review-worthy in any context where the caller's data isn't fully trusted.

#### 6.2.7 Configurable thresholds

Ten integer knobs drive the metric rules. Set in `[lint.thresholds]` (project config) or via `--threshold KEY=VAL` (repeatable on the CLI). Unknown keys are rejected at config-load time so typos don't silently no-op.

| Key | Default | Used by | Meaning |
|-----|--------:|---------|---------|
| `line_length` | 200 | M-MOD-001 | Max bytes per line (any kind) |
| `code_line_length` | 1000 | M-MOD-002 | Max bytes for non-comment lines |
| `routine_lines` | 1000 | M-MOD-003 | Max lines per `.m` file |
| `label_lines` | 50 | M-MOD-004 | Max lines per labeled subroutine |
| `cyclomatic` | 15 | M-MOD-005 | McCabe cyclomatic per label |
| `cognitive` | 20 | M-MOD-006 | Cognitive complexity per label |
| `dot_block_depth` | 5 | M-MOD-007 | Max nested dot-block depth |
| `argument_count` | 7 | M-MOD-008 | Max formal arguments per label |
| `commands_per_line` | 3 | M-MOD-009 | Max commands per line |
| `comment_density_pct` | 10 | M-MOD-029 | Min comment-to-code ratio |

Resolution: built-in default → profile preset (`pythonic` bundles tighter values) → `[lint.thresholds]` config → `--threshold` CLI. CLI always wins.

#### 6.2.8 Engine targeting

Engine-aware rules behave differently per `--target-engine`:

- **`yottadb`** — `$Z*` ISVs and Z-functions documented by YottaDB pass; everything else flags as a portability concern
- **`iris`** — same for InterSystems IRIS / Caché
- **`any`** (default) — no engine-specific allowlist; M-MOD-021..023 use the ANSI subset only

Source of truth is m-standard's `standard_status` column. Persistent setting in `.m-cli.toml`:

```toml
[lint]
target_engine = "yottadb"   # or "iris" | "any"
```

When the linter detects ≥ 50 portability-rule findings under `target_engine=any`, it surfaces a one-line hint at the end of the run pointing here.

#### 6.2.9 Inline disable directives

Suppress findings without editing config — comment-driven, line-scoped:

```m
SOMELABEL ; m-lint: disable=M-MOD-031     ;; suppress on the next code line
 SET PRICE=1995
 ; m-lint: disable=M-MOD-009              ;; suppress next-line
 SET A=1 SET B=2 SET C=3
 SET X=1 ; m-lint: disable=M-MOD-031      ;; suppress same line (trailing)
 ; m-lint: file-disable=M-MOD-028          ;; suppress for the entire file
 ; m-lint: disable=*                       ;; suppress every rule
```

Forms:
- **`; m-lint: disable=RULE`** — next line only
- **trailing on same line** — same-line scope
- **`file-disable=RULE`** — whole file
- **`disable=*`** — every rule
- **`disable=RULE1,RULE2`** — multiple rules at once

LSP hover on a diagnostic shows the rule ID + title so you can copy it directly into the directive. `M-INTERNAL-RULE-CRASH` is exempt from suppression — buggy rules always surface.

#### 6.2.10 Baseline mode

Adopt the linter on a noisy legacy codebase without churning every existing finding:

```bash
m lint --update-baseline Routines/   # capture current findings; exit 0
m lint Routines/                      # subsequent runs suppress baselined findings
m lint --no-baseline Routines/        # opt out for one run; show everything
```

Stored as `.m-lint-baseline.json` (configurable path via `--baseline`). Schema is pinned and stable for diffs. Discovery walks up to find the nearest baseline file.

#### 6.2.11 Auto-fix linkage with `m fmt`

Some lint rules carry a `fixer_id` pointing to an `m fmt` rule that deterministically fixes the diagnostic:

| Rule | Severity | Auto-fix |
|------|:--------:|----------|
| `M-XINDX-013` | style | `m fmt --rules=trim-trailing-whitespace` |
| `M-XINDX-047` | style | `m fmt --rules=uppercase-command-keywords` |
| `M-MOD-035` | info | `m fmt --rules=expand-intrinsic-functions` |

The link surfaces in JSON output (`"fixer_id": "..."` per diagnostic) and via `m_cli.lint.fixer_for(rule_id)`. The LSP wrapper exposes these as Quick Fix code actions.

`m lint --fix` applies the fixers in-place: each unique `fixer_id` runs once per affected file; remaining (non-fixable) findings are still reported.

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

### 6.4 `m coverage`

Collect line- and label-level coverage from a YottaDB test run.

```bash
m coverage routines/tests/                  # whole directory
m coverage --routines=routines/             # restrict trace to specific source paths
m coverage --suites=HELLOTST,IDXTST         # restrict to named suites
m coverage --format=lcov > coverage.lcov    # genhtml / Codecov / Coveralls
m coverage --format=text --lines            # per-routine label + line columns
m coverage --uncovered                      # list uncovered lines only
m coverage --min-percent=70                 # exit 1 if coverage falls below threshold
m coverage --quiet                          # suppress per-routine progress
```

**How it works.** The runner uses YottaDB's built-in `view "TRACE":1:"^ycov":""` to capture per-line hit data in a single trace pass — one trace pass replaces N `ZBREAK`s per label that the legacy `ycover` script needed.

**Trace decoding.** YDB stores hits at `^ycov(routine, LABEL, N)` where N is the line offset from LABEL's declaration line. The parser's `_executable_lines_for_file` walks every `line` AST node with a `command_sequence` child, tracks the owning label's declaration line, and computes absolute line numbers as `label_decl_line + N`. So per-line hit counts are precise.

**Coverage on m-tools** (the validation gate): label-level **85/123 = 69.1%** byte-identical to `ycover`; line-level **340/637 = 53.4%**.

**Output formats:**
- **`text`** (default) — per-routine summary table + aggregate
- **`text --lines`** — adds per-line columns
- **`json`** — richest, includes raw line-hit pairs
- **`lcov`** — `lcov`-format file for genhtml / Codecov / Coveralls integration

**Env composition** mirrors `m test`: `$YDB` overrides the binary location, falling back to `$ydb_dist/ydb` then plain `ydb` on PATH. `ydb_routines` is honoured if exported, else derived.

The runner subprocess is injectable (`RunnerFn = (cmd, stdin_text, env) -> (stdout, returncode)`), so unit tests don't need a live ydb.

### 6.5 `m watch`

Auto-rerun affected suites on file save.

```bash
m watch routines/tests/        # poll, re-run on save
m watch --interval=1.0         # custom poll interval (seconds)
m watch --once                 # run the initial pass and exit
```

**Polling, not inotify.** Periodic `os.stat` (default 0.5 s) keeps the dependency tree minimal at the cost of latency. Pure Python — no `watchdog` / `entr` / `inotify` dependency.

**Affinity rule.** `<X>.m` source change → suite `<X.upper()>TST.m` if it exists; otherwise every suite re-runs (defensive default). Suite-file edits map to themselves only.

### 6.6 `m lsp`

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

### 6.7 `m doctor`

Diagnose the M development environment. Useful as the first command to run on a new shell or in CI.

```bash
m doctor                  # human-readable report
m doctor --format json    # machine-readable for CI dashboards
```

Five checks run in order; each carries a status + a one-line message + an optional hint on failure:

| Check | OK when | WARN when | FAIL when |
|---|---|---|---|
| `ydb_dist` | env var set, directory exists, `ydb` binary inside | unset, or directory exists but no binary | path missing, or not a directory |
| `ydb_routines` | env var set | unset | (never; downstream tools will surface the real error) |
| `parser` | `tree-sitter-m` parses a trivial routine | — | parser fails to load or returns no root |
| `keywords` | m-standard TSVs load with > 0 records | — | loader raises, or 0 records |
| `ydb_binary` | resolved via `$YDB`, `$ydb_dist/ydb`, or PATH | no binary found anywhere | `$YDB` points at a non-executable path |

Exit codes: `0` if no FAIL, `1` if any FAIL. **WARN does not fail the run** — many checks are recoverable for non-runtime workflows (e.g. `m fmt`/`m lint`/`m doc` need the parser and keywords but not `ydb_dist`).

---

### 6.8 `m new`

Scaffold a self-contained M project that passes the four gates on a clean clone.

```bash
m new hello                     # creates ./hello/
m new myapp --path /work/myapp  # explicit target dir
m new myapp --force             # scaffold even into a non-empty dir
```

Generated layout:

```
<name>/
├── routines/<NAME>.m         starter routine (pythonic-lower style)
├── routines/<NAME>ASRT.m     in-tree assertion helper (no m-stdlib dependency)
├── tests/<NAME>TST.m         starter test suite
├── .m-cli.toml               [fmt] pythonic-lower / [lint] default
├── .gitignore                .venv, *.o, coverage.lcov, ...
├── Makefile                  fmt / fmt-check / lint / test / coverage / check
└── README.md                 layout + quick-start
```

**Routine name derivation.** The project name is uppercased and stripped of non-alphanumeric characters, then truncated to 8 chars per the M routine-name limit (`my-app-v2` → `MYAPPV2`; `supercalifragilistic` → `SUPERCAL`). Names that start with a digit or strip to empty are rejected with a usage error.

**Why an in-tree assertion helper?** `<NAME>ASRT.m` is a tiny ~25-line wrapper exposing `start` / `eq` / `report` labels that emit the same `  PASS  desc` / `  FAIL  desc` / `Results: N tests P passed F failed` wire protocol that `m test`'s parser expects. New projects therefore have **zero external M dependencies** at startup. When the project later adopts [`m-stdlib`](https://github.com/m-dev-tools/m-stdlib), each call to `^<NAME>ASRT` swaps to the equivalent on `^STDASSERT` (same API).

**Generated content is verified at build time.** Unit tests apply `format_source(rules=select_fmt_rules('pythonic-lower'))` and `lint_source(rules=select_rules('default'))` to the rendered routine, helper, and test — no shipped scaffold ships with lint errors.

---

### 6.9 `m ci init`

Emit a GitHub Actions workflow that runs the four project gates on every push and pull request.

```bash
m ci init                  # writes .github/workflows/m-ci.yml in cwd
m ci init --path /repo     # write into a different project root
m ci init --force          # overwrite an existing workflow
```

The generated `m-ci.yml` runs against the `yottadb/yottadb-base:latest-master` container so test/coverage actually have a YDB engine, clones `tree-sitter-m` and `m-cli` from GitHub and installs them into a venv, sources `ydb_env_set`, then walks:

1. `m doctor` — sanity check before doing anything destructive
2. `m fmt --check routines tests`
3. `m lint --error-on=fatal routines tests`
4. `m test tests`
5. `m coverage --format=lcov --routines routines --tests tests > coverage.lcov`
6. `actions/upload-artifact@v4` — saves `coverage.lcov` for downstream upload to Codecov / Coveralls / etc.

The workflow is a **starter, not a vendor lock.** Common customizations: pin a specific YottaDB tag, add `codecov/codecov-action@v4` to push coverage, swap m-cli's pip source to a private index. `m ci init` reuses the template-emitter pattern introduced for `m new`.

---

### 6.10 `m run`

Thin wrapper around `ydb -run ENTRYREF`.

```bash
m run HELLO                            # → ydb -run ^HELLO
m run EN^HELLO                         # → ydb -run EN^HELLO
m run --routines ./routines HELLO      # prepend ./routines onto $ydb_routines
m run --routines ./routines --routines ./third_party HELLO   # repeatable
m run HELLO -- arg1 arg2               # extra args flow through to $ZCMDLINE
```

**Resolution order for the ydb binary.** `$YDB` (explicit, useful in CI) → `$ydb_dist/ydb` (canonical YDB install layout) → `ydb` on `$PATH`. `m run` exits 2 if no binary is found.

**Entryref normalization.** Routine name uppercased and truncated to 8 chars (M's routine-name limit). Label name uppercased but kept full-length (ydb itself is permissive). Bare-routine form (`HELLO`) becomes `^HELLO`; labelled form (`EN^HELLO`) is passed through.

**Exit-code passthrough.** The subprocess `returncode` is returned directly so M's `HALT`/`$ECODE`-driven exit codes flow back to the caller. Stdout and stderr are inherited (not captured), so `m run` is safe in pipelines and interactive sessions alike.

---

### 6.11 `m build`

Warm-compile a directory of M routines via `ydb <file>` (which YottaDB invokes as the routine compiler).

```bash
m build                            # walk ./ for *.m and compile each
m build routines tests             # explicit roots
m build --check routines           # compile + clean up .o byproducts (CI)
m build --quiet routines           # suppress per-file `ok` lines
```

Discovery is recursive; explicit `.m` files are accepted alongside directories; results are deduped by resolved path and sorted by filename.

**Output format.**

```
routines/HELLO.m: ok
routines/BAD.m: compile failed (rc=1)
  %YDB-E-LABELMISSING, Label EN referenced but not defined in HELLO
  %YDB-E-ZLINKFILE, Error while zlinking "BAD.m"

5 compiled, 1 failed
```

Exits `0` if every file compiled, `1` if any failed, `2` on usage error (no ydb binary, or no `.m` files in the given paths).

**`--check` mode** identifies any `.o` files this run created and removes them at the end. CI gates that just want to know "does this compile?" use `--check` to avoid polluting the working tree. Files that already had an `.o` sibling at start-time are preserved.

The compiler subprocess is injectable (`runner=...` kwarg on `build_command`) so unit tests cover discovery, error aggregation, and the `--check` cleanup contract without needing real ydb.

---

### 6.12 `m doc`

Extract `@summary` docstrings from M source into Markdown or HTML.

```bash
m doc                              # walk ./ for *.m, write Markdown to stdout
m doc routines                     # explicit roots
m doc routines --output API.md     # write to a file instead of stdout
m doc routines --format html       # HTML output (inline stylesheet, no external assets)
```

The extractor pulls four pieces of structure from each routine:

1. **Routine name** — file stem, uppercased (matches the M convention).
2. **Routine summary** — text after the first `;` on line 1, with a leading `@summary` annotation stripped.
3. **Version stub** — line 2 if it matches `;;<version>;<package>;;<date>;<build>`. Surfaced as the per-routine `version` and `package` metadata.
4. **Per-label entries** — one for each labelled definition discovered by `tree-sitter-m`. Each carries `name`, `formals` (`"(a,b)"` or `""`), and the `@summary` text from the label's line.

Double-semicolon lines (`;;<directive>`) are excluded from human-prose extraction — they're either version stubs or structured directives, not documentation.

**Markdown output** — one `## ROUTINE` heading per routine with a `_version · package · source_` italic metadata line, then a `### Labels` bullet list of `` `name(formals)` — summary `` entries.

**HTML output** — same structure wrapped in a `<!doctype html>` document with a tiny inline stylesheet. Renders cleanly without external assets, suitable for emailing or hosting on a static site.

**Reuses the parser.** `m_cli.lsp.structure.find_labels` does the AST walk; `m_cli.build.runner.discover_files` does the file walk. New code in `m_cli.doc` is purely the docstring-extraction + render layer.

---

## 7. Project configuration

`m fmt`, `m lint`, and `m lsp` all read project config on startup. Discovery walks up from the working directory looking for:

1. **`.m-cli.toml`** — preferred, project-local
2. **`pyproject.toml`** with a `[tool.m-cli]` table — fallback for projects that already use Python packaging conventions

Walking stops at the nearest `.git` boundary so configs in unrelated parent directories don't leak in.

**Schema:**

```toml
[lint]
rules = "default"              # rule filter (same syntax as --rules)
disable = ["M-XINDX-013"]      # rule ids to skip after selection
target_engine = "yottadb"      # "any" (default, portable) | "yottadb" | "iris"

[lint.severity]
"M-XINDX-019" = "warning"      # remap per-rule severity
"M-MOD-031" = "info"           # demote a noisy rule to non-actionable
                               # values: "error" | "warning" | "style" | "info"

[lint.thresholds]              # configurable knobs for metric rules
line_length = 100              # M-MOD-001 (default 200)
commands_per_line = 1          # M-MOD-009 (default 3)
cyclomatic = 10                # M-MOD-005 (default 15)
# See §6.2.7 for the full ten-knob table.

[lint.taint]                   # M-MOD-036 taint analysis (Phase 9)
formals_tainted = true         # default true; set false for purely-internal helpers
extra_sanitizers = ["$E"]      # ADD to the default sanitizer set
                               # ($L, $LENGTH, $A, $ASCII)

[fmt]
rules = "canonical"            # canonical, none (identity), pythonic, compact, or comma-separated rule ids
```

**Resolution order:** defaults → config → CLI flag (CLI always wins). Unknown keys are ignored silently to keep forward compatibility cheap. Invalid values (bad severity name, `disable` not a list) raise on load.

The LSP loads the config from `Path.cwd()` at spawn time. VS Code spawns subprocesses with `cwd = workspace folder`, so this finds the workspace's project config without needing the `initialize` rootUri.

---

## 8. Editor integration (VS Code)

`m-cli`'s LSP is wired into VS Code via the sibling extension repo [`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode) (installed as `rafael5.tree-sitter-m-vscode`). The extension:

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
| **VistA round-trip** | `make vista` | `m fmt` (identity) is byte-for-byte clean over 38,954 VistA routines (376 routines fail to parse — same set as `tree-sitter-m`'s known boundary). |
| **VistA canonical layout** | `make vista-canonical` | `m fmt --rules=canonical` is idempotent + AST-preserving over the corpus. |
| **VistA lint baseline** | `make lint-vista` | Full XINDEX rule pack runs over the corpus in 22.6 s; findings are byte-identical against the prior baseline. |
| **Modern-corpus lint baseline** | `make lint-modern` | M-MOD-NN rules run over the catalogued non-VA corpus (YDBTest, mgsql, YDBOcto-aux, EWD, M-Web-Server — 3,470 lintable routines); per-corpus finding counts must match `scripts/lint_modern.baseline.json` within tolerance. |

A change that breaks any of these is a release blocker.

---

## 12. Roadmap & open work

### What's shipped

Strategic phases beyond Tier 1 (in dependency order):

| Phase | Capability | Status | Notes |
|-------|------------|:---:|---|
| **A** | Project configuration files (`.m-cli.toml` / `[tool.m-cli]`) | ✅ Done | `[lint]`, `[lint.severity]`, `[lint.thresholds]`, `[lint.taint]`, `[fmt]`. |
| **B** | Workspace symbol index → `textDocument/definition` / `references` / `workspace/symbol` + incremental `didChangeWatchedFiles` updates | ✅ Done | Foundation for cross-routine M-XINDX rules (M-XINDX-007/008/049). |
| **C** | `m coverage` (line + label, four output formats) and `m trace` foundation | ✅ Done | YDB `view "TRACE"`-based; lcov output for genhtml/Codecov/Coveralls. |
| **D** | M-MOD modernization track, Phases 1–8 (35 rules) | ✅ Done | Profiles, two-axis severity, configurable thresholds, modern-corpus regression gate. |
| **Phase 7** | Data-flow infrastructure + path-sensitive rules (M-MOD-024/025/026/027/017) | ✅ Done | Per-label CFG, definite-assignment, lock/transaction/etrap/dollar_test analyzers. |
| **Phase 9 (MVP)** | Taint analysis (M-MOD-036) | 🟡 MVP shipped | `READ` + formals as sources; `@expr` / `XECUTE` sinks; `$L`/`$A` sanitizers; `[lint.taint]` config schema; by-reference DO/JOB call modeling. |
| **Phase 3a** | Quick-win subcommands per [language-cli-survey.md §6.2](language-cli-survey.md): `m doctor`, `m new`, `m ci init`, `m run`, `m build`, `m doc` | ✅ Done | Six independent items closing §4.1 ranks 8, 2, 12, 11, 9, 4. Each ships with tests, dispatcher wiring, and §6 reference docs. `m new` projects pass `m fmt --check && m lint && m test && m coverage` on a clean clone (the §6.2 exit criterion). |

### What's still open

| Capability | Status | Notes |
|------------|:---:|---|
| Cross-routine taint propagation (Phase 9 follow-up) | ⏸️ Deferred | Tainted formal flowing into `$$F(X)` doesn't yet inherit through to the callee's return. Largest remaining piece of Phase 9. |
| Implicit globals as taint sources (`^TMP("USER", ...)`, `^XTMP`, etc.) | ⏸️ Deferred | Would extend `[lint.taint]` with a `source_globals = [...]` knob. |
| `$EXTRACT` / `$TRANSLATE` conditional sanitizers | ⏸️ Deferred | Pattern-match safe usage (e.g. `$E(X,1,N)` where N is a constant). Workaround today: add to `extra_sanitizers` if you've audited the call sites. |
| DAP debugger integration | ⏸️ Deferred | Tier 2 capability; substantial engineering on its own. Both engines ship `ZBREAK` at engine level. |
| FOR loop back-edge in CFG | ⏸️ Deferred | Phase 7+ refinement. Currently FOR body is straight-line; first-iteration reads of FOR-set variables may under-report. |

The full roadmap with phasing plan and validation criteria lives in [docs/plans/m-linting-implementation-plan.md](plans/m-linting-implementation-plan.md). Historical work-board / archaeology in [docs/evolution.md](evolution.md).

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

*This guide tracks the state of `m-cli` as of 2026-05-06 (after Phase 3a — `m doctor`, `m new`, `m ci init`, `m run`, `m build`, `m doc`). For the per-session changelog, see `git log`. For the comprehensive lint reference (rule-by-rule, with worked examples), see [docs/m-linting-user-guide.md](m-linting-user-guide.md). For strategic context, the canonical references are [m-tool-gap-analysis.md](../../m-tools/docs/m-tool-gap-analysis.md), [m-tooling-tier1.md](../../m-tools/docs/m-tooling-tier1.md), and [language-cli-survey.md](language-cli-survey.md).*
