# m-cli — the M (MUMPS) source-level toolchain

The canonical `m <subcommand>` developer toolchain for the M (MUMPS)
language: `m fmt` (formatter), `m lint` (linter), `m test` (test runner),
`m coverage` (line + branch coverage), `m doc` (m-stdlib reference
lookup), `m lsp` (Language Server), `m watch`, plus orientation
helpers `m doctor` / `m new` / `m run` / `m build` / `m ci init`.

Built on:
- **[m-standard](https://github.com/m-dev-tools/m-standard)** — the language reference (commands / ISVs / functions / SAC overlay)
- **[tree-sitter-m](https://github.com/m-dev-tools/tree-sitter-m)** — the parser (99.06% clean on the 39,330-routine VistA corpus)
- **[m-test-engine](https://github.com/m-dev-tools/m-test-engine)** — minimal YottaDB Docker container for `m test` / `m coverage` (default; legacy vista-meta SSH path also supported via `M_CLI_ENGINE=ssh`)

The source-level tools (`m fmt`, `m lint`, `m doc`, `m lsp`) are
engine-neutral; runtime tools (`m test`, `m coverage`) target YottaDB
primarily with IRIS portability documented per-feature.

## Status

| Subcommand | Status |
|---|---|
| `m fmt` | **Shipped** — identity round-trip 99.04% byte-for-byte on the 39,330-routine VistA corpus; `--rules=canonical` (trim + uppercase), plus the Phase A translation presets `pythonic` / `pythonic-lower` / `compact` for converting between VistA-compact and canonical-name forms. Idempotent + AST-preserving. |
| `m lint` | **Shipped** — engine-neutral lint engine + 7 named profiles. **Default profile = curated M-MOD daily-lint subset** (26 rules, ~3 findings/routine on the 4K-routine modern corpus); the full M-MOD modernization track is 35 rules across length/complexity, concurrency, transactions, control-flow, portability. Plus the legacy 34-rule `xindex` profile (VA VistA Toolkit port) and the 8-rule `vista` profile (VA Kernel-specific). Path-sensitive flow analysis (CFG + reaching-def + LOCK / TSTART / $ETRAP / $TEST / taint state) is wired; M-MOD-024 / 025 / 026 / 027 / 036 ride on it. See the Linter section below for the full rule + profile breakdown. |
| `m test` | **Shipped** — parser-aware suite + label discovery; YottaDB runner via the multi-transport `Engine` abstraction (Local / Docker / SSH); text / TAP / JSON / JUnit output. Supports `--filter`, single-test selection (`m test FILE.m::tLabel`), `--changed` (diff-driven runs), `--seed` / `--update-snapshots` / `--env` / `--timings` / `--no-isolation` consuming m-stdlib's TDD primitives. |
| `m coverage` | **Shipped** — line + branch coverage via YottaDB's `view "TRACE"`; output formats `text` / `text --lines` / `json` / `lcov`. Label-level on m-tools 85/123 (69.1%); line-level 340/637 (53.4%). |
| `m watch` | **Shipped** — polling-based file watcher with source→suite affinity (`FOO.m` change → `FOOTST.m` re-run). |
| `m lsp` | **Shipped through Phase B** — diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, find-references, workspace symbol search, incremental index updates. Stdio transport; pip-extra `m-cli[lsp]`. |
| `m doc` | **Shipped** — m-stdlib reference lookup (`m doc parse^STDJSON` → signature / params / examples). |
| `m doctor` / `m new` / `m run` / `m build` / `m ci init` | **Shipped** — Phase 3a quick-win orientation + scaffolding helpers. |
| `m plugins` (Track D 6a) | **Shipped** — entry-points-based plugin discovery in the `m_cli.plugins` group. Out-of-tree subcommands are in [`m-cli-extras`](https://github.com/m-dev-tools/m-cli-extras) (first plugin: `m corpus-stats`). |

## Linter — `m lint`

`m lint` is engine- and dialect-neutral by design: the lint engine
registers rules and runs them, while opinionated rule sets ship as
named **profiles**. This separation keeps m-cli from privileging any
single dialect (VistA, IRIS, YottaDB, ANSI) and makes it easy to
extend the rule library without forcing existing projects to rename
their config.

**Built-in profiles** (run `m lint --list-profiles` for the live list):

| Profile | Rules | Notes |
|---------|-------|-------|
| `default` | 26 | **Curated daily-lint set** — the M-MOD-NN modernization track *minus* the four pedantic style rules (M-MOD-009 commands-per-line, M-MOD-028 label-docstring, M-MOD-031 magic-numbers, M-MOD-032 single-letter-vars). Validated against 4K-routine non-VA corpus: ~3 findings/routine. This is what `m lint` runs when no `--rules` flag is given. |
| `modern` | 30 | Full M-MOD-NN track — every rule tagged `modern`, including the four pedantic style rules. Use for the strict review pass; on a 4K-routine non-VA corpus produces ~57 findings/routine, mostly from M-MOD-031/032. |
| `pedantic` | 4 | Just the four pedantic style rules — useful for a focused style pass. |
| `pythonic` | 30 | **Preset for developers coming from Python.** Same rules as `modern` (Python culture wants long names, no magic numbers, one statement per line, label docstrings) plus tighter thresholds: `line_length=100`, `commands_per_line=1`, `argument_count=5`, `cyclomatic=10`, `cognitive=15`, `dot_block_depth=3`, `label_lines=30`. Override any threshold via `[lint.thresholds]` or `--threshold`. |
| `xindex` | 34 | VA VistA Toolkit `^XINDEX` port, engine-neutral subset. The 34 ported rules that don't require VA Kernel APIs. **XINDEX itself is a VA tool — not part of the M standard, not shipped by IRIS or YottaDB.** Use this for VistA-style discipline. |
| `vista` | 8 | VA VistA-Kernel-specific rules: `OPEN`→`^%ZIS`, `CLOSE`→`^%ZISC`, `HALT`→`^XUSCLEAN`, `JOB`→TASKMAN, `$SYSTEM` Kernel-only, plus VistA banner conventions (1st/2nd-line SAC, patch number). Opt-in via `--rules=vista`; emits pure false positives outside VistA. |
| `sac` | 23 | VA SAC (Standards & Conventions) portable subset — `sac`-tagged rules minus VistA-Kernel ones. |
| `all` | 72 | Every registered rule, regardless of profile. |

**XINDEX-derived rules** (34 of XINDEX's 66, surfaced via the `xindex` profile):

| ID | Severity | Title |
|----|----------|-------|
| M-XINDX-002 | Standard | Non-standard Z command used |
| M-XINDX-013 | Warning  | Blank(s) at end of line |
| M-XINDX-014 | Fatal    | Call to missing label in this routine |
| M-XINDX-015 | Warning  | Duplicate label |
| M-XINDX-017 | Warning  | First line label NOT routine name |
| M-XINDX-018 | Warning  | Line contains a CONTROL (non-graphic) character |
| M-XINDX-019 | Standard | Line is longer than 245 bytes |
| M-XINDX-020 | Standard | VIEW command used |
| M-XINDX-021 | Fatal    | Syntax error in line (parse failure) |
| M-XINDX-022 | Standard | Exclusive Kill |
| M-XINDX-023 | Standard | Unargumented Kill |
| M-XINDX-024 | Standard | Kill of unsubscripted global |
| M-XINDX-025 | Standard | BREAK command used |
| M-XINDX-026 | Standard | NEW exclusive or unargumented |
| M-XINDX-027 | Standard | $VIEW function used |
| M-XINDX-028 | Standard | $Z* intrinsic special variable used |
| M-XINDX-029 | Standard | CLOSE command — use ZISC instead |
| M-XINDX-030 | Standard | LABEL+OFFSET reference (fragile) |
| M-XINDX-031 | Standard | $Z* intrinsic function used |
| M-XINDX-032 | Standard | HALT command — use XUSCLEAN instead |
| M-XINDX-033 | Warning  | READ without timeout |
| M-XINDX-034 | Standard | OPEN command — use ZIS instead |
| M-XINDX-035 | Standard | Routine exceeds SACC maximum size of 20000 bytes |
| M-XINDX-036 | Standard | JOB command — use TASKMAN instead |
| M-XINDX-041 | Standard | Star/pound READ format |
| M-XINDX-042 | Warning  | Null line (no commands or comment) |
| M-XINDX-044 | Standard | 2nd line of routine violates the SAC |
| M-XINDX-045 | Standard | Set to %global |
| M-XINDX-047 | Standard | Lowercase command(s) used in line |
| M-XINDX-050 | Standard | Extended global reference |
| M-XINDX-054 | Standard | $SYSTEM access — Kernel-only |
| M-XINDX-056 | Info     | Patch number reference |
| M-XINDX-058 | Standard | Code line >15000 bytes |
| M-XINDX-060 | Warning  | LOCK without timeout |
| M-XINDX-061 | Standard | Non-incremental LOCK |
| M-XINDX-062 | Standard | First-line SAC violation |

**Rule selection:**

```bash
m lint <paths>                           # default: --rules=default
m lint --list-profiles                   # show available profiles
m lint --rules=xindex <paths>            # VA VistA Toolkit profile
m lint --rules=all <paths>               # every registered rule
m lint --rules=M-XINDX-014,M-XINDX-015 <paths>  # explicit list
m lint --format=json <paths>             # machine-readable
m lint --format=tap <paths>              # CI integration
m lint --error-on=fatal <paths>          # exit-1 only on fatal
```

**Engine targeting (recommended):** if your code targets a specific
M engine (YottaDB or IRIS), set `--target-engine` to silence the
engine-portability rules' false positives. The default (`any`) flags
*every* `$Z*` token as non-portable; on engine-specific code this
generates thousands of irrelevant findings dominated by
`M-MOD-021` / `M-MOD-022` / `M-MOD-023`.

```bash
m lint --rules=default --target-engine=yottadb <paths>
m lint --rules=default --target-engine=iris <paths>
```

Persist via `.m-cli.toml` so you don't need the flag every run:

```toml
[lint]
target_engine = "yottadb"   # or "iris"; "any" = portable lint
```

When the linter detects a heavy load of portability-rule findings
under `target_engine=any`, it surfaces a one-line hint at the end
of the run pointing here. (Real impact on YottaDB code: a recent
audit measured 134,848 → 125,561 findings (-7%) just from setting
`--target-engine=yottadb`.)

The XINDEX-parity rule pack will grow incrementally toward the full 66-rule baseline. After parity, `m lint` extends with parser-aware checks XINDEX cannot do (deeper control-flow analysis, dead-code detection, naked-reference hazards, etc.). New rules from non-VA sources will use their own ID prefix (e.g. `M-IRIS-NN`, `M-YDB-NN`) and ship under their own profile.

### VistA-corpus baseline

`make lint-vista` runs `m lint --rules=xindex,vista` over the full 39,330-routine VistA corpus — explicitly selecting both the engine-neutral XINDEX subset and the VistA-Kernel-specific profile, since the corpus is VistA itself. (Non-VistA shops should run `m lint --rules=xindex` or `--rules=default`.)

```
total routines : 39,330  (38,954 linted, 376 skipped on parse error)
routines flagged : 24,877 (63.9%)
total findings : 62,806
elapsed        : ~1458 s (~27 routines/s)

By rule (descending):
  M-XINDX-013  35,214  trailing blanks
  M-XINDX-056  10,867  patch number references          (INFO)
  M-XINDX-060   5,621  LOCK without timeout
  M-XINDX-044   3,556  2nd-line SAC
  M-XINDX-033   2,652  READ without timeout
  M-XINDX-030   1,602  LABEL+OFFSET reference
  M-XINDX-047   1,330  lowercase command
  M-XINDX-061     419  non-incremental LOCK
  M-XINDX-017     333  first label != routine name
  M-XINDX-045     286  Set to %global
  M-XINDX-041     203  star/pound READ
  M-XINDX-050     144  extended global reference
  M-XINDX-042     138  null line
  M-XINDX-034     109  OPEN — use ZIS
  M-XINDX-029      98  CLOSE — use ZISC
  M-XINDX-014      42  call to missing label             (FATAL — real bugs)
  M-XINDX-025      39  BREAK command
  M-XINDX-062      33  first-line SAC violation
  M-XINDX-019      31  line >245 bytes
  M-XINDX-032      23  HALT — use XUSCLEAN
  M-XINDX-036      15  JOB — use TASKMAN
  M-XINDX-024      14  kill of unsubscripted global
  M-XINDX-058      12  code line >15000 bytes
  M-XINDX-020       8  VIEW command
  M-XINDX-022       6  exclusive Kill
  M-XINDX-023       5  unargumented Kill
  M-XINDX-035       4  routine >20000 bytes
  M-XINDX-026       2  NEW exclusive/unargumented

By severity:
  fatal        42
  standard 26,876
  warning  35,685
  info        203
```

The 42 fatal findings are concrete missing-label bugs (e.g., `A1BFJOBR.m` calls `EXIT` on lines 5 and 6, but no `EXIT` label is defined in the file).

**Coverage:** 28 of 36 registered rules fire on the VistA corpus. The 8 silent rules cover patterns rare in VistA (non-standard `Z` commands, `$Z*` ISVs/funcs, `$SYSTEM`, `$VIEW`, parse-error fallback) — they remain registered for use against more diverse codebases.

**Performance:** the corpus-lint budget is 120 s. Single-pass dispatcher
(`NodeIndex` walks each parse tree once and groups by node type;
rules consume `index.of("X")` instead of running their own walks)
cut serial lint time from ~1458 s to 166 s (8.7×). With
`m lint --jobs N` (default `os.cpu_count()`) on a 16-core host the
full VistA corpus lints in **22.6 s — 5.3× under budget, 64.5× faster
than the original**. Findings byte-identical at every step.

## Install (development)

```bash
cd ~/projects/m-cli
make install      # uv sync --extra dev + pre-commit hooks
```

## Use

```bash
m --version                          # m-cli 0.1.0
m fmt path/to/routine.m              # rewrite in place (identity, default)
m fmt --rules=canonical path/        # SAC hygiene: trim + uppercase
m fmt --rules=pythonic path/         # expand abbreviations: S→SET, $L→$LENGTH
m fmt --rules=pythonic-lower path/   # same but lowercase: set, $length, $test
m fmt --rules=compact path/          # compact canonical names: SET→S, $LENGTH→$L
m fmt --check src/routines/          # CI mode: exit 1 if any file would change
m fmt --diff path/to/routine.m       # unified diff
m fmt --stdout single_file.m         # write to stdout
```

The `pythonic` and `compact` presets translate between VistA-compact code
(`S X=1 W $L(X),$T`) and canonical-name code (`SET X=1 WRITE $LENGTH(X),$TEST`)
for readers coming from Python or other modern languages without the M
tradition of one-/two-character abbreviations. `pythonic-lower` is the
PEP-8-flavoured variant that produces all-lowercase output
(`set X=1 write $length(X),$test`). All three presets are *normalizing*
(idempotent and AST-shape-preserving) and round-trip on already-
normalized input (`compact(pythonic(compact(src))) == compact(src)`).

## Run the round-trip gate against an M corpus

```bash
make vista                                                  # default: m-modern-corpus
make vista CORPUS=$HOME/path/to/some/Packages               # override
```

The default points at
[`m-modern-corpus`](https://github.com/m-dev-tools/m-modern-corpus)
(in-org). Maintainers with a VistA checkout override `CORPUS`
to that path to exercise the full 39,330-routine VistA gate
(~99.04% round-trip clean; parse errors in the remaining ~0.96%
match the [tree-sitter-m corpus boundary](https://github.com/m-dev-tools/tree-sitter-m)).

## Naming convention

Commands follow the universal `m <subcommand>` pattern (mirroring `cargo`,
`go`, `git`). m-cli is the canonical interface; older bash-prototype
tooling is retired.

## Layout

```
m-cli/
├── pyproject.toml              # uv-managed; tree-sitter-m URL-pinned to the GitHub release wheel
├── src/m_cli/
│   ├── cli.py                  # `m` dispatcher (argparse subcommands + plugin discovery)
│   ├── parser.py               # tree-sitter-m wrapper (lru_cached Language/Parser)
│   ├── plugins.py              # entry-points-based plugin discovery (Track D 6a)
│   ├── engine.py               # multi-transport Engine: LocalEngine / DockerEngine / SSHEngine
│   ├── fmt/                    # `m fmt` — formatter + Phase A translation rules
│   ├── lint/                   # `m lint` — rule registry + 7 profiles + path-sensitive flow analysis
│   ├── test/                   # `m test` — parser-aware discovery + ydb runner + TAP/JSON/JUnit output
│   ├── coverage/               # `m coverage` — line + branch via `view "TRACE"`
│   ├── watch/                  # `m watch` — polling-based, source→suite affinity
│   ├── lsp/                    # `m lsp` — diagnostics, formatting, code actions, hover, completion,
│   │                           #          go-to-def, find-refs, workspace symbol, code lens, signature help
│   ├── doc/                    # `m doc` — m-stdlib reference lookup
│   └── workspace/              # cross-routine label index (Phase B)
├── tests/                      # pytest — one file per source module; 1300+ tests
├── scripts/
│   ├── vista_round_trip.py     # corpus round-trip gate driver
│   └── vista_lint.py           # corpus lint baseline driver
├── docs/                       # guide.md, m-linting-survey.md, plugin-development.md, m-cli-history-and-evolution.md, …
├── Makefile                    # `make install` / `test` / `lint` / `mypy` / `cov` / `check` / `vista` / `lint-vista` / `engine-up` / `engine-down`
└── README.md                   # this file
```

## Roadmap

The Tier 1 + Tier 2 toolchain is shipped; current work is in
[`TODO.md`](TODO.md). Live status is tracked in the M-language ecosystem
sprint plan — the [m-dev-tools self-containment work](https://github.com/m-dev-tools)
closed in May 2026, leaving Tier 6c (audit-and-migrate niche subcommands
into `m-cli-extras`) and post-soak polish as the remaining items.

## Licence

AGPL-3.0, matching m-standard, m-stdlib, and tree-sitter-m.
