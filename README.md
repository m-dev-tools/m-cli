# m-cli — the M (MUMPS) source-level toolchain

`m fmt`, `m lint`, `m test` for the M (MUMPS) language. **Tier 1** of the M
ecosystem gap-remediation plan ([strategy doc](../m-tools/docs/m-tooling-tier1.md)).

Built on:
- **[m-standard](https://github.com/rafael5/m-standard)** — the language reference
- **[tree-sitter-m](https://github.com/rafael5/tree-sitter-m)** — the parser (99.06% clean on the 39,330-routine VistA corpus)
- **YottaDB** — open-source M engine; the test runner adapter targets YottaDB primarily, with the source-level tools (`m fmt`, `m lint`) engine-neutral

## Status

| Step | Tool | Status |
|------|------|--------|
| 1 | `m fmt` (formatter) | **Step 1.0 + canonical + Phase A translation** — identity round-trip 38,954 / 39,330 (99.04%); `--rules=canonical` adds trim + uppercase; `--rules=pythonic` / `--rules=compact` translate between VistA-compact and canonical-name forms |
| 2 | `m lint` | **Step 2.1 shipped** — engine-neutral lint engine; the `xindex` profile (VA VistA Toolkit port) provides 42 of the 66 XINDEX rules. See Linter section below |
| 3 | `m test` | Planned (parser-aware port of `ytest`) |
| 4 | Single-test selection | Folded into `m test` |
| 5 | `m watch` | Planned |

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

**Rules shipped in Step 2.1** (42 of XINDEX's 66, surfaced via the `xindex` profile):

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

The XINDEX-parity rule pack will grow incrementally toward the full 66-rule baseline. After parity, `m lint` extends with parser-aware checks XINDEX cannot do (deeper control-flow analysis, dead-code detection, naked-reference hazards, etc.). New rules from non-VA sources will use their own ID prefix (e.g. `M-IRIS-NN`, `M-YDB-NN`) and ship under their own profile.

### VistA-corpus baseline (Step 2.1)

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

**Performance note:** the §3.5 budget for `m lint` on the corpus is 120 s. Step 2.1 runs in 1458 s — **12× over budget**, on a single thread, with a naive AST walk per rule. The 4.6× slowdown vs Step 2.0 (316 s) tracks the rule-count growth from 11 to 36. Optimisation work (parallelism, single-pass walk, selective rule activation) is sequenced as a follow-up; correctness comes first.

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

## Run the VistA round-trip gate

```bash
.venv/bin/python scripts/vista_round_trip.py \
    ~/vista-meta/vista/vista-m-host/Packages
```

Expected output: ~99.04% round-trip clean, parse errors in the
remaining ~0.96% match the [tree-sitter-m corpus boundary](https://github.com/rafael5/tree-sitter-m).

## Naming convention

Commands follow the universal `m <subcommand>` pattern (mirroring `cargo`,
`go`, `git`). The legacy `y*` shell tools in [m-tools/bin/](../m-tools/bin/)
are kept as references and templates only — they remain functional but
are not the canonical interface going forward.

## Layout

```
m-cli/
├── pyproject.toml              # uv-managed; tree-sitter-m as editable dep
├── src/m_cli/
│   ├── __init__.py
│   ├── cli.py                  # `m` dispatcher
│   ├── parser.py               # tree-sitter-m wrapper
│   └── fmt/
│       ├── __init__.py
│       ├── cli.py              # `m fmt` argparse + file orchestration
│       └── formatter.py        # the round-trip pretty-printer
├── tests/
│   └── test_formatter.py       # round-trip + idempotence + parse-error tests
├── scripts/
│   └── vista_round_trip.py     # full-corpus validation gate
└── README.md                   # this file
```

## Roadmap

Step 1 (this doc) ships the **identity formatter** — the full parse → emit
round-trip with no canonical-layout rules yet. Subsequent passes layer in:

1. **Indentation normalisation** — `; comment` lines, dot-block indentation, label-column-1 enforcement.
2. **Whitespace canonicalisation** — no spaces around `_` (string concat), single-space after commas, etc., per the M style guide.
3. **Vertical spacing** — blank `;` lines between sections.
4. **`--check` integration with pre-commit** — hook scaffold + reference config.
5. **VistA-corpus performance ceiling tightening** — target sub-30s, then incremental improvements as rules are added.

Each rule is added with: a hand-crafted test, a VistA-corpus regression
gate (cleanly-parsing routines must still round-trip with the rule
*disabled*; with the rule enabled, only intentional changes appear), and
a brief design note.

## Licence

AGPL-3.0, matching the YottaDB and `tree-sitter-m` licence posture.
