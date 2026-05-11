# Phase 3 Implementation Plan — `m fix`, `m profile`, `m bench`, `m debug`

**Status:** working plan. Phase 3a is shipped; this document scopes Phase 3b and Phase 3c with explicit dependencies and priorities.

**Derived from:** [`language-cli-survey.md`](language-cli-survey.md) §6.2 (phased roadmap) and §4.1 (capability ranks). The phase labels and shape come from there — this doc converts the prose into an actionable punch list.

**Audience:** m-cli contributors picking up the next subcommand; reviewers tracking what's queued.

**Scope:**

- Phase 3b: `m fix`, `m profile`, `m bench`.
- Phase 3c: `m debug` (DAP server + VS Code wiring).
- Cross-cutting: VistA gate, library API surface, performance budgets.

**Not in scope:** Phase 4 (`m pkg` / `m audit` / `m publish` — ecosystem work, year-2+) and Phase 5 polish (`m typecheck`, `m toolchain`, `$PATH`-discovered subcommands). The IRIS portability track in [`iris-ydb-portability.md`](iris-ydb-portability.md) runs in parallel; this plan only notes touchpoints, not deliverables.

---

## 0. Current state — Phase 3a shipped

| Subcommand | Source | Status |
|---|---|---|
| `m doctor` | [`src/m_cli/doctor/cli.py`](../../src/m_cli/doctor/cli.py) | Shipped |
| `m new` | [`src/m_cli/new/cli.py`](../../src/m_cli/new/cli.py) | Shipped |
| `m ci init` | [`src/m_cli/ci/cli.py`](../../src/m_cli/ci/cli.py) | Shipped |
| `m run` | [`src/m_cli/run/cli.py`](../../src/m_cli/run/cli.py) | Shipped |
| `m build` | [`src/m_cli/build/cli.py`](../../src/m_cli/build/cli.py) | Shipped |
| `m doc` | [`src/m_cli/doc/cli.py`](../../src/m_cli/doc/cli.py) | Shipped |

Phase 3a exit criterion is met: `m new` produces a project that passes `m fmt --check && m lint && m test && m coverage` on a clean clone. Everything below builds on the Phase 3a / Tier 1+2 foundation; nothing in this plan revisits it.

---

## 1. Dependency graph

```
   Tier 1+2 foundation (parser · fmt rule engine · lint runner ·
                        WorkspaceIndex · YDB trace · test discovery)
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
  ┌──────────┐              ┌──────────┐             ┌──────────┐
  │  m fix   │              │ m profile│             │ m bench  │
  │  (3b-1)  │              │  (3b-2)  │             │  (3b-3)  │
  └────┬─────┘              └────┬─────┘             └──────────┘
       │                         │
       │ shares fixer_id         │ shares TRACE view
       │ contract with LSP       │ with `m coverage`
       ▼                         ▼
  (Quick Fix code-actions   (flamegraph output ·
   expand to ≥10 rules)      folded-stack format)

  ┌────────────────────────┐
  │ engine ZBREAK / ZSTEP  │
  │ ZSHOW  (existing)      │
  └──────────┬─────────────┘
             ▼
       ┌──────────┐         ┌──────────────────┐
       │ m debug  │  ────▶  │ VS Code DAP wiring│
       │  (3c-1)  │         │      (3c-2)       │
       └──────────┘         └──────────────────┘
```

**Critical-path observations:**

1. `m fix` is the highest-leverage 3b item — every `fixer_id`-tagged lint rule becomes an LSP Quick Fix the day it ships, and future lint rules can register a fixer alongside the rule.
2. `m profile` and `m bench` are independent of `m fix` and of each other. They can ship in parallel.
3. `m debug` depends on no other Phase 3 work. It's gated by DAP-server scope (large, ~4–6 weeks) and can run in parallel with all of 3b.
4. Nothing in 3b/3c blocks Phase 4. The ecosystem work is independent and deliberately a year-2+ commitment.

---

## 2. Priorities — what to ship first

Ranked by leverage (developer time saved per engineering week invested) and by how much existing infrastructure each item reuses.

| Rank | Item | Why first | Effort |
|:---:|---|---|:---:|
| 1 | `m fix` | Promotes every existing `fixer_id`-tagged lint rule into an auto-fix; LSP Quick Fix coverage jumps from 2 → 10+ on day one. Reuses `m fmt` rule engine wholesale. | M (1–2 wk) |
| 2 | `m profile` | Closes the biggest "I can't tell where my routine is slow" gap. Reuses `view "TRACE"` machinery from `m coverage`; folded-stack output is one new formatter. | M (1–2 wk) |
| 3 | `m bench` | Smallest of the three; immediately useful for m-cli's own perf-budget discipline. Reuses test discovery 1:1 (just a different label prefix and a `.m` file-name suffix). | S (3–5 d) |
| 4 | `m debug` (DAP server) | Largest single developer-felt missing feature, but largest scope. Parallelizable, not blocking. | L (4–6 wk) |
| 5 | VS Code DAP wiring | Trivial once `m debug` exists; lands in `tree-sitter-m-vscode`. | S (3–5 d) |

**Recommended sequencing.** Start `m fix` first — it has the steepest payoff curve and the smallest blast radius. Begin `m debug` in parallel if a second contributor is available; otherwise queue 3c after 3b. `m profile` and `m bench` can interleave with `m fix` reviews without contention.

---

## 3. Phase 3b — Generalize existing infrastructure

### 3b-1 · `m fix` — auto-fix recipes + structural search/replace

**Builds on:** `m fmt` rule engine ([`src/m_cli/fmt/`](../../src/m_cli/fmt/)), lint `fixer_id` linkage ([`src/m_cli/lint/__init__.py`](../../src/m_cli/lint/__init__.py) `fixer_for`).

**Deliverables:**

- New subcommand package `src/m_cli/fix/` with `cli.py` + `recipes.py` + `engine.py`.
- Named recipes that wrap a single fmt rule (`m fix trim-trailing-whitespace`).
- Structural search/replace driven by tree-sitter-m queries (`m fix --query 'SET $x=$x+1' --replace 'SET $x=$x+1  ; iterate'`).
- Every lint rule with a `fixer_id` becomes auto-fixable via `m fix --rule M-XINDX-013`.
- LSP `code_actions_for_uri` updated to expose all `fixer_id`-tagged rules (currently exposes 2, target ≥10).
- Idempotency tests: running `m fix` twice on the same source produces no second diff.

**Exit criterion:**

- All currently-registered `fixer_id` mappings are reachable via `m fix --rule <id>`.
- `make check-fixer-linkage` (new gate) asserts every lint rule with a `fixer_id` resolves to a real fmt rule.
- LSP Quick Fix code-action count ≥10 on a fixture file that triggers all auto-fixable rules.
- `make lint-vista` over the configured corpus shows zero regressions in finding counts (auto-fixes change source, not finding semantics).

**Risks:**

- Tree-sitter structural-replace UX is unproven in M; start with named recipes only, defer the `--query` mode if it complicates the first ship.
- Recipe-on-recipe ordering matters once we ship more than one rule that touches the same node type. Document the conflict resolution rule upfront — likely "left-to-right in CLI invocation, deterministic-order if discovered from `fixer_id` set."

---

### 3b-2 · `m profile` — flat profile + folded-stack output

**Builds on:** YDB `view "TRACE"` driver from [`src/m_cli/coverage/runner.py`](../../src/m_cli/coverage/runner.py).

**Deliverables:**

- New subcommand package `src/m_cli/profile/` with `cli.py` + `runner.py` + `output.py`.
- Flat profile: line/label execution counts × time per call, sorted by self-time.
- Folded-stack format compatible with [`flamegraph.pl`](https://github.com/brendangregg/FlameGraph).
- Optional `--svg` flag that shells to `flamegraph.pl` if available; otherwise prints folded stacks for the user to pipe.
- `--baseline FILE` for comparison runs (delta self-time per label).
- Test fixture: profile a real `*TST.m` suite from m-stdlib; assert the slowest label surfaces in the top-N.

**Exit criterion:**

- `m profile FILE.m::tLabel` produces a flat profile with non-zero self-times.
- `m profile --format=folded` output renders correctly in `flamegraph.pl` (manually verified once; CI checks format only, not rendering).
- `make check` includes a smoke test that profiles a known-slow fixture and asserts the hot label is at the top of the flat profile.

**Risks:**

- `view "TRACE"` resolution granularity is per-line, not per-call. Document the limitation; don't promise call-graph reconstruction we can't deliver.
- Time measurement uses `$ZH` (or `$ZHOROLOG`); confirm sub-millisecond resolution on the target YDB version. Fall back to "count-only profiling" if the timer is too coarse for short tests.

---

### 3b-3 · `m bench` — micro-benchmark runner

**Builds on:** `m test` discovery ([`src/m_cli/test/discovery.py`](../../src/m_cli/test/discovery.py)) and runner ([`src/m_cli/test/runner.py`](../../src/m_cli/test/runner.py)).

**Deliverables:**

- New subcommand package `src/m_cli/bench/` with `cli.py` + `discovery.py` + `runner.py` + `output.py`.
- Discovery: `b<UpperCase>` labels in `*BCH.m` files (parser-aware, same pattern as test discovery).
- Timing via `$ZH`; report ops/sec and ns/op.
- `--baseline FILE` for comparison mode (delta ops/sec per label, with significance threshold).
- Output formats: text (default), JSON.
- Document the benchmark-writing convention in [`docs/guide.md`](../guide.md) (analogous to the test section).

**Exit criterion:**

- `m bench` discovers and runs at least one bench file in a real M project (m-stdlib `STDFMT` or `STDREGEX` are obvious candidates).
- Comparison mode flags a deliberate 2× regression in a fixture and surfaces it in the output.
- Zero new dependencies beyond what `m test` already pulls in.

**Risks:**

- Warmup / JIT-like effects are absent in M, but YDB block-cache state isn't. Document that benches should be self-contained or include explicit setup; don't try to auto-warm.

---

## 4. Phase 3c — `m debug` (DAP server + editor wiring)

### 3c-1 · `m debug` — DAP server

**Builds on:** YDB engine primitives (`ZBREAK`, `ZSTEP`, `ZSHOW`) — already used elsewhere in the codebase via [`src/m_cli/engine.py`](../../src/m_cli/engine.py); no new engine work required.

**Deliverables:**

- New subcommand package `src/m_cli/debug/` exposing a [Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/) server over stdio.
- Capabilities: breakpoints (line, conditional), step in/over/out, locals/watch (via `ZSHOW`), call stack, exception breakpoints.
- Driver wraps a `ydb -direct` subprocess; multiplexes DAP messages on stdin/stdout while controlling the YDB process via `ZBREAK` / `ZSTEP`.
- Engine targeting: YDB-first. The `--target-engine` flag accepts `iris` but exit-1's with "not supported yet" — the hook stays in for the IRIS portability track.
- Tests use a fake engine (same pattern as `m test`'s injectable `RunnerFn`) so unit tests don't need a live ydb.

**Exit criterion:**

- A DAP client (manually invoked, no editor) can set a breakpoint, run, hit it, inspect locals, and step through a routine.
- `m debug` survives a 10-minute soak with breakpoints set on a real m-stdlib test suite (no leaks, no orphaned ydb processes).

**Risks:**

- `ZBREAK` semantics across YDB versions: confirm the documented behavior on the pinned minimum YDB version, pin the test suite to that version in CI.
- Variable scoping: M's local variables don't have explicit scopes the way most DAP clients expect. The DAP `Scope` for "locals" maps to "all currently-defined locals via `ZSHOW \"V\"`"; document the mapping upfront.
- Multi-process: YDB can fork worker processes (`JOB`); we will not attempt multi-process debugging in v1. Document and exit-1 if encountered.

---

### 3c-2 · VS Code DAP wiring

**Builds on:** `m debug` server + existing [`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode) extension.

**Deliverables:**

- Register a debug adapter contribution in `tree-sitter-m-vscode/package.json`.
- Launch configuration template: `m debug <routine>` or `m debug --test FILE.m::tLabel`.
- F5 launches a debug session; breakpoints set in the gutter round-trip to the DAP server.
- Documentation update in `tree-sitter-m-vscode/README.md`.

**Exit criterion:**

- Setting a gutter breakpoint, pressing F5 on a `*TST.m` file, hitting the breakpoint, inspecting locals, and stepping through a routine all work without manual `ydb` terminal interaction.

---

## 5. Cross-cutting investments

These thread through every phase and should be budgeted explicitly, not as line items.

| Investment | When | Why |
|---|---|---|
| **VistA gate maintenance.** Re-run `make vista`, `make lint-vista`, smoke tests on every new subcommand that touches the parser or rule engines. | Every PR | The 39,330-routine corpus is the only honest stress test we have. Regressions caught here cost 1 hour; in prod they cost weeks. |
| **Library API stability.** Anything new that out-of-tree tools should consume goes into `m_cli.__all__` and is pinned by [`tests/test_library_api.py`](../../tests/test_library_api.py). | Phase 3b onward | LSP, pre-commit, future IDE integrations all consume the library API. Breaking it is a tax on every consumer. |
| **Performance budget.** Every new subcommand that walks the corpus declares a budget and verifies it. | Phase 3b onward | Lint already costs ~22 s on 16 cores. A `fix` / `profile` / `bench` run that scales linearly to corpus size needs the same `--jobs` discipline up front. |
| **`make check-manifest` drift gate.** Every new subcommand must register a `cli.py` so `make manifest` picks it up into `dist/commands.json`. | Phase 3b onward | The manifest is the tier-1 contract for downstream tooling discovery. |

---

## 6. Decision points to revisit per phase

| Decision | When | Default | Watch for |
|---|---|---|---|
| Continue extending Python codebase vs port hot paths to Rust | End of 3b | Stay in Python | Lint perf regressing past 60 s on VistA; test runner startup overhead becoming visible. |
| `m debug` on YDB only or design for engine-portable DAP | Start of 3c | YDB-first; abstraction comes later if Caché / IRIS users appear | Demand signal from non-YDB users; sponsor for Caché support. |
| Tree-sitter structural-replace UX | During 3b-1 | Ship named recipes only in v1; defer `--query` mode | Recipe coverage stays flat; users hand-rolling `sed` for cross-rule fixes. |
| Profile call-graph reconstruction | During 3b-2 | Flat profile + folded stacks only; no synthetic call graph | Repeated user requests for true call-graph view. |

---

## 7. Suggested Gantt

```
                 W1  W2  W3  W4  W5  W6  W7  W8  W9  W10 W11 W12 …
m fix (3b-1)     █████████████
m profile (3b-2)             █████████████
m bench (3b-3)                           ████████
m debug (3c-1)   ░░░░░░░░░░░░░░░░░░░░░░░░░████████████████████
VS Code DAP (3c-2)                                            ████████
VistA gate       ◄────────── continuous ──────────────────────────►
```

- 3b lands inside ~8 weeks if sequential, ~5 if `m profile` and `m bench` overlap.
- 3c can start at W1 with a second contributor; otherwise picks up at W8. Either way, lands inside one quarter.
- The "two productivity-defining phases (3b + 3c) ship inside one quarter" target from the survey is achievable; the constraint is contributor-count, not technical scope.

---

## 8. Exit criterion for the phase as a whole

Phase 3 is complete when:

1. `m fix`, `m profile`, `m bench`, `m debug` are all documented in [`guide.md`](../guide.md), shipped with tests, and reachable via `m --help`.
2. `make check-manifest` passes — every subcommand is in `dist/commands.json`.
3. LSP Quick Fix coverage is ≥10 rules.
4. A flamegraph generated by `m profile` is checked in as a worked example under [`examples/`](../../examples/).
5. A debug session in VS Code (gutter breakpoint → hit → step → inspect) is documented with screenshots in `tree-sitter-m-vscode/README.md`.
6. The `m-cli` capability surface in `dist/commands.json` matches §6 of [`language-cli-survey.md`](language-cli-survey.md) rows 1–12 (the Tier-1 essentials + Phase 3 deliverables).

When all six are true, the next planning doc is Phase 4 (`m pkg` / `m audit` / `m publish`) — explicitly a year-2+ commitment per the survey, contingent on ecosystem demand signal.
