# m lint — User Guide

The `m lint` command checks `.m` source for engine-neutral logic, style,
and modernization issues. Output goes to stdout in `text` (default),
`json`, or TAP format. Issues never block compilation — they're a
review tool, with a configurable threshold for which severity gates CI.

This guide is organized by what you need to look up:

1. [Quick start](#1-quick-start)
2. [Profiles](#2-profiles)
3. [Severity](#3-severity-and-the---error-on-gate)
4. [Categories](#4-categories)
5. [Configurable thresholds](#5-configurable-thresholds)
6. [Output formats](#6-output-formats)
7. [Inline disable directives](#7-inline-disable-directives)
8. [Project configuration (`.m-cli.toml`)](#8-project-configuration)
9. [CLI flags reference](#9-cli-flags-reference)
10. [Engine targeting](#10-engine-targeting)
11. [Auto-fix linkage with `m fmt`](#11-auto-fix-linkage-with-m-fmt)
12. [Worked example: VistA routine → Pythonic M](#12-worked-example-vista-routine--pythonic-m)


## 1. Quick start

```bash
m lint Routines/                          # default profile, text output
m lint --rules=xindex Routines/           # VistA-Toolkit-style rules
m lint --rules=pythonic Routines/         # Python-style strict review
m lint --error-on=warning Routines/       # exit 1 on WARNING or above
m lint --format=json Routines/            # CI-friendly output
m lint --jobs=8 Routines/                 # 8-process parallel scan
m lint --list-profiles                    # show available profiles
```

The default profile (`m lint` with no `--rules` flag) runs the
**curated daily-lint set**: 26 rules from the M-MOD-NN modernization
track, calibrated against a 4K-routine non-VA corpus to produce ~3
findings per routine.


## 2. Profiles

A profile is a named bundle of rule IDs. Run `m lint --list-profiles`
for the live list with descriptions; the table below summarizes.

| Profile | Rules | Use when |
|---------|------:|----------|
| `default` | 26 | Daily lint pass — opinionated modernization track minus the four loud pedantic rules. This is what runs when you don't pass `--rules`. |
| `modern` | 30 | Strict review pass — the full M-MOD-NN track, including the pedantic style rules. Expect heavy noise on legacy code. |
| `pedantic` | 4 | Just the four high-noise style rules: M-MOD-009 (commands-per-line), M-MOD-028 (label-docstring), M-MOD-031 (magic-numbers), M-MOD-032 (single-letter-vars). Use to focus a style sweep. |
| `pythonic` | 30 | Same selection as `modern` but bundles tighter thresholds (line=100, commands-per-line=1, cyclomatic=10, …) for projects coming from PEP-8 conventions. |
| `xindex` | 34 | Engine-neutral subset of VA's `^XINDEX` Toolkit. Mirrors XINDEX's numeric error codes 1:1. |
| `vista` | 8 | VA Kernel-specific rules (`OPEN→^%ZIS`, `HALT→^XUSCLEAN`, banner format). Pure false positives outside VistA — opt in only when linting VistA. |
| `sac` | 23 | Portable VA SAC rules (Standards & Conventions) minus the VistA-Kernel mandates. Gives non-VA shops VA-style discipline. |
| `all` | 72 | Every registered rule. Diagnostic-only — produces overlap. |

### How to combine

`--rules` accepts a comma-separated list mixing profiles and rule IDs:

```bash
m lint --rules=xindex,vista Routines/         # VA shops — full VistA flavour
m lint --rules=default,M-XINDX-013 Routines/  # daily set + one extra rule
m lint --rules=sac,modern Routines/           # union of both profiles
```


## 3. Severity and the `--error-on` gate

| Severity | Code | Meaning | LSP map |
|----------|:----:|---------|---------|
| `error` | E | Must fix; CI fails. Real bugs or undefined behavior. | Error |
| `warning` | W | Should fix. Likely-but-not-certain issues, complexity ceilings. | Warning |
| `style` | S | Auto-fix preferred. Hygiene, casing, formatting. | Hint |
| `info` | I | Informational, no action expected. | Information |

Distribution at the time of writing: **10 error**, **35 warning**,
**18 style**, **9 info** rules.

The `--error-on=LEVEL` flag picks the CI gate:

```bash
m lint --error-on=error Routines/    # only ERROR-severity issues fail CI (default)
m lint --error-on=warning Routines/  # WARNING+ also fails — stricter
m lint --error-on=style Routines/    # STYLE+ also fails — strictest
```

Per-rule severity overrides go in `[lint.severity]` — see
[§8](#8-project-configuration).


## 4. Categories

Category is **orthogonal to severity** — it describes *what kind* of
issue a rule catches, regardless of how strictly the project enforces
it. Filter by category to narrow attention.

| Category | Rules | What it covers |
|----------|------:|----------------|
| `bug` | 21 | Real defects: dead code, undefined references, control-flow holes |
| `style` | 13 | Casing, spacing, line length, naming conventions |
| `complexity` | 9 | Cyclomatic / cognitive complexity, nesting depth, argument counts |
| `concurrency` | 6 | LOCK, $ETRAP, OPEN/CLOSE pairing, transaction boundaries |
| `portability` | 8 | Engine-specific `Z*` / `$Z*` use without an allowlist |
| `documentation` | 6 | Missing comments, label docstrings, TODO ownership |
| `modernization` | 8 | Idioms that have a better post-1990 replacement |
| `security` | 1 | XECUTE/eval-like patterns on tainted data |


## 5. Configurable thresholds

Thresholds are integer knobs that drive several rules. Set them in
`[lint.thresholds]` (project config) or via `--threshold KEY=VAL`
(repeatable on the CLI). Unknown keys are rejected at config-load
time so typos don't silently no-op.

| Key | Default | Used by | Meaning |
|-----|--------:|---------|---------|
| `line_length` | 200 | M-MOD-001 | Max bytes per line (any kind) |
| `code_line_length` | 1000 | M-MOD-002 | Max bytes for non-comment lines |
| `routine_lines` | 1000 | M-MOD-003 | Max lines per `.m` file |
| `label_lines` | 50 | M-MOD-004 | Max lines per labeled subroutine |
| `cyclomatic` | 15 | M-MOD-005 | McCabe cyclomatic complexity per label |
| `cognitive` | 20 | M-MOD-006 | Cognitive complexity per label |
| `dot_block_depth` | 5 | M-MOD-007 | Max nested dot-block depth |
| `argument_count` | 7 | M-MOD-008 | Max formal arguments per label |
| `commands_per_line` | 3 | M-MOD-009 | Max commands per line |
| `comment_density_pct` | 10 | M-MOD-029 | Min comment-to-code ratio |

Resolution order: `default` → profile preset (e.g. `pythonic` bundles
tighter values) → `[lint.thresholds]` config → `--threshold KEY=VAL`
CLI. CLI always wins. **Line length is measured in bytes**, which
equals characters for ASCII source (which all real M code is).


## 6. Output formats

| Format | When |
|--------|------|
| `text` (default) | Interactive use; one diagnostic per line with file:line:col, severity, rule ID, message |
| `json` | CI / downstream tooling. Stable schema; carries `fixer_id` when a `m fmt` rule auto-fixes the diagnostic |
| `tap` | Test-runner pipelines that already consume TAP v13 |

```bash
m lint --format=json Routines/ | jq '.diagnostics[] | select(.severity=="error")'
```


## 7. Inline disable directives

Suppress findings without editing config — comment-driven, line-scoped:

```m
SOMELABEL ; m-lint: disable=M-MOD-031     ;; suppress on the next code line
 SET PRICE=1995
 ; m-lint: disable=M-MOD-009              ;; suppress same-line of next line
 SET A=1 SET B=2 SET C=3
 SET X=1 ; m-lint: disable=M-MOD-031      ;; suppress on this same line
 ; m-lint: file-disable=M-MOD-028          ;; suppress for entire file
 ; m-lint: disable=*                       ;; suppress every rule (next line)
```

Forms:
- **`; m-lint: disable=RULE`** — next line only
- **`SET X=1 ; m-lint: disable=RULE`** — same line (inline trailing comment)
- **`; m-lint: file-disable=RULE`** — whole file
- **`disable=*`** — every rule (any of the three scopes above)
- **`disable=RULE1,RULE2`** — multiple rules at once

Hover-on-diagnostic in the LSP shows the rule ID + title so you can
copy it directly into the directive.


## 8. Project configuration

`m lint` walks up from the working directory looking for `.m-cli.toml`
first, then a `pyproject.toml` containing `[tool.m-cli]`. The walk
stops at a `.git` boundary so configs in unrelated parents don't leak
in.

```toml
# .m-cli.toml at the project root

[lint]
rules = "default"                  # profile name, comma list, or rule IDs
disable = ["M-XINDX-013"]          # rules to skip after selection
target_engine = "yottadb"          # "yottadb" | "iris" | "any" (default any)

[lint.severity]
"M-XINDX-019" = "warning"          # remap any rule's severity
"M-MOD-031" = "info"               # demote to non-actionable
                                   # values: "fatal" | "standard" | "warning" | "info"

[lint.thresholds]
line_length = 100                  # PEP-8-flavoured
commands_per_line = 1
cyclomatic = 10
```

Equivalent with `pyproject.toml`:

```toml
[tool.m-cli.lint]
rules = "default"
```

Resolution order for every setting: built-in default → profile preset
→ config file → CLI flag (CLI wins).


## 9. CLI flags reference

| Flag | Default | Meaning |
|------|---------|---------|
| `--rules SPEC` | `default` (or config) | Profile name, rule ID, or comma list mixing both |
| `--format text\|json\|tap` | `text` | Output dialect |
| `--error-on LEVEL` | `error` | CI gate threshold |
| `--threshold KEY=VAL` | — | Override a threshold; repeatable |
| `--target-engine yottadb\|iris\|any` | `any` | Engine context for engine-aware rules |
| `--jobs N` | `os.cpu_count()` | Parallel worker processes |
| `--disable RULE` | — | Disable a rule (in addition to config) |
| `--list-profiles` | — | Print profiles and exit |
| `-q / --quiet` | off | Suppress per-file progress |


## 10. Engine targeting

Several rules behave differently depending on which M engine the code
will run on. Setting `target_engine` unlocks engine-aware allowlists:

- **`yottadb`** — `$Z*` ISVs and Z-functions documented by YottaDB pass; everything else flags as portability concerns
- **`iris`** — ditto for InterSystems IRIS / Caché
- **`any`** (default) — no engine-specific allowlist; M-MOD-021..023 use the ANSI subset only

Source of truth for the allowlists is m-standard's TSV `standard_status`
column: `ansi`, `ydb`, `iris`, `ydb-and-iris`, `vista`. The 8
`portability`-category rules (M-MOD-021..023 and friends) consume this.


## 11. Auto-fix linkage with `m fmt`

Some lint rules carry a `fixer_id` pointing to an `m fmt` rule that
deterministically fixes the diagnostic. Today's pairings:

| Rule | Severity | Auto-fix |
|------|:--------:|----------|
| `M-XINDX-013` | style | `m fmt --rules=trim-trailing-whitespace` |
| `M-XINDX-047` | style | `m fmt --rules=uppercase-command-keywords` |

The link surfaces in JSON output (`"fixer_id": "..."` per diagnostic)
and via `m_cli.lint.fixer_for(rule_id)` for tooling. The LSP wrapper
uses this to expose Quick Fix code actions — clicking a Hint-level
diagnostic in VS Code runs the fmt rule file-wide.


## 12. Worked example: VistA routine → Pythonic M

The companion to `m lint` for modernization is `m fmt --rules=pythonic`
(or `--rules=pythonic-lower`), which mechanically translates between
the dense VistA-compact form and the more readable canonical-name form
without changing the parsed AST. M is case-insensitive on commands,
intrinsic functions, and special variables, so the translated routine
runs identically on YottaDB or IRIS.

### Source: a 40-line VistA-style routine

This is a synthetic but idiomatic example covering the constructs that
appear in real VistA: comments, labels with formals, dot-blocks, FOR
loops, KILL/NEW, intrinsics (`$L`, `$E`, `$O`, `$D`, `$G`, `$T`),
special variables (`$J`), and global / routine references.

```m
INVENTRY ; INVENTORY MANAGEMENT — DAILY ROLLUP ; v1.2
 ;;1.2;DEMO;;Apr 30, 2026
 ;
 ; Walks the line-item global, totals quantities by SKU, and writes
 ; a flat report to ^TMP for downstream consumption.
 ;
RUN(SITE,DATE) ; [Procedure] entry point — site = facility id, date = FileMan day
 N SKU,QTY,TOT,LINE,LCNT
 K ^TMP("INVRPT",$J) S LCNT=0
 S SKU=""
 F  S SKU=$O(^INV("S",SITE,SKU)) Q:SKU=""  D
 . S TOT=0,LINE=""
 . F  S LINE=$O(^INV("S",SITE,SKU,LINE)) Q:'LINE  D
 .. S QTY=$P($G(^INV("S",SITE,SKU,LINE)),"^",2)
 .. S:QTY>0 TOT=TOT+QTY
 . S LCNT=LCNT+1
 . S ^TMP("INVRPT",$J,LCNT)=SKU_"^"_TOT
 Q
 ;
SHOW ; [Procedure] dump the rollup to the current device
 N I,LN
 S I=0
 F  S I=$O(^TMP("INVRPT",$J,I)) Q:'I  D
 . S LN=^TMP("INVRPT",$J,I)
 . W !,$E($P(LN,"^"),1,12),?14,$P(LN,"^",2)
 W !!,"Done.",!
 Q
 ;
CLEAR ; [Procedure] reset the work area for re-runs
 K ^TMP("INVRPT",$J)
 Q
 ;
TEST ; [Procedure] smoke check — was the global populated?
 I '$D(^INV("S")) W !,"No inventory data for any site.",! Q
 W !,"Sites configured: ",$L($G(^INV(0)),"^")
 Q
 ;
EXIT K SKU,QTY,TOT,LINE,LCNT,I,LN
 Q
```

### Translated: `m fmt --rules=pythonic`

```m
INVENTRY ; INVENTORY MANAGEMENT — DAILY ROLLUP ; v1.2
 ;;1.2;DEMO;;Apr 30, 2026
 ;
 ; Walks the line-item global, totals quantities by SKU, and writes
 ; a flat report to ^TMP for downstream consumption.
 ;
RUN(SITE,DATE) ; [Procedure] entry point — site = facility id, date = FileMan day
 NEW SKU,QTY,TOT,LINE,LCNT
 KILL ^TMP("INVRPT",$JOB) SET LCNT=0
 SET SKU=""
 FOR  SET SKU=$ORDER(^INV("S",SITE,SKU)) QUIT:SKU=""  DO
 . SET TOT=0,LINE=""
 . FOR  SET LINE=$ORDER(^INV("S",SITE,SKU,LINE)) QUIT:'LINE  DO
 .. SET QTY=$PIECE($GET(^INV("S",SITE,SKU,LINE)),"^",2)
 .. SET:QTY>0 TOT=TOT+QTY
 . SET LCNT=LCNT+1
 . SET ^TMP("INVRPT",$JOB,LCNT)=SKU_"^"_TOT
 QUIT
 ;
SHOW ; [Procedure] dump the rollup to the current device
 NEW I,LN
 SET I=0
 FOR  SET I=$ORDER(^TMP("INVRPT",$JOB,I)) QUIT:'I  DO
 . SET LN=^TMP("INVRPT",$JOB,I)
 . WRITE !,$EXTRACT($PIECE(LN,"^"),1,12),?14,$PIECE(LN,"^",2)
 WRITE !!,"Done.",!
 QUIT
 ;
CLEAR ; [Procedure] reset the work area for re-runs
 KILL ^TMP("INVRPT",$JOB)
 QUIT
 ;
TEST ; [Procedure] smoke check — was the global populated?
 IF '$DATA(^INV("S")) WRITE !,"No inventory data for any site.",! QUIT
 WRITE !,"Sites configured: ",$LENGTH($GET(^INV(0)),"^")
 QUIT
 ;
EXIT KILL SKU,QTY,TOT,LINE,LCNT,I,LN
 QUIT
```

### Translated: `m fmt --rules=pythonic-lower`

PEP-8-flavoured variant that keeps user-defined names uppercase but
lowers all keywords, intrinsics, and special variables:

```m
INVENTRY ; INVENTORY MANAGEMENT — DAILY ROLLUP ; v1.2
 ;;1.2;DEMO;;Apr 30, 2026
 ;
 ; Walks the line-item global, totals quantities by SKU, and writes
 ; a flat report to ^TMP for downstream consumption.
 ;
RUN(SITE,DATE) ; [Procedure] entry point — site = facility id, date = FileMan day
 new SKU,QTY,TOT,LINE,LCNT
 kill ^TMP("INVRPT",$job) set LCNT=0
 set SKU=""
 for  set SKU=$order(^INV("S",SITE,SKU)) quit:SKU=""  do
 . set TOT=0,LINE=""
 . for  set LINE=$order(^INV("S",SITE,SKU,LINE)) quit:'LINE  do
 .. set QTY=$piece($get(^INV("S",SITE,SKU,LINE)),"^",2)
 .. set:QTY>0 TOT=TOT+QTY
 . set LCNT=LCNT+1
 . set ^TMP("INVRPT",$job,LCNT)=SKU_"^"_TOT
 quit
 ;
…
```

### What changed, what didn't

- **Changed:** every command keyword (`N→NEW`, `S→SET`, `K→KILL`,
  `F→FOR`, `Q→QUIT`, `W→WRITE`, `I→IF`, `D→DO`), every intrinsic
  function (`$O→$ORDER`, `$P→$PIECE`, `$G→$GET`, `$L→$LENGTH`,
  `$E→$EXTRACT`, `$D→$DATA`), and the special variable `$J→$JOB`.
- **Untouched:** comments (`; INVENTORY MANAGEMENT — DAILY ROLLUP`),
  string literals (`"INVRPT"`, `"^"`, `"No inventory data..."`),
  variable names (`SITE`, `DATE`, `SKU`, `QTY`, `TOT`), labels (`RUN`,
  `SHOW`, `CLEAR`, `TEST`, `EXIT`), routine references (`^TMP`,
  `^INV`), and dot-block indentation.
- **Idempotent:** running `--rules=pythonic` twice yields the same
  bytes the second time. Mixed-form input (some `NEW`, some `N`)
  collapses to all-canonical, by design.
- **Round-trip:** `m fmt --rules=compact` recovers the original
  compact form from a pythonic file. The only delta on real code is
  that *trailing whitespace* gets normalized along the way (since
  `trim-trailing-whitespace` rides along in both presets) — the
  compact source stays unchanged in everything that matters.

### What the linter finds in this routine

For completeness — the same routine under the default lint profile:

```
$ m lint inventry.m
m lint: 1 file(s) checked, 26 rule(s) active (--rules=default), 2 finding(s): 0E 0W 0S 2I
inventry.m:7:1: [I] M-MOD-029: Label 'RUN' comment density 8% below threshold 10% (1/12 non-blank lines)
inventry.m:16:6: [I] M-MOD-034: `SET LCNT=LCNT+1` — prefer `SET LCNT=$INCREMENT(LCNT)`
```

Two informational findings — a comment-density nudge on `RUN` and a
modernization suggestion (`$INCREMENT` is atomic; the read-modify-write
pattern isn't, which matters under `LOCK` contention). Neither blocks
CI at the default `--error-on=error` gate.

### Verifying functional identity

The translation rules preserve AST shape by construction (only the
text inside `command_keyword` / `intrinsic_function_keyword` /
`special_variable_keyword` nodes changes), and M is case-insensitive on
all three. To paranoid-verify on your own routine:

```bash
# Translate to a copy without touching the original
m fmt --rules=pythonic --stdout routine.m > routine.pythonic.m

# Both should compile and run identically under YottaDB or IRIS
ydb -run ENTRY^routine
ydb -run ENTRY^routine.pythonic
```

`tests/test_fmt_rules.py::TestExpandCommandKeywords::test_preserves_ast_shape`
pins the AST-shape contract on the rule level for every translation
rule shipped.


## See also

- [`docs/guide.md`](guide.md) — the complete `m-cli` user guide (lint, fmt, test, watch, coverage, LSP)
- [`docs/plans/m-linting-survey.md`](plans/m-linting-survey.md) — the survey behind the M-MOD-NN rule design
- [`docs/plans/m-linting-implementation-plan.md`](plans/m-linting-implementation-plan.md) — phasing roadmap
- [`docs/pre-commit.md`](pre-commit.md) — wiring `m lint` into pre-commit hooks
