---
created: 2026-05-11
last_modified: 2026-05-11
revisions: 0
doc_type: [REFERENCE, GUIDE]
---

# m-cli — command menu (by developer journey)

Master reference table for every `m <subcommand>` shipped today.
Rows are arranged in the **order a developer would actually reach
for them** — from "is my box ready?" through "scaffold a project"
through the daily inner loop and out to the ecosystem-integration
surfaces. Each row is tagged by **lifecycle** (which workflow stage
it serves) so the same table can also be skimmed thematically.

Authoritative source: `m capabilities --json` and `m` bare overview.
This document is the human-readable companion — refresh it whenever a
new top-level subcommand lands.

## Lifecycle stages

- **environmental health** — is my dev box ready to run M code?
  (`m doctor`, the `m engine ...` family, `m plugins`).
- **setup project** — bootstrap a new codebase or wire it into CI
  (`m new`, `m ci init`).
- **inner loop** — what you run dozens of times a day while writing
  code: format, lint, hover/completion, run, test, watch, measure
  coverage.
- **integration** — surfaces consumed by downstream tools, AI agents,
  and humans reading library docs: the m-stdlib reference family
  (`m stdlib doc` / `search` / `manifest` / `examples` / `errors`,
  grouped under one namespace since 2026-05-11) and `m capabilities`
  (the machine-readable command surface that backs
  `dist/commands.json`).

## Frequency rating

The **Use** column is a 5-circle visual rating of how often a typical
M programmer reaches for the command on a working day. Filled (●),
half (◐), and empty (○) glyphs lets the column carry sub-unit
resolution.

| Rating | Glyph | Meaning |
|---|---|---|
| 5 | `●●●●●` | continuous / inner loop — fires on every keystroke or save, or runs as a long-lived process (~100×/day at process level) |
| 4 | `●●●●○` | many times per hour (~10–30×/day) |
| 3 | `●●●○○` | a few times per hour (~3–10×/day) |
| 2 | `●●○○○` | several times per day (~1–3×/day) |
| 1 | `●○○○○` | less than once per day on average (debug-driven, session bookend) |
| ½ | `◐○○○○` | rare — weekly or monthly cadence (project setup, image bumps, emergency recovery) |
| 0 | `○○○○○` | not in the human dev loop — tooling-only surface (`make manifest`, CI, AI agents read it; humans almost never type it) |

Ratings reflect a "medium TDD day" with `m lsp` wired into the
editor and the engine container running in the background.
Individual mileage varies — see the [Honest caveats](#honest-caveats)
subsection below the table.

## Run mode

The **Run** column distinguishes commands the developer *types* from
ones that fire *without their direct involvement* — daemons, watchers,
LSP handlers, pre-commit hooks, CI jobs, `make manifest`.

| Glyph | Meaning |
|---|---|
| `⟳` | **continuously used** — runs as a long-lived process (`m lsp`, `m watch`) or fires on every editor save through the LSP (`m fmt`, `m lint`). The developer experiences these as always-on or always-firing, not as commands they type. |
| `▶` | **manual / on-demand** — developer or tooling types / invokes it to get a one-shot result. Includes commands that are machine-readable (`m capabilities`, `m engine capabilities`, `m stdlib manifest`) but only invoked occasionally — being machine-processable does **not** by itself qualify as continuous. |

The split is about *whether the command is in continuous use*, not
whether it can be machine-driven. `m fmt` lands in `⟳` because the
LSP fires it on every save — dozens or hundreds of times an hour.
`m capabilities` lands in `▶` because, even though it's a tooling
surface, it's only invoked when `make manifest` or CI needs to
refresh the JSON — a few times per week, not continuously.

## Master table — the developer core cycle

The 9 commands that drive the day-to-day TDD inner loop, plus the
two scaffolders that get a project into that loop. Reading order
groups the **continuously-used** (`⟳`) commands together as the
always-on backbone of the inner loop (LSP daemon + editor-save
fmt/lint + the test watcher), then the **manual** (`▶`) commands
the developer types: the core test cycle (`test` → `run` →
`coverage`).

M-stdlib reference lookups (`m stdlib doc` / `search` / `examples` /
`errors` / `manifest`) split out into the
[M-stdlib reference](#m-stdlib-reference--library-lookups)
table below — they're occasional and not part of the core cycle.
Environment / engine lifecycle commands plus the rest of the
introspection surface (`m plugins`, `m capabilities`,
`m engine capabilities`) sit in the
[Environment & introspection](#environment--introspection--low-frequency--one-shot)
table further down.

The **Typical use** column is an honest practical estimate for a
"medium TDD day" — an M programmer working in an editor with `m lsp`
wired in, writing tests then implementation, with the engine
container running in the background. Numbers are rough; real-world
spread is wide and depends on what the developer is doing that day
(integrating against m-stdlib heavily? rewriting one large routine?
debugging a transaction-control bug? doing pure refactor?). Treat
the figures as orders-of-magnitude, not benchmarks.

A few patterns worth calling out before reading the column:

- **Editor-triggered** vs **manual** matters. `m fmt` and `m lint`
  fire on every editor save via the LSP — easily 50–200×/day at the
  process level — but the developer rarely *types* them.
- **`m watch` collapses `m test`** into one long-running start.
  Manual `m test` count drops to ~zero when watch is running.

| # | Lifecycle | Run | Command | Use | Typical use | What it does |
|---|---|---|---|---|---|---|
| 1 | setup project | `▶` | `m new <name>` | `◐○○○○` | once per project (~handful/year) | First step for any new project: scaffold a TDD-ready M project (`routines/`, `tests/`, `.m-cli.toml`, Makefile, README) — clean on `m fmt --check && m lint && m test && m coverage` from minute one |
| 2 | setup project | `▶` | `m ci init [--write]` | `◐○○○○` | once per project (~handful/year) | Wire CI once per project: preview / scaffold `.github/workflows/m-ci.yml` (fmt-check + lint + test + coverage). Bare = preview only — pass `--write` to actually create the file |
| 3 | inner loop | `⟳` | `m lsp` | `●●●●●` | `1× session start`, then continuous (~8 hr) | Background always-on once your editor is wired: Language Server over stdio — diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, find-references, workspace symbols |
| 4 | inner loop | `⟳` | `m fmt [PATHS]` | `●●●●●` | **editor-save (50–200×/day at process level)**; manual `0–3×/day` | After writing code: round-trip formatter (default = identity); presets `canonical` / `pythonic` / `pythonic-lower` / `compact`; `--check` / `--diff` / `--stdout` |
| 5 | inner loop | `⟳` | `m lint [PATHS]` | `●●●●●` | **continuous via LSP**; manual `0–3×/day` (CI / pre-commit gate) | After formatting: engine-neutral linter; profiles `default` / `modern` / `pedantic` / `pythonic` / `xindex` / `vista` / `sac` / `all`; `--target-engine` / `--threshold` / `--error-on` / `--jobs` |
| 6 | inner loop | `⟳` | `m watch [PATHS]` | `●●●●○` | `1× start`, then runs all session — **collapses dozens of `m test` runs** | Long-running TDD loop: polling file watcher (no inotify dep); source→suite affinity (`FOO.m` → `FOOTST.m`); `--once` / `--interval` / `--filter` |
| 7 | inner loop | `▶` | `m test [PATHS]` | `●●●●○` | **`5–30×/day`** if invoked manually; **~0** if `m watch` is running | Run the suite: parser-aware suite + test discovery (`*TST.m`, `t<Upper>(pass,fail)`); `STDASSERT` protocol; `FILE.m::tLabel` selector; `--changed` / `--seed` / `--env` / `--update-snapshots` / `--timings` / `--timeout`; text / TAP / JSON / JUnit output |
| 8 | inner loop | `▶` | `m run ENTRYREF` | `●○○○○` | `0–10×/day` (debug-driven; bursts during incident response) | Ad-hoc execution for debugging or one-offs: routes via `detect_engine()` so docker / SSH / local all work transparently. Args after `--` flow to `$ZCMDLINE`; `--routines PATH` prepends to the stage; rc passthrough |
| 9 | inner loop | `▶` | `m coverage [PATHS]` | `●○○○○` | `1–3×/day` (pre-commit; PR gate) | Gate before commit / PR: label + line + branch coverage via YDB `view "TRACE"`; text / `text --lines` / JSON / LCOV output; `--min-percent` CI gate; `--uncovered` |

## M-stdlib reference — library lookups

Six sub-verbs nested under the `m stdlib` namespace (grouped there
since 2026-05-11 — see [`evolution.md`](evolution.md) "Renames /
namespace moves"; `list` added in the same week). They surface the
[m-stdlib](https://github.com/m-dev-tools/m-stdlib) manifest as a
developer-facing reference. Not part of the daily edit-run-test
cycle — reach for them when integrating against the library:
discover what's available (`m stdlib list`), look up an API
(`m stdlib doc` / `search` / `examples`), trace an error code
back to its raising labels (`m stdlib errors`), or pull JSON for
jq pipelines (`m stdlib manifest`).

All `▶` manual. Frequency depends heavily on what the developer is
doing that day — heavy when wiring up new library calls, near-zero
on internal-only work.

| # | Run | Command | Use | Typical use | What it does |
|---|---|---|---|---|---|
| 1 | `▶` | `m stdlib list` | `●○○○○` | `0–2×/day` (discoverability — "what's in stdlib?") | List every m-stdlib module with its one-line synopsis, sorted; `--json` for tooling |
| 2 | `▶` | `m stdlib doc [SYMBOL]` | `●●○○○` | `0–15×/day` (heavy when integrating m-stdlib; near-0 on pure-internal days) | Research a library API before you call it: godoc-style symbol lookup over the m-stdlib manifest — module overview, single-label long form, or fuzzy lookup |
| 3 | `▶` | `m stdlib search <query>` | `●○○○○` | `0–5×/day` (when you don't know the symbol name) | Fuzzy lookup when you don't know the symbol name: full-text AND-style search over synopsis / description / examples; tiered ranking (synopsis > description > examples) |
| 4 | `▶` | `m stdlib examples [MODULE]` | `●○○○○` | `0–3×/day` | See real usage patterns: print every `@example` from the manifest, prefixed with `module.label:` (greppable) |
| 5 | `▶` | `m stdlib errors` | `◐○○○○` | `0–2×/day` (when debugging a `$ECODE`) | Figure out where a `$ECODE` came from: inverted index of every `U-STD*` error code → the modules and labels that raise it |
| 6 | `▶` | `m stdlib manifest [path]` | `◐○○○○` | `<1×/day` (mostly tooling) | Lower-level JSON pull for tooling / agents: emit the resolved m-stdlib manifest (or a `STDJSON` / `STDJSON.parse` sub-path) as JSON — pipe-friendly for `jq` |

## Environment & introspection — low-frequency / one-shot

The 14 commands that keep the dev environment alive and expose
m-cli / engine internals to tooling, but rarely run during a
steady-state coding session. Three clusters:

- **Engine lifecycle** (bootstrap → debug → maintenance): `m doctor`
  · `m engine install` / `start` / `status` / `stop` / `restart` /
  `reset` · debug-driven `m engine exec` / `shell` / `logs` ·
  `m engine version` after image bumps.
- **Plugin enumeration**: `m plugins`.
- **Machine-readable surfaces** (dominantly tooling-invoked, ~0
  manual): `m capabilities` (backs `dist/commands.json`) and
  `m engine capabilities`.

All `▶` manual — none are continuously firing.

| # | Run | Command | Use | Typical use | What it does |
|---|---|---|---|---|---|
| 1 | `▶` | `m doctor` | `●○○○○` | `0–2×/day` (mostly 0; spike when something feels off) | First touch on any fresh box: environment self-check; transport-aware (selects local / docker / ssh checks per detected engine); docker is the default when no other transport is configured; `--fix` delegates to `m engine` verbs |
| 2 | `▶` | `m engine install` | `◐○○○○` | once per image rev (~monthly) | Day-zero bootstrap: pull the canonical engine image (`docker pull ghcr.io/m-dev-tools/m-test-engine:<tag>`) |
| 3 | `▶` | `m engine start` | `●○○○○` | `0–1×/day` (start of session) | Start the engine container (compose-first; `docker run` fallback). Idempotent across absent / stopped / running |
| 4 | `▶` | `m engine status` | `●○○○○` | `0–3×/day` (mostly 0; spikes during debugging) | Verify running state — container / image / daemon; `--verbose` populates the in-container `mte` payload and surfaces version skew |
| 5 | `▶` | `m engine exec <m-cmd>` | `●○○○○` | `0–5×/day` (debug-driven) | Debugging: run a one-shot M command via `mumps -run %XCMD` inside the engine |
| 6 | `▶` | `m engine shell` | `●○○○○` | `0–2×/day` (deeper debugging) | Deeper debugging: interactive bash shell inside the container |
| 7 | `▶` | `m engine logs` | `●○○○○` | `0–3×/day` (when test results look wrong) | Diagnose container issues: print container logs; `--follow` to stream |
| 8 | `▶` | `m engine version` | `◐○○○○` | `<1×/week` (after image bump) | Check after image bump: manifest-declared vs container-reported versions (table with ✓/✗) |
| 9 | `▶` | `m engine restart` | `●○○○○` | `0–1×/day` (when state's wonky) | When state gets weird: stop + start |
| 10 | `▶` | `m engine stop` | `●○○○○` | `0–1×/day` (end of session) | End of day / context switch: stop the engine container (globals volume preserved) |
| 11 | `▶` | `m engine reset` | `◐○○○○` | `<1×/month` (emergency only) | **Destructive** — last-resort recovery: stop + remove + drop globals volume; gated behind `--confirm` |
| 12 | `▶` | `m plugins` | `◐○○○○` | `<1×/month` (one-shot check) | See what extras the user has installed: list out-of-tree subcommands registered via the `m_cli.plugins` entry-point group |
| 13 | `▶` | `m capabilities` | `○○○○○` | tooling-only (~0 manual; `make manifest` hits it 1–2×/week) | Machine-readable surface for CI / AI agents / `make manifest`: interactive TTY = short overview · piped or `--json` = full JSON (backs `dist/commands.json`) |
| 14 | `▶` | `m engine capabilities` | `○○○○○` | tooling-only (~0 manual) | Programmatic introspection: engine namespace's machine-readable capabilities (JSON) |

### Rating roll-up

Sorted from most-used to least, ignoring textual nuance:

| Rating | Commands |
|---|---|
| `●●●●●` (5) | `m lsp` · `m fmt` · `m lint` |
| `●●●●○` (4) | `m test` · `m watch` |
| `●●●○○` (3) | — |
| `●●○○○` (2) | `m stdlib doc` |
| `●○○○○` (1) | `m doctor` · `m engine start` · `m engine status` · `m engine restart` · `m engine stop` · `m engine exec` · `m engine shell` · `m engine logs` · `m stdlib list` · `m stdlib search` · `m stdlib examples` · `m run` · `m coverage` |
| `◐○○○○` (½) | `m engine install` · `m engine version` · `m engine reset` · `m new` · `m ci init` · `m stdlib errors` · `m stdlib manifest` · `m plugins` |
| `○○○○○` (0) | `m engine capabilities` · `m capabilities` |

### Run-mode roll-up

| Mode | Commands |
|---|---|
| `⟳` continuously used (4) | `m lsp` · `m watch` · `m fmt` · `m lint` |
| `▶` manual / on-demand (24) | everything else, including the machine-readable `m capabilities` / `m engine capabilities` / `m stdlib manifest` (tooling-invoked but not continuous) |

### Honest caveats

- **Different developer profiles see very different numbers.** A
  *library author* (writing m-stdlib code) lives in `m fmt` / `m lint`
  / `m test` and barely touches `m stdlib doc`. A *library consumer*
  (writing an app on top of m-stdlib) inverts that: `m stdlib doc` is hot,
  many lint rules don't fire. An *infra-/CI person* lives in
  `m engine` and `m doctor`.
- **Process-level vs human-keystroke counts diverge by orders of
  magnitude** once you wire the LSP. The honest number for "how
  often does the developer think about `m fmt`?" on a good day is
  zero — the editor handles it silently on save.
- **`m watch` is the great consolidator.** Adopt it and your manual
  `m test` count goes from ~25/day to ~0; trade-off is one
  long-running terminal pane.
- The **`m engine` family is bimodal.** On a healthy day: `start`
  in the morning, `stop` at night, everything else stays at 0. On a
  debugging day: `status` / `logs` / `exec` / `shell` fire in
  bursts of 5–15 in an hour, then back to 0 for days.
- **Project-setup commands (`m new`, `m ci init`)** look low only
  because the unit is "per developer per year." Per *new project*
  they're 100% — you can't skip them and stay on the golden path.

## Dispatcher tree

The literal CLI topology — what `m --help` and `m capabilities` walk.
Two of the top-level entries (`m ci`, `m engine`) are themselves
dispatchers with their own verb sets; everything else is a leaf.

```
m
├── fmt                 format M source files
├── lint                lint M source files
├── test                run M test suites
├── watch               re-run test suites on file change
├── coverage            measure test coverage
├── lsp                 Language Server over stdio
├── engine              manage the m-test-engine container
│   ├── status              container / image / daemon state
│   ├── install             pull the canonical engine image
│   ├── start               start the container
│   ├── stop                stop (globals volume preserved)
│   ├── restart             stop + start
│   ├── logs                print container logs
│   ├── shell               interactive bash inside the container
│   ├── exec <m-cmd>        run a one-shot M command
│   ├── version             manifest vs container version table
│   ├── reset               DESTRUCTIVE — drop globals volume
│   └── capabilities        engine namespace JSON surface
├── doctor              environment self-check
├── new <name>          scaffold a TDD-ready M project
├── ci                  CI scaffolding
│   └── init                preview / scaffold m-ci.yml (--write)
├── run <entryref>      run an M routine via `ydb -run`
├── stdlib              m-stdlib reference (list/doc/search/...)
│   ├── list                list every module with its synopsis
│   ├── doc [symbol]        godoc-style symbol lookup
│   ├── search <query>      full-text search over the manifest
│   ├── examples [module]   print every @example
│   ├── errors              U-STD* error codes → producing labels
│   └── manifest [path]     emit the manifest as JSON
├── plugins             list out-of-tree subcommands
└── capabilities        machine-readable command surface (JSON)
```

14 top-level commands · 11 `m engine` subverbs · 6 `m stdlib`
subverbs · 1 `m ci` subverb · 29 distinct invocations end-to-end.

## Lifecycle quick view

The same surface, sliced by lifecycle stage instead of domain.

| Stage | Commands |
|---|---|
| **environmental health** | `m doctor` · `m engine status` · `m engine install` · `m engine start` · `m engine stop` · `m engine restart` · `m engine logs` · `m engine shell` · `m engine exec` · `m engine version` · `m engine reset` · `m engine capabilities` · `m plugins` |
| **setup project** | `m new` · `m ci init` |
| **inner loop** | `m fmt` · `m lint` · `m lsp` · `m test` · `m watch` · `m coverage` · `m run` |
| **integration** | `m stdlib list` · `m stdlib doc` · `m stdlib search` · `m stdlib manifest` · `m stdlib examples` · `m stdlib errors` · `m capabilities` |

## Cross-cutting notes

**Engine-neutral vs engine-bound.** Source-level tools (stdlib +
development columns) parse M with `tree-sitter-m` and need no
YottaDB. Runtime tools (testing column) auto-detect transport via
`m_cli.engine.detect_engine`: `$M_CLI_ENGINE` env override → docker
(default) → local YDB → SSH.

**Exit codes.** Every command follows the org
[CLI-UX conventions guide](cli-frameworks/cli-ux-conventions-guide.md)
§3.7:

- **0** — success (also "nothing to do" for `m test` / `m watch` /
  `m fmt` / `m lint` / `m coverage` when there are no files / suites
  to act on).
- **1** — domain failure (missing manifest, missing `ydb` binary, lint
  diagnostics above `--error-on`, coverage below `--min-percent`).
- **2** — usage error (unknown flag, missing required positional;
  argparse-level).

**Bare invocation.** Every dispatcher (`m`, `m ci`, `m engine`) prints
a gh-style two-line description + indented COMMANDS block to stdout at
exit 0 — `m fmt` etc. follow the leaf rules of the guide (sensible
default or named error). The one intentional divergence is `m lsp`,
which is a filter-family leaf: bare invocation enters server mode on
stdin/stdout, like `python` or `psql`. See
[`AGENTS.md`](../AGENTS.md) § LSP server for the rationale.

**Configuration.** `m fmt`, `m lint`, and `m lsp` all read project
config from `.m-cli.toml` (preferred) or `[tool.m-cli]` in
`pyproject.toml`. Discovery walks up from cwd, stopping at `.git`.
Schema and resolution order are in
[`guide.md`](guide.md) § Configuration.

## Related references

- [`guide.md`](guide.md) — comprehensive user guide, every flag and profile.
- [`m-linting-user-guide.md`](m-linting-user-guide.md) — deep dive on `m lint`.
- [`plugin-development.md`](plugin-development.md) — how out-of-tree subcommands register against the `m_cli.plugins` entry-point group.
- [`pre-commit.md`](pre-commit.md) — wiring `m fmt --check` / `m lint` into downstream projects.
- [`evolution.md`](evolution.md) — chronological history of how each subcommand came to exist.
