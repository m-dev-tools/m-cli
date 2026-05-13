# m-cli Output Remediation — Plan 0 (2026-05-13)

This plan responds to the findings of two as-is audits captured on the
same day:

- [`cli-output-audit-2026-05-13.md`](cli-output-audit-2026-05-13.md) —
  every subcommand, every `--format`, every error path.
- [`audit-m-engine-2026-05-13.md`](audit-m-engine-2026-05-13.md) — every
  verb of `m engine` and every option, across container state transitions.

Both audits catalogue ~30 distinct UX inconsistencies. This document
proposes that **all of them trace to a single root cause** and lays out
a phased remediation that addresses the cause, not the symptoms.

This is "plan 0" — a first-pass proposal. Reviewing it should produce
edits, sequencing changes, and out-of-scope calls; the deliverable is
agreement on the cause and the phasing, not pixel-perfect specs.

---

## 0. Premise — what's already settled

This plan **builds on**, doesn't replace, two existing documents:

- [`docs/cli-frameworks/cli-ux-conventions-guide.md`](cli-frameworks/cli-ux-conventions-guide.md)
  — dispatcher-layer conventions: bare invocation, `--help`/`-h`
  aliasing, stdout vs stderr destination, exit-code vocabulary, the
  `print_overview` pattern.
- [`docs/cli-frameworks/cli-ux-plan.md`](cli-frameworks/cli-ux-plan.md)
  — the previous round of P0/P1/P2 fixes that landed `print_overview`
  itself, the `m ci init` preview-by-default behaviour, and the cwd
  defaults for `m fmt` / `m lint`.

That work fixed the dispatcher layer. **The audits document what the
dispatcher layer's conventions never reached**: per-verb output
formatting, summary-line discipline, severity vocabulary, capabilities
recursion, error-prefix derivation, manifest drift. Plan 0 is the
output-layer companion to the dispatcher-layer guide.

---

## 1. The single root cause

> **m-cli has dispatcher-level UX conventions but no output-layer or
> registry-level conventions. Every subcommand author writes their own
> `print()` calls, their own help body, their own exit codes, their own
> error prefixes. There is no shared infrastructure for rendering, no
> single declarative spec that all surfaces consume, and no policy gate
> that catches drift.**

This explains all 8 problem categories the audits surfaced. The CLI
grew bottom-up: when `m fmt` shipped, its author chose `m fmt:` as a
summary prefix and stdout as the destination. When `m lint` shipped,
its author chose stderr (with no `\n`). When `m test` shipped, its
author chose stderr regardless of `--format`. When `m engine status`
shipped, its author chose ✓/✗/- glyphs. When `m doctor` shipped, its
author chose `OK / WARN / FAIL`. Every one of these decisions was
locally reasonable and individually testable. None of them shared
infrastructure with any other.

The result, after twelve subcommands and eleven engine verbs, is a
surface that is internally consistent inside each verb and
cross-verb-inconsistent everywhere else.

---

## 2. The eight problem categories

Each category collapses ~3-6 audit findings to one underlying gap. The
mapping back to specific audit findings is in
[Appendix A](#appendix-a--audit-finding--phase-mapping).

### C1 — No shared output primitives
Every verb prints by hand. Glyphs (`✓` / `✗` / `-` / `—` / `⚠`),
summary-line prefixes (`m fmt:` / `m lint:` / `m doc:` / `refusing:`),
table rendering (status / version / coverage / lint-list-profiles all
roll their own), and "missing value" idioms (`-`, `—`, `(none)`,
`null`) are duplicated across files with subtle drift.

### C2 — stdout / stderr discipline is improvised per verb
`m lint` summary on stderr **without a leading newline** → joins last
finding line. `m test --format=json` writes a non-JSON summary to
stderr above the JSON. `m coverage` summary on stderr. `m fmt` summary
on stdout. `m watch` header on stdout. There is no policy on where a
summary line goes when stdout is structured (JSON/TAP/JUnit/LCOV)
versus when it's prose.

### C3 — Severity / status vocabulary is bifurcated
Two parallel schemes:
- `OK / WARN / FAIL / skipped` (used by `m doctor` only).
- `[E] / [W] / [S] / [I]` (used by `m lint` text; in JSON it becomes
  `"severity": "warning"` etc.).

`m engine status` uses neither; it uses `✓ / ✗ / -` directly on
key-value rows. `m doctor` and `m engine status` describe overlapping
state in two unrelated dialects.

### C4 — Capabilities manifest doesn't descend
`m capabilities` walks one argparse layer. Sub-actioned dispatchers
(`ci`, `engine`, `stdlib`) report `options: []` — no consumer can see
`m engine status`'s `--json` flag, `m stdlib doc`'s `--short`, etc. The
engine namespace ships its own second manifest (`m engine
capabilities`) to compensate; the others have no equivalent.

### C5 — Help-body completeness is uneven
Per the engine audit: of 11 engine verbs, **one** (`reset`) carries a
description paragraph, **one** (`exec`) carries an inline example,
**zero** document their exit codes (`m engine status`'s 0/1 split is
invisible). At the top level: every `capabilities` entry has
`examples: []`. The pattern repeats elsewhere — `m fmt --check` returns
exit 0 on a missing file; nothing in `--help` mentions it.

### C6 — Three sources of truth for the engine verb set
`dist/m-test-engine.json` advertises 13 verbs (`upgrade`, `watch`
extras); `engine_cli.py` wires 11; `_cmd_capabilities` reports 11. No
test asserts the three agree. The drift is silent.

### C7 — Error-prefix strings are hardcoded, not derived
`m stdlib doc UNKNOWN` errors as `m doc: …` — a vestige of when the
verb was top-level. `m stdlib search 'x'` errors as `m search: …`.
`m engine reset` errors as `refusing: …` with no command-path prefix at
all. There is no rule that an error's prefix should match the
invocation path; each handler hardcodes its own.

### C8 — Top-level rendering has two competing styles
The dispatcher-layer guide settled the `print_overview` pattern, and
the audit confirms it's in use everywhere (`m`, `m ci`, `m engine`,
`m stdlib`). But:
- `m --help` still falls through to argparse's default formatter.
- Bare `m engine` prints the description **and** the tagline, which
  for this namespace say nearly the same thing (other dispatchers use
  the two strings to carry different information).
- Unknown-command paths emerge from argparse with its own style
  (`m: error: argument <command>: invalid choice: …`).

Three styles, one CLI.

---

## 3. Remediation principles

1. **One declarative spec per subcommand drives every surface.** Help,
   capabilities, exit codes, output destination, examples. argparse,
   capabilities walker, and contract tests all read from the same
   spec.
2. **Output is a layer, not a habit.** Glyphs, summary lines, tables,
   error prefixes live in one module. Every verb calls into it. No
   bare `print()` for user-visible output in subcommand code.
3. **Drift is caught at test time.** Three-way agreement (argparse
   registry ↔ manifest ↔ capabilities payload) is a contract test, not
   a code-review checklist.
4. **Policy beats taste.** Where two reasonable choices exist (`OK` vs
   `[E]`, stderr vs stdout for summaries), pick one in writing, in the
   guide, then refactor everything to it. No second vocabulary.
5. **No big rewrite.** Phases are small, independently shippable, and
   ordered by "consistency dividend per line changed."

---

## 4. Phased plan

Each phase ships independently, leaves the CLI in a consistent state,
and is gated by tests that pin the new contract.

### P0 — Pin the current contract (no behaviour change)

Before refactoring anything, write contract tests that lock down
today's behaviour. This is the regression net for all later phases.

| Deliverable | What it pins |
| --- | --- |
| `tests/test_cli_contract_destinations.py` | Per-format output destination (e.g. `m test --format=json` body → stdout, summary → stderr). One assertion per `(verb, --format)` pair. |
| `tests/test_cli_contract_exit_codes.py`   | Per-scenario exit codes (success, drift, refusal, missing-arg, unknown-action, container-not-running). One assertion per scenario the audits enumerate. |
| `tests/test_cli_contract_help_shape.py`   | Per-verb `--help` shape: presence of description, examples, options table. Snapshot-style assertions. |

These tests **codify the bugs as well as the good behaviour** —
deliberately. Each later phase changes the tests *and* the
implementation in the same PR, so the net is never green-but-wrong.

Effort: small (~1 day). Mostly mechanical capture.

### P1 — Introduce `m_cli.display` (the output layer)

A small module with pure functions. No global state. Every subcommand
gradually migrates to it; the migration is the entire UX-consistency
win for phases 2-5.

```python
# m_cli/display.py
from enum import Enum

class Glyph:                # the single glyph vocabulary
    OK      = "✓"
    FAIL    = "✗"
    UNKNOWN = "-"
    WARN    = "⚠"
    ABSENT  = "—"           # em-dash — for "no data" in tables
    NONE    = "(none)"      # text literal — for "no declared counterpart"

class Severity(Enum):       # the single severity vocabulary
    ERROR    = ("E", "error",    "FAIL")
    WARNING  = ("W", "warning",  "WARN")
    STYLE    = ("S", "style",    "OK")
    INFO     = ("I", "info",     "OK")

def summary(prefix: str, body: str, *, stream=sys.stderr) -> None:
    """Always trailing newline. Always one canonical prefix derivation."""

def kv_row(label: str, value: str | bool | None, *, indent=0) -> str:
    """Status-style row: '  label:  value' or with a glyph."""

def table(rows, headers, *, glyph_col=False) -> str:
    """Version-style table with consistent column widths."""

def error_prefix(*invocation_path: str) -> str:
    """`m stdlib doc` → 'm stdlib doc' (not 'm doc')."""

def cmd_error(invocation_path, msg, *, exit_code=1) -> NoReturn:
    """Standard error path: prefix + newline + sys.exit."""
```

First three migration targets, ordered by audit-finding density:

1. `m lint` text output → fixes C2's `\n` bug, fixes C3's `[E]` vs
   `error` mismatch, normalises the `m lint:` summary line.
2. `m engine status` + `m doctor` → unify glyphs and severity vocab
   (C3); single rendering path for "is the engine up?"
3. `m test` / `m watch` summary lines → resolve the JSON/JUnit
   contamination (C2).

Effort: medium (~3-5 days). The hard part is taste — picking the
single vocabulary. The code is small and self-contained.

### P2 — Recursive capabilities + drift gates

Walk argparse subparsers recursively in `m capabilities` so
`ci`/`engine`/`stdlib` sub-actions surface. Result:

```json
"engine": {
  "purpose": "Manage the m-test-engine container (install/start/stop/...)",
  "options": [],
  "actions": {
    "status":  { "purpose": "...", "options": [{"name": "--json", ...}] },
    "install": { "purpose": "...", "options": [] },
    ...
  }
}
```

Then `m engine capabilities` (the namespace's own JSON dump) is
**generated from the walker**, not hand-maintained. Removes one of the
three sources of truth in C6.

Add a contract test `tests/test_engine_manifest_drift.py` that
asserts:

```
set(argparse subparsers under 'engine') ==
  set(verbs in dist/m-test-engine.json) ==
  set(verbs in m engine capabilities payload)
```

Today this test would **fail** — caught by the audit
(`upgrade`/`watch` in manifest only). The PR that lands the test
either: (a) wires the missing verbs, or (b) removes them from the
manifest. Either fix kills C6 permanently.

Effort: small (~1-2 days). Mostly code consolidation.

### P3 — Help-body completeness

A single linter test that asserts, for every leaf subparser:

- `description=` non-empty.
- `epilog=` non-empty with at least one example invocation.
- If the verb has a non-trivial exit-code semantic (today: `m engine
  status`, `m fmt --check`, `m lint --error-on`), exit codes are
  documented in `epilog`.

Effort: small for the test (~half a day). Effort to **make the test
green** is medium — writing 30+ short paragraphs and examples. But
it's parallelizable, and once the test exists the corpus only grows.

Once `epilog` is universal, the `examples: []` gap in capabilities
(C4) closes mechanically — `m capabilities` already plumbs examples
from `epilog`.

### P4 — Output-format policy, written down and enforced

Add `docs/cli-frameworks/cli-output-policy.md` (sibling of the
conventions guide) codifying:

| Rule | Applies to |
| --- | --- |
| Structured output (`--format=json/tap/junit/lcov`) → **stdout, nothing else**. | `m lint`, `m test`, `m coverage`, `m watch`, `m doctor`, `m fmt --list-rules`, `m lint --list-rules`, `m plugins`, `m capabilities`, `m engine status/version/capabilities` |
| Text output → summary on **stderr**, body on **stdout**. | Same list, text mode |
| `-q / --quiet` suppresses the summary line. Body is unaffected. | All of the above |
| Missing-value glyph is `Glyph.ABSENT` in tables, `null` in JSON. No `-`/`—`/`(none)` drift. | `m engine status`, `m engine version`, `m doctor` |
| Exit codes follow §3.7 of the conventions guide; domain-specific extensions (`m engine status`'s 1-when-stopped) are documented per-verb in `epilog`. | All verbs |

P0's destination test (`test_cli_contract_destinations.py`) becomes
the enforcement gate. Today many of its assertions encode the *current*
mis-routing; the P4 PR flips them to the *correct* routing in the same
commit that lands the fix.

Effort: medium (~3 days). The policy doc is short; the migration to
satisfy it is mostly mechanical given P1's `display.summary` helper.

### P5 — Subcommand registry (the long-term arc)

The audits' deep finding is that **argparse alone is not enough
structure**. argparse is fine for parsing; it's a weak source-of-truth
for help, capabilities, examples, exit codes, and tests. Today these
all live in side channels (hand-curated dicts in `_cmd_capabilities`,
free-form description strings, scattered exit-code conventions).

Long-term, a small registry alongside argparse:

```python
@subcommand(
    name="status",
    parent="engine",
    purpose="...",
    examples=["m engine status", "m engine status --json"],
    exit_codes={0: "container running", 1: "container not running"},
    format_choices=["text", "json"],
)
def _cmd_status(args): ...
```

argparse is generated from the registry; capabilities is generated
from the registry; contract tests read from the registry; the help
body is generated from the registry. One source of truth, every
surface a derived view.

This is a phase 5 because by then phases 1-4 have already paid down
most of the visible inconsistency, and the registry's value is mostly
"prevent future drift" — a lower-urgency win.

Effort: large (~1-2 weeks if scoped to the existing surface).
Optional; ship only if phases 1-4 leave any meaningful drift behind.

---

## 5. Phasing and dependency graph

```
P0 (contract tests, no behavior change)
   ↓
P1 (display module + 3 pilot migrations)
   ↓
   ├── P2 (capabilities recursion + drift gates)
   ├── P3 (help-body completeness)
   └── P4 (output-format policy + remaining migrations)
                 ↓
                 P5 (registry, optional)
```

P0 is mandatory and ships first. P1 is mandatory and ships before
P2-P4 (which assume `display`). P2 / P3 / P4 are independent of each
other and can ship in any order or in parallel. P5 is optional.

Suggested PR order if shipping one phase per week:

1. **Week 1** — P0 (contract tests, today's behaviour pinned).
2. **Week 2** — P1 (display module + lint/engine-status/test migrated).
3. **Week 3** — P4 (output-format policy doc + remaining migrations).
4. **Week 4** — P2 (capabilities recursion + engine drift gate).
5. **Week 5** — P3 (help-body completeness).
6. **Later** — P5 if drift returns.

---

## 6. What this plan does **not** do

- **Does not rewrite argparse.** Every existing verb keeps its
  argparse parser. Only the output and capabilities surfaces change.
- **Does not introduce new dependencies** (no `rich` / `click` /
  `typer`). The `display` module is pure stdlib `print()` /
  `sys.stderr` / fixed-width formatting.
- **Does not break public APIs.** `m_cli.parse`, `format_source`,
  `lint_source`, `select_rules`, etc., are unchanged. The library
  consumers from `__all__` see no diff.
- **Does not change exit-code semantics for any verb** unless P4
  explicitly says so (and only with the manual / `--help` updated in
  the same PR).
- **Does not touch `m run`'s YDB passthrough.** `%YDB-E-*` errors stay
  raw — they're authored by YottaDB and m-cli doesn't own them.
- **Does not touch `m lsp` stdio output.** LSP messages are protocol,
  not user UX.
- **Does not pre-design the registry (P5).** That phase exists only as
  a placeholder; design it then if it's still needed.

---

## 7. Verification

Every phase ships with:

1. **Contract tests** updated in the same PR that changes behaviour.
   Tests should never be green-and-wrong; flip the assertion in the
   commit that lands the fix.
2. **A docs update** in the relevant guide:
   - P1 → `cli-output-policy.md` (new sibling of the conventions
     guide); the `display` module gets a one-page reference.
   - P2 → `cli-ux-conventions-guide.md` §5.4 (capabilities walker).
   - P3 → `cli-ux-conventions-guide.md` §3.3 (help body must include
     description + epilog example).
   - P4 → `cli-output-policy.md`.
3. **A re-run of the two audits**. After each phase, regenerate
   `cli-output-audit-<date>.md` and `audit-m-engine-<date>.md` and
   diff against the 2026-05-13 snapshot. Findings should monotonically
   decrease. The diff is the PR's evidence of progress.

---

## Appendix A — audit-finding → phase mapping

The numbered headings reference the cross-cutting observations in the
two audit documents. "Audit ref" cites the audit file's section
identifier.

| Audit finding | Audit ref | Category | Resolved by |
| --- | --- | --- | --- |
| Two competing top-level layouts (`m` vs `m --help` vs `m engine` no-action) | cli-output §1 | C8 | Existing UX work (already landed); P3 closes residual gaps |
| `m engine` description printed twice | engine §"Top-level m engine" | C8 | P1 (`print_overview` becomes single-source; tagline becomes optional) |
| Summary lines on different streams across verbs | cli-output §2 | C2 | P4 (codified policy) + P1 (`display.summary`) |
| `m lint` summary on stderr without `\n` (joins findings) | lint §"Observations" | C2 | P0 (pinned), P1 (`display.summary` always writes `\n`) |
| `m test --format=json` writes text summary to stderr above JSON | test §"Observations" | C2 | P4 + P1 |
| `m fmt --check non-existent.m` exits 0 | fmt §"Observations" | C5 | P0 (pin), P4 (policy: missing-input = exit 2 or domain choice) |
| Verb-prefix drift (`m doc:` not `m stdlib doc:`) | stdlib §"Observations" | C7 | P1 (`error_prefix(*path)` derives from dispatch) |
| `refusing:` prefix on `m engine reset` not matching other styles | engine §"reset" | C7 | P1 |
| JSON/text parity uneven (status, doctor, version) | cli-output §4 | C1, C3 | P1 (kv_row + table) + P4 |
| Manifest reports `options: []` for ci/engine/stdlib | cli-output §5 | C4 | P2 (recursive walker) |
| `examples: []` for every command | cli-output §5 | C5 | P3 (epilog gate) |
| Unicode HTML-escapes in capabilities JSON | cli-output §"capabilities" | C1 | P1 (single `json.dumps(..., ensure_ascii=False)` helper) |
| Two severity vocabularies (`OK/WARN/FAIL` vs `[E]/[W]/[S]/[I]`) | cli-output §6 | C3 | P1 (`Severity` enum, single mapping) |
| Three "missing value" glyphs in engine version (`-`, `—`, `(none)`) | engine §version | C1 | P1 (`Glyph` constants) |
| `m engine status` exit code (0 running / 1 not running) undocumented | engine §status | C5 | P3 (epilog) + P0 (pin) |
| Engine verb-set drift: manifest (13) vs argparse (11) vs capabilities (11) | engine §"Cross-cutting §1" | C6 | P2 (drift gate test) |
| Engine `--help` shapes vary across 11 verbs | engine §"Cross-cutting §2" | C5 | P3 (description + epilog gate) |
| Five output-source categories mixed in 11 engine verbs | engine §"Cross-cutting §3" | C1 | P1 (synthesize where today's behaviour is docker passthrough) |
| `m engine status` "healthy: -" collapses two states | engine §status | C3 | P1 (`Glyph.UNKNOWN` vs explicit `starting` / `none`) |
| Lint `--list-profiles` lines run 600+ chars unwrapped | lint §"Observations" | C1 | P1 (table renderer with wrap) |
| Coverage's no-routines string identical in text/JSON/lcov | coverage §"Observations" | C2 | P4 (per-format failure shapes) |
| `m test` label-not-found `available:` line unwrapped | test §FILE::tLabel | C1 | P1 (list-renderer) |
| `m stdlib` seven verbs, seven layouts | stdlib §"Observations" | C1 | P1 (table / list helpers) |
| `m doctor` tally line plural mismatch (`OK / warning / fail / skipped`) | doctor §"Observations" | C1 | P1 (single tally formatter) |

Every finding in the audits is covered by at least one phase. C1-C8
collapse 30 findings into 8 design defects; P0-P5 collapse 8 design
defects into 6 work packages.

---

## Appendix B — sample `display` module API (illustrative, not normative)

```python
# m_cli/display.py — proposed P1 surface.
# Pure stdlib. No deps. No global state.

import json
import sys
from enum import Enum
from typing import Any, NoReturn, TextIO


class Glyph:
    OK      = "✓"
    FAIL    = "✗"
    UNKNOWN = "-"
    WARN    = "⚠"
    ABSENT  = "—"
    NONE    = "(none)"


class Severity(Enum):
    ERROR   = ("E", "error",   Glyph.FAIL)
    WARNING = ("W", "warning", Glyph.WARN)
    STYLE   = ("S", "style",   Glyph.OK)
    INFO    = ("I", "info",    Glyph.OK)

    @property
    def letter(self) -> str: return self.value[0]
    @property
    def word(self) -> str:   return self.value[1]
    @property
    def glyph(self) -> str:  return self.value[2]


def summary(path: tuple[str, ...], body: str, *, stream: TextIO = sys.stderr) -> None:
    """Canonical summary line. Always `\\n`. Always `m <path>: body`."""
    prefix = " ".join(("m",) + path)
    stream.write(f"{prefix}: {body}\n")


def error_exit(path: tuple[str, ...], body: str, *, code: int = 1) -> NoReturn:
    """Canonical error path. Stderr, single newline, single exit."""
    summary(path, body, stream=sys.stderr)
    sys.exit(code)


def kv(label: str, value: Any, *, indent: int = 0, label_width: int = 16) -> str:
    """Status-style key-value row."""
    pad = " " * indent
    return f"{pad}{label + ':':<{label_width}}  {value}"


def tristate_glyph(b: bool | None) -> str:
    """True → ✓, False → ✗, None → -. The single source of truth."""
    return {True: Glyph.OK, False: Glyph.FAIL, None: Glyph.UNKNOWN}[b]


def dump_json(payload: Any, *, stream: TextIO = sys.stdout) -> None:
    """Canonical JSON dump: indent=2, ensure_ascii=False, trailing newline."""
    stream.write(json.dumps(payload, indent=2, ensure_ascii=False))
    stream.write("\n")


__all__ = [
    "Glyph", "Severity",
    "summary", "error_exit",
    "kv", "tristate_glyph", "dump_json",
]
```

This is illustrative — the final shape gets settled in the P1 PR. The
point is that it's small (~50 lines) and replaces ~30 distinct ad-hoc
print sites across the codebase.
