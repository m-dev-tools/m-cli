---
title: m-cli — history and evolution
status: live (2026-05-06)
audience: anyone trying to understand how m-cli came to exist, what its precursors were, and where it sits among the M-language tooling sibling projects
companion: ../README.md (current capability surface)
---

# m-cli — history and evolution

m-cli did not appear from nothing. It is the **fourth named project**
in a six-week sprint that started as one developer's MUMPS learning
exercise and ended up producing a small ecosystem of cooperating
M-language libraries and tools. This document is the roadmap of how
that happened, in chronological order, and how the pieces depend on
each other today.

It also exists to clear up genuine confusion about **m-tools** —
which has worn three different hats over its short life and whose
remaining role is easy to misread.

---

## 1. TL;DR

```
2026-03-24  m-tools          MUMPS learning project; bespoke ^TESTRUN runner; 11 module test suites
2026-04-18  vista-meta       VistA-FOIA Dockerised sandbox; PIKS data-asset classification
2026-04-23  m-standard       Initial scaffold (machine-readable M language reference)
2026-04-25  tree-sitter-m    Grammar consumer of m-standard
2026-04-25  m-tools (y* )    Tier 1/2/3 bash dev tools — exploratory implementation of the inner loop
2026-04-27  m-tools (docs)   Gap analysis + Tier 1 strategy committed
2026-04-27  m-cli            Clean Python rewrite of the y* tools, on top of tree-sitter-m
2026-04-30  m-stdlib         Pure-M runtime library, filling stdlib gaps; tested via m-cli
2026-05-05  m-modern-corpus  Curated 5-project / 4,215-routine non-VA M corpus for tooling validation
```

m-cli is the **canonical** Tier-1 inner-loop toolchain (`m fmt` /
`m lint` / `m test` / `m watch` / `m coverage` / `m lsp`). Its
existence depends, in order, on:

1. **m-standard** providing the language vocabulary,
2. **tree-sitter-m** providing the parser,
3. **vista-meta** providing the YottaDB runtime engine for the
   tools that need one.

m-tools' shell scripts (`bin/y*`) are kept as **historical
references** — they were the prototype that proved the design before
m-cli rewrote it cleanly.

m-stdlib is **downstream** of m-cli (it uses `m test` / `m coverage`
/ `m lint` to gate every release), but m-cli is **upstream** of
m-stdlib at the API level (m-cli does not import m-stdlib;
m-stdlib's modules are consumed by *other* M projects, including
m-tools after the 2026-05-06 migration).

---

## 2. Dependency graph

Solid arrows = hard runtime / API dependency. Dashed = testing
exercise only (the consumer can be removed without breaking the
producer).

```
                     ┌────────────────────────┐
                     │      m-standard        │
                     │  (language reference)  │
                     │   commands/ISVs/SVNs   │
                     │   grammar-surface.json │
                     └──────────┬─────────────┘
                                │
                                │ generates
                                ▼
                     ┌────────────────────────┐
                     │     tree-sitter-m      │
                     │  (parser + bindings)   │
                     │  Node / Rust / Py / Go │
                     └──────────┬─────────────┘
                                │
                                │ AST
                                ▼
              ┌─────────────────────────────────────┐
              │              m-cli                  │
              │   m fmt · m lint · m test ·         │
              │   m watch · m coverage · m lsp      │
              └──┬──────────────────────────────┬───┘
                 │                              │
       runtime   │                              │   tested via
       engine    ▼                              ▼   `m test`
              ┌──────────────┐         ┌─────────────────┐
              │  vista-meta  │         │    m-stdlib     │
              │ Docker+YDB+  │         │ STD* routines   │
              │ VistA-FOIA   │         │ (assert, uuid,  │
              │ + PIKS data  │         │  json, regex,…) │
              └──────────────┘         └─────────┬───────┘
                                                 │
                                                 │ ^STDASSERT
                                                 ▼
                                       ┌──────────────────┐
                                       │     m-tools      │
                                       │  bin/y* (legacy) │
                                       │  routines/*.m    │
                                       │  GTREETST etc.   │
                                       └──────────────────┘

         ┌────────────────────────┐
         │   m-modern-corpus      │   ← validation corpus only
         │  ewd / mgsql / ...     │      (4,215 non-VA routines)
         └────────────────────────┘
                      ▲
                      │ exercised by
                      │ m-cli + m-stdlib
                      └── (validation, no API dep)
```

**Reading the graph**: m-standard is the root of trust; everything
language-level traces to it. tree-sitter-m exists to make
m-standard's vocabulary AST-addressable. m-cli sits on top of
tree-sitter-m to deliver the inner-loop. vista-meta is the runtime
engine for the tools that need one (tests, coverage, trace);
m-stdlib gets exercised through that runtime; m-tools consumes
m-stdlib's STDASSERT.

---

## 3. Chronological history

### Phase 0 — A MUMPS learning project (2026-03-24)

**m-tools begins** (commit `41ed967` "Initial MUMPS/YottaDB project
scaffold", 2026-03-24). Original purpose stated in the commit
message: *"Sets up TDD environment for learning MUMPS with
YottaDB."* The first scaffold ships:

- a hand-rolled `routines/tests/TESTRUN.m` (lightweight, no
  external deps) as the assertion library,
- one test suite (`HELLOTST.m`) "demonstrating TDD pattern,"
- `bin/yrun` as a command-line entry point for running routines
  from any directory.

Within 24 hours of the initial scaffold (still 2026-03-24), nine
more commits land — TDD-driven additions of `globals.m`, `gtree.m`,
`tasks.m`, `strfns.m`, `csv.m`, `json.m`, `validate.m`, `txn.m`,
`idx.m`, plus a CLI layer and HTTP server. Each lands "all tests
green." This is m-tools-as-learning-project, and the learning is
working: 250+ assertions across the M test suites, every module
TDD-built.

**vista-meta begins** later (2026-04-18, commit `e3e9d4d`) on a
parallel track — a Dockerised VistA-FOIA sandbox for an unrelated
classification project (PIKS — "patient information kindred
schema"). It will eventually become the m-cli runtime engine, but
not for another six weeks.

### Phase 1 — Discovering the gaps (2026-04-25 → 2026-04-27)

After the learning phase, m-tools acquires a second life: a
**reference implementation of M-language developer tools as
shell scripts**. This happens in three rapid commits over 2026-04-25:

| Commit | Tier | Tools added |
|---|---|---|
| `6c4fb9e` | Tier 1 | `ytest`, `yclean`, `ywhat`, `ylog`, `yhook`, `yci` |
| `d2e9999` | Tier 2 | `yexport`, `yseed`, `ydiff`, `yglobsize`, `yrundown`, `ytest-watch-smart` |
| `2c40ed2` | Tier 3 | `ynew`, `ydoc`, `ytap`, `yperf`, `ysnapshot`, `ycover` |

Total: 24 `y*` shell scripts under `~/projects/m-tools/bin/`. They
work, but they are bash. They invoke YottaDB processes, parse
output with `awk`/`grep`, and have all the limitations that come
with bash + grep against a non-trivial AST. They are good
**enough** to validate the design — running tests, watching files,
showing coverage — but they are not the long-term answer.

The same week (2026-04-25 → 2026-04-27), three other projects
appear or accelerate dramatically, all driven by the realisation
emerging from the m-tools experiment:

- **m-standard** (initial scaffold 2026-04-23 with `7502a51`,
  `4f7d8aa`, `103bbaa`, `1a13caa`; meaningful work begins
  2026-04-25 with `ac42e63` "Phase A0"). The thesis: *we cannot
  build trustworthy lint rules until we have a machine-readable,
  vendor-neutral inventory of the M language surface.* m-standard
  will reconcile four primary sources (AnnoStd / YottaDB / IRIS /
  VA SAC) into TSVs and `grammar-surface.json`.

- **tree-sitter-m** (initial scaffold 2026-04-25, `cc870a8`
  "Specification phase: m-parser as the tree-sitter grammar
  consumer of m-standard"). The thesis: *every M tool needs an
  AST; nobody has shipped a production tree-sitter grammar for M;
  we'll generate one mechanically from m-standard's
  grammar-surface.* By 2026-04-26 it parses 99.06% of the
  39,330-routine VistA corpus.

- **m-tools strategic docs** (2026-04-27, commit `4fa55b3`). With
  m-standard and tree-sitter-m both in flight, the gap analysis
  gets written down formally: `docs/m-tool-gap-analysis.md`,
  `docs/gap-analysis-and-remediation-strategy.md`,
  `docs/m-tooling-tier1.md`. These docs identify five Tier 1 gaps
  (test runner, linter, formatter, single-test selection, test
  watcher) as the integrated developer "inner loop" and argue
  that all five are now feasible because the parser and language
  reference exist.

### Phase 2 — m-cli is born (2026-04-27)

Hours after m-tools' Tier 1 strategy doc lands, **m-cli's first
commit** ships: `927ea16` "Initial commit: m-cli — Tier 1 Step 1
(`m fmt` identity formatter)" (2026-04-27). The commit message
states the lineage explicitly:

> First step of the M ecosystem Tier 1 toolchain (see
> `m-tools/docs/m-tooling-tier1.md`).
>
> Naming convention: universal `m <subcommand>` (mirrors
> cargo/go/git).
>
> Legacy `y*` shell tools in `m-tools/bin` remain functional but
> are references only, not the canonical interface.

The same commit exercises the rationale: `m fmt` round-trips
38,954 / 39,330 (99.04%) of the VistA corpus byte-for-byte at
~1,500 routines/second. This is something a bash script cannot
do — it requires the AST.

So **m-cli is to m-tools' bash y\* scripts what `m-cli`'s Python
implementation is to bash**: a clean rewrite, on top of the parser
and language reference that didn't exist when m-tools first tried
the same problem.

### Phase 3 — m-cli's Tier 1 build-out (2026-04-27 → 2026-04-30)

m-cli ships rapidly through April 27–30:

- 2026-04-27: `m fmt` (Step 1), `m lint` (Step 2 with 11 then 36
  XINDEX rules), `m test` (Step 3+4 with single-test selection),
  `m watch` (Step 5), pre-commit hooks, LSP stages 1–4 (diagnostics
  → format → code actions → hover/completion), workspace symbol
  index. By the end of the day Tier 1 is functionally complete.
- 2026-04-28: `m coverage` (Tier 2 / Phase C — label-level via
  ZBREAK; later deepened to YDB `view "TRACE"` with lcov output);
  cross-routine lint rules.
- 2026-04-30: M-MOD modernization rule pack (35 rules through
  M-MOD-036), profile system, taint analysis MVP, lint audit
  closure.

Throughout, m-cli's **runtime requirement** remains YottaDB:
source-level tools (`fmt`, `lint`) parse via tree-sitter-m and need
no engine, but `test`, `coverage`, `trace` invoke YottaDB
processes. Initially the host machine's local YottaDB; soon
migrating to vista-meta's container.

### Phase 4 — m-stdlib begins (2026-04-30)

With Tier 1 stable, attention turns to the **second** kind of M-
language gap: M itself ships almost no standard library.
**m-stdlib** scaffolds (commit `347a938` "Phase 0: bootstrap
m-stdlib skeleton", 2026-04-30). Its very first non-bootstrap
commit (`ab08e27` "v0.0.1: STDASSERT + STDUUID", same day) ships
`STDASSERT.m` — and the bootstrap commit message explicitly notes
that `STDASSERT` mirrors `^TESTRUN`'s output protocol byte-for-byte:

> `src/STDASSERT.m`: stub assertion library (start, eq, ok, pass,
> fail, report) mirroring `^TESTRUN`'s output protocol
> byte-for-byte.

So **STDASSERT inherits m-tools' protocol design**. The protocol
gets re-used because m-cli's `m test` runner was already shaped to
parse it. (This fact later becomes the C1 toolchain finding when
m-cli's runner hardcoded `^TESTRUN`; the C1 fix in m-cli `23241a2`
made the runner protocol-aware.)

m-stdlib then ships nine modules through `v0.1.0` (2026-05-05),
adds Phase 1b TDD primitives (STDFIX / STDMOCK / STDSEED in
`v0.1.1`–`v0.1.3`), and lands all four Phase 2 modules (STDJSON,
STDREGEX, STDCOLL, STDURL) on `main` awaiting the `v0.2.0` tag.

### Phase 5 — Self-hosting (2026-05-05 → 2026-05-06)

Two recent events tie the loop:

1. **m-tools migrates to STDASSERT** (m-tools `3eec0bf`,
   2026-05-06): all 11 of m-tools' original test suites get
   mechanically renamed from `^TESTRUN` to `^STDASSERT` and
   `routines/tests/TESTRUN.m` is deleted. The bespoke runner that
   started everything is replaced by its descendant. The m-tools
   suites are **the** real-project STDASSERT consumer in the
   ecosystem (m-cli, tree-sitter-m, m-standard ship no M-side
   test suites at all).

2. **m-modern-corpus seeded** (2026-04-29 onwards): five non-VA M
   projects (`ewd/`, `mgsql/`, `m-web-server/`, `ydbocto-aux/`,
   `ydbtest/`) totalling 4,215 routines, used as a tooling
   validation corpus for both m-cli (lint rule signal-to-noise)
   and m-stdlib (real-code library-fit findings — see
   `docs/realcode-validation.md` and
   `docs/modern-m-corpus-test-results.md` in m-stdlib).

The ecosystem now self-hosts: m-cli is built and tested using
itself; m-stdlib is gated by m-cli; m-tools (the original
exploratory project) consumes m-stdlib.

---

## 4. Per-project roles, in plain language

### m-tools — what it *is*, what it *was*, what it *is not*

This is the project most likely to confuse a new reader, because
it has had three roles in sequence and still wears traces of all
three.

**What m-tools *was*:**

1. **(2026-03-24 → 2026-04-12)** A personal MUMPS learning
   project. Hand-rolled `^TESTRUN.m` runner, eleven library
   modules under `routines/`, all TDD-built. This was the soil
   the rest of the ecosystem grew out of.
2. **(2026-04-25 → 2026-04-27)** A reference implementation of
   M-language developer tools as bash. The 24 `y*` scripts under
   `bin/` (`ytest`, `ylint`-precursors, `ywatch`-precursors,
   `ycover`, `ynew`, `ytap`, etc.) were the experiment that
   proved the inner loop was implementable and that bash was the
   wrong tool for the job.

**What m-tools *is* (today, 2026-05-06):**

- **Status: maintenance** (per `CLAUDE.md` schema). The `y*`
  scripts are kept as references — they still work for someone
  who wants to invoke a specific YottaDB primitive directly — but
  they are **not** the canonical interface for new work. The
  canonical interface is `m <subcommand>` in m-cli.
- A **library of M routines** (`gtree.m`, `globals.m`, `json.m`,
  `csv.m`, `tasks.m`, `txn.m`, `idx.m`, etc.) under `routines/`,
  all tested via STDASSERT (post `3eec0bf`). Some of these
  predate m-stdlib's equivalents (m-tools' `json.m` predates
  m-stdlib's STDJSON); long-term the m-tools' modules likely
  cede to m-stdlib's, but no migration is scheduled.
- The **historical home of the gap analysis docs** (`docs/m-tool-
  gap-analysis.md`, `docs/m-tooling-tier1.md`,
  `docs/gap-analysis-and-remediation-strategy.md`). These are
  reference reading for understanding why m-cli is shaped the way
  it is.

**What m-tools *is not*:**

- It is **not** the canonical M-language CLI. That is m-cli.
- It is **not** the standard library for M routines. That is
  m-stdlib.
- It is **not** dead. The `y*` scripts are still useful for
  one-off YottaDB-primitive invocations that don't have a clean
  `m <subcommand>` equivalent yet, and the M routines under
  `routines/` are still consumed by other m-tools tests.
- It is **not** the place to add new tooling. New developer
  tools belong in m-cli.

### m-standard — the language reference

The root of trust. Without m-standard, every downstream tool has
to re-derive the M language definition from scratch (which is
what every prior M tool effort has done — and explains why most
M tools cover only a fraction of the language correctly).

m-standard reconciles **four primary sources** (AnnoStd 1995 /
YottaDB / IRIS / VA SAC) and emits **machine-readable artefacts**:
TSVs (`commands.tsv`, `intrinsic-functions.tsv`,
`intrinsic-special-variables.tsv`, etc.) and a curated
`integrated/grammar-surface.json` that downstream parsers consume.

**Consumed by:** tree-sitter-m (grammar generation), m-cli (lint
keyword tables).

### tree-sitter-m — the parser

A production tree-sitter grammar for M, **mechanically generated
from m-standard's grammar-surface**. 99.06% clean parse on the
full 39,330-routine VistA corpus. Bindings for Node / Rust /
Python / Go.

The existence of tree-sitter-m is what enabled m-cli; the bash
y\*-tools experiment in m-tools could not do AST-level work, and
that is what limited it. Until tree-sitter-m existed, "M
formatter" / "M linter" / "M LSP" were each multi-year efforts;
with tree-sitter-m as a Python binding, m-cli built all of them
in days.

**Consumed by:** m-cli (parser binding), tree-sitter-m-vscode
(WASM build powering the VS Code extension).

### m-cli — the canonical inner-loop toolchain

What this document is the history of.

**Surface:** `m fmt` / `m lint` / `m test` / `m watch` /
`m coverage` / `m lsp` / pre-commit hooks. Six subcommands plus
the LSP server, all under one binary. 77 lint rules across 7
profiles. Configurable via `.m-cli.toml`.

**Built on:** tree-sitter-m (parser binding); m-standard (lint
keyword tables, loaded at import time from m-standard's TSVs);
vista-meta (when a runtime engine is needed).

**Status:** Tier 1 + Tier 2 done; Phase 9 (taint analysis) in
progress. C1–C5 m-cli companion tracks for m-stdlib closed
2026-05-05. Two open P1s in TOOLCHAIN-FINDINGS (single-test mode
rc=253 regression; pending fix for `$$encode^STDJSON` recursive-
descent harness crash).

### m-stdlib — pure-M standard library

Sibling to m-cli, not built on it: m-stdlib is **pure M code**
(YottaDB-first; IRIS-portable where reasonable). m-cli does not
import m-stdlib; m-stdlib is consumed by *other* M projects.

m-stdlib does, however, **depend on m-cli at development time**
— every release is gated by `m fmt --check`, `m lint
--error-on=error`, `m test`, `m coverage --min-percent=85`. This
makes m-stdlib m-cli's most demanding dogfooding consumer and the
de-facto regression suite for the m-cli toolchain (see
m-stdlib's `TOOLCHAIN-FINDINGS.md`).

**Modules shipped or landed-awaiting-tag** (2026-05-06):
STDASSERT, STDUUID, STDB64, STDHEX, STDFMT, STDLOG, STDDATE,
STDCSV, STDARGS (`v0.1.0`); STDFIX, STDMOCK, STDSEED
(`v0.1.1`–`v0.1.3`); STDJSON, STDREGEX, STDCOLL, STDURL plus L4
STDLOG-`FORMAT(kv|json)` and L10 STDSEED-`loadJson` add-ons
(landed on `main`, awaiting `v0.2.0`).

### vista-meta — Dockerised YottaDB engine

Originally a VistA-FOIA classification project (PIKS — "patient
information kindred schema") started 2026-04-18. Acquired its
second role as the **canonical YottaDB runtime engine** for the
sibling tooling: m-cli's `m test` / `m coverage` / `m trace`
require a YottaDB; vista-meta provides one (over SSH) plus a
seeding contract (`~/data/vista-meta/conn.env`).

m-stdlib's tests run on vista-meta. m-cli's coverage smoke tests
use it. m-tools is in the middle of a working-tree migration to
use it as well (uncommitted as of 2026-05-06).

### m-modern-corpus — non-VA validation corpus

The smallest sibling. Five non-VA M projects vendored as a
**fixed snapshot** (2026-04-29 onwards): `ewd/` (86 routines),
`mgsql/` (36), `m-web-server/` (23), `ydbocto-aux/` (21),
`ydbtest/` (4,049). 4,215 routines / ~14 MB total. Used by m-cli
(rule-noise calibration) and m-stdlib (library-fit validation —
see m-stdlib `docs/realcode-validation.md`).

Per its own `CLAUDE.md`, this is a **one-time snapshot**, not a
live mirror. Re-syncing would be a deliberate decision.

### tree-sitter-m-vscode — editor integration (FYI)

VS Code extension that loads tree-sitter-m as WASM for syntax
highlighting and semantic tokens. Not in m-cli's runtime
dependency chain, but it exercises tree-sitter-m end-to-end and
will eventually consume m-cli's LSP server for richer features.

---

## 5. Why this shape works

Three design choices, set early, keep the ecosystem coherent:

1. **Single source of truth for the language.** m-standard
   reconciles vendor docs once; tree-sitter-m and m-cli both
   consume the same TSVs / grammar-surface. Changes to vendor
   behaviour propagate via a single update path.

2. **Universal `m <subcommand>` interface.** m-cli's first commit
   (`927ea16`) chose `m fmt` / `m lint` / `m test` over
   per-tool binaries (`mfmt` / `mlint` / `mtest`). This mirrors
   `cargo` / `go` / `git` and lets users learn the surface as one
   tool with subcommands rather than as a fleet of separate
   tools. It also makes the legacy `y*` scripts visibly
   sub-canonical without removing them.

3. **m-stdlib has architectural priority over m-cli.** Stated
   plainly in m-stdlib's `CLAUDE.md`: *"When both projects need
   a utility, implement it here first; m-cli imports."* This
   keeps m-cli's Python codebase from re-implementing things that
   M code can do natively, and gives M projects (not just m-cli)
   a stdlib worth depending on.

---

## 6. Forward roadmap

What is queued, in rough order:

**Imminent (days):**

- **m-stdlib `v0.2.0` tag.** All four Phase 2 modules + both
  add-ons are on `main`; only the release sync remains. Closes a
  release that has been development-complete since 2026-05-05/06.
- **STDASSERT.raises P1 verification.** The 2026-05-06
  `9ee9724` ZGOTO-based fix is committed; remaining parked
  raises-path test bodies in STDFMT / STDDATE / STDCSV /
  STDARGS can be unparked once the fix is independently
  exercised.

**Near term (weeks):**

- **m-cli single-test mode P1.** Post-C1 regression: `m test
  FILE.m::tLabel` exits rc=253 silently on STDASSERT-driven
  suites. Fix is "in-process stderr capture." Whole-suite mode is
  unaffected.
- **m-stdlib Phase 3.** STDHTTP, STDCRYPTO, STDCOMPRESS via
  `$ZF` host calls. Build-callouts harness (`tools/
  build-callouts.sh`) shipped as A6, so the infra prereq is met.
- **tree-sitter-m v0.1 publish.** Prebuildify CI is shipped;
  `npm publish` / `cargo publish` / Go-module tag are
  maintainer-credential-gated and need to be done manually. The
  Python binding stays clone-and-install (no PyPI publication).

**Medium term (months):**

- **m-cli `m env`.** A YottaDB / IRIS environment manager (see
  `docs/m-env-implementation-plan.md`) — close the "no canonical
  way to bootstrap an M dev environment" gap.
- **m-cli `--integration`** (C6). Blocked on parent-plan Phase 4
  in vista-meta orchestration.
- **Editor integrations beyond VS Code.** JetBrains, Neovim
  (LSP-only).

**Long term (open):**

- **m-stdlib `v1.0.0`.** Time-based — three months of API
  stability after `v0.3.0`.
- **m-cli `--target-engine=iris`.** Source-only IRIS support is
  scaffolded; a live IRIS test engine is not in scope.

---

## 7. Where to look next

- **m-cli's own status:** [`README.md`](../README.md), `m --help`.
- **Inner-loop strategy origins:** [`m-tools/docs/m-tooling-
  tier1.md`](../../m-tools/docs/m-tooling-tier1.md) — the
  document that argued for everything m-cli now is.
- **Cross-engine gap analysis:** [`m-tools/docs/m-tool-gap-
  analysis.md`](../../m-tools/docs/m-tool-gap-analysis.md) — Tier
  1–4 ranking and DORA-validated rationale.
- **m-stdlib roadmap:** [`m-stdlib/docs/parallel-tracks.md`](
  ../../m-stdlib/docs/parallel-tracks.md) — live dispatch board
  for the M-side library work, plus the toolchain regressions
  m-stdlib has surfaced for m-cli and tree-sitter-m.
- **m-stdlib release plan:** [`m-stdlib/docs/m-stdlib-
  implementation-plan.md`](../../m-stdlib/docs/m-stdlib-
  implementation-plan.md) — the per-module spec and acceptance
  gate.
- **Parser internals:** [`tree-sitter-m/STATUS.md`](
  ../../tree-sitter-m/STATUS.md) and [`tree-sitter-m/docs/build-
  log.md`](../../tree-sitter-m/docs/build-log.md).
- **Language reference:** [`m-standard/docs/spec.md`](
  ../../m-standard/docs/spec.md) and the ADRs under
  `m-standard/docs/adr/`.

---

## 8. One-line summary

> *m-cli is the clean Python rewrite of m-tools' bash inner-loop
> experiment, made possible by m-standard and tree-sitter-m, and
> validated by m-stdlib running on top of vista-meta.*
