# M Linting Implementation Plan

**Status:** working plan, derived from [`docs/m-linting-survey.md`](m-linting-survey.md) §7 (greenfield rule list) and §8 (roadmap), informed by [`docs/m-corpus-catalog.md`](m-corpus-catalog.md) for the regression gate.

**Audience:** m-cli contributors picking up the next phase of work; reviewers tracking what shipped.

**Scope:** the M-MOD-NN modernization track, the `vista` profile split, modernized thresholds, engine-aware allowlists, and the data-flow / taint research projects identified in the survey. **Not in scope:** the 42 existing XINDEX-derived rules (already shipped) and the formatter / test runner / coverage / LSP work tracked elsewhere.

---

## 0. Current state (already shipped)

The foundational architecture is in place. Anything below builds on it; nothing in this plan revisits it.

| Item | Where | Status |
|---|---|---|
| Profile registry (`default`, `xindex`, `vista`, `sac`, `modern`, `all`) | [`src/m_cli/lint/profiles.py`](../src/m_cli/lint/profiles.py) | Shipped |
| Two-axis Severity (`ERROR`/`WARNING`/`STYLE`/`INFO`) + Category enum (9 values) | [`src/m_cli/lint/diagnostic.py`](../src/m_cli/lint/diagnostic.py) | Shipped |
| 42 XINDEX-derived rules — severity remapped, category assigned | [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) | Shipped |
| SAC tag policy (31 rules tagged `sac`, 11 not) | rules.py module docstring + [`tests/test_lint_profiles.py`](../tests/test_lint_profiles.py) | Shipped |
| `Rule.replaces` field for M-MOD ↔ M-XINDX cross-reference | [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) | Shipped |
| M-MOD-NN ID convention + tag (`modern`) documented | rules.py module docstring; tests in [`tests/test_lint_replaces.py`](../tests/test_lint_replaces.py) | Shipped |
| Engine-targeting config (`[lint] target_engine` + `--target-engine`) | [`src/m_cli/config.py`](../src/m_cli/config.py); [`src/m_cli/lint/cli.py`](../src/m_cli/lint/cli.py) | Shipped (knob; rules consume it in Phase 6) |
| Wild-corpus catalog | [`docs/m-corpus-catalog.md`](m-corpus-catalog.md) | Shipped |
| LSP severity mapping (`STYLE → Hint`) | [`src/m_cli/lsp/convert.py`](../src/m_cli/lsp/convert.py) | Shipped |
| **Phase 1A — `vista` profile split** (8 VA-Kernel rules → `vista` profile; engine-neutral `xindex` & `sac` profiles exclude them) | [`src/m_cli/lint/profiles.py`](../src/m_cli/lint/profiles.py); [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) | **Shipped (this PR)** |
| **Phase 1A — comma-list profile+rule-id mixing in `--rules`** | [`src/m_cli/lint/runner.py`](../src/m_cli/lint/runner.py) | **Shipped (this PR)** |
| **Phase 1B — `make lint-modern` regression gate** (driver, baseline JSON, corpus-setup script) | [`scripts/lint_modern.py`](../scripts/lint_modern.py); [`scripts/setup_modern_corpus.sh`](../scripts/setup_modern_corpus.sh); [`Makefile`](../Makefile) | Shipped |
| **Phase 2 — `LintContext` plumbing** (replaces `needs_workspace` with unified `needs_context`; ships `thresholds`, `target_engine`, `workspace`, `config` to context-aware rules) | [`src/m_cli/lint/context.py`](../src/m_cli/lint/context.py); [`src/m_cli/lint/thresholds.py`](../src/m_cli/lint/thresholds.py); [`src/m_cli/lint/runner.py`](../src/m_cli/lint/runner.py) | **Shipped (this PR)** |
| **Phase 2 — Configurable thresholds** (`[lint.thresholds]` config + `--threshold KEY=VAL` CLI flag) | [`src/m_cli/config.py`](../src/m_cli/config.py); [`src/m_cli/lint/cli.py`](../src/m_cli/lint/cli.py) | **Shipped (this PR)** |
| **Phase 2 — M-MOD-001..004** (configurable line / code-line / routine-LOC / label-LOC limits, replacing M-XINDX-019/058/035 plus a new label-body rule) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | Shipped |
| **Phase 3 — M-MOD-005..009** (cyclomatic / cognitive complexity per label, dot-block nesting depth, argument count, commands-per-line) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | Shipped |
| **Phase 4 — M-MOD-010..014** (LOCK without timeout, LOCK acquire/release imbalance, TSTART/TCOMMIT pairing, $ETRAP without NEW, OPEN/CLOSE imbalance — single-file/intra-label cut; path-sensitive versions deferred to Phase 7) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | Shipped |
| **Phase 5 — M-MOD-015, 016, 018, 019, 020** ($SELECT default arm, side-effecting postconditional, argumentless FOR without exit, broad `?.E` pattern, intra-routine by-ref-unused) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | Shipped |
| **M-MOD-017 deferred** — `$TEST` read after a $T-resetting command requires understanding *user intent* (which prior command was meant to set $T); a tractable detector needs Phase 7's data-flow analyzer. | n/a (deferred) | Deferred to Phase 7 |
| **Phase 6 — M-MOD-021..023** (engine-aware Z-command, $Z* ISV, $Z* function allowlists; consult m-standard's `standard_status` field via new `engine_allowlist()` helper; replace M-XINDX-002/028/031 with `replaces=` cross-reference) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py); [`src/m_cli/lint/_keywords.py`](../src/m_cli/lint/_keywords.py) | Shipped |
| **Pre-existing bug fix** — M-XINDX-028 / M-XINDX-031 used `intrinsic_special_variable` / `intrinsic_function` node types which tree-sitter-m doesn't emit (correct names: `special_variable` / `function_call`). Both rules were silently no-op'ing; now corrected and surface real findings on VistA. | [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) | Shipped |
| **Phase 8 — M-MOD-028..035** (label docstring, comment density, TODO/FIXME ownership, magic numbers, single-letter vars, argumentless NEW, SET X=X+1 → $INCREMENT, $Z* function abbrev → canonical) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | Shipped |
| **Modern-corpus validation pass** — cloned the catalogued non-VA corpus (`YottaDB/YDBTest`, `chrisemunt/mgsql`, `YottaDB/YDBOcto src/aux/`, `robtweed/EWD`, `shabiel/M-Web-Server`; 4,215 `.m` files total, 888 lintable). Found legacy XINDEX defaults at 62K findings (mostly SAC lowercase mandates), full M-MOD at 50K (90% of which from 4 pedantic style rules). | [`docs/m-corpus-catalog.md`](m-corpus-catalog.md); [`scripts/setup_modern_corpus.sh`](../scripts/setup_modern_corpus.sh) | Shipped |
| **Profile-split refactor** — tagged the 4 pedantic rules (M-MOD-009/028/031/032), redefined `default` as the curated M-MOD subset (26 rules, ~3K findings on the modern corpus — 94% noise reduction), added `pedantic` profile (the 4 style rules) and kept full `modern` (30 rules) for strict review. Architectural change: `default` no longer aliases `xindex` engine-neutral; users wanting legacy XINDEX checks select `--rules=xindex` explicitly. | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py); [`src/m_cli/lint/profiles.py`](../src/m_cli/lint/profiles.py) | Shipped |
| **tree-sitter-m tab fix** — scanner.c rejected tab as horizontal whitespace (only `' '` was treated as `_sp1`/`_sp2plus`); a sample YottaDB Octo file went from 3,149 parse errors → 37 (residual = unrelated `$&package.func()` external-call grammar gap). Modern corpus parse coverage: **888 → 3,470 lintable routines (21% → 82%)**. YDBTest alone went from 816 → 3,336 (+2,520). 4 new corpus tests in tree-sitter-m's test suite (114 total, all passing). | [`tree-sitter-m/src/scanner.c`](https://github.com/m-dev-tools/tree-sitter-m/blob/main/src/scanner.c); [`tree-sitter-m/grammar.js`](https://github.com/m-dev-tools/tree-sitter-m/blob/main/grammar.js) | **Shipped (upstream)** |
| **Phase 7 — data-flow infrastructure** (`flow/cfg.py` per-label CFG; `flow/vars.py` per-command variable extraction with by-reference def handling for DO/JOB and `$$F(.X)` extrinsic calls + per-argument granularity; `flow/reaching.py` definite-assignment forward MUST analyzer) | [`src/m_cli/lint/flow/`](../src/m_cli/lint/flow/) | **Shipped (2026-04-30)** |
| **Phase 7 — M-MOD-024** (read of local before any SET on every prior path) | [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) | **Shipped** |
| **Phase 7 — `flow/lock_state.py` + M-MOD-025** (LOCK leak across exit paths; forward MAY analysis with union meet; replaces M-MOD-011) | [`src/m_cli/lint/flow/lock_state.py`](../src/m_cli/lint/flow/lock_state.py) | **Shipped** |
| **Phase 7 — `flow/transaction_state.py` + M-MOD-026** (TSTART leak across exit paths; forward MAY analysis with max meet over a bounded integer lattice; replaces M-MOD-012) | [`src/m_cli/lint/flow/transaction_state.py`](../src/m_cli/lint/flow/transaction_state.py) | **Shipped** |
| **Phase 7 — `flow/etrap_state.py` + M-MOD-027** ($ETRAP leak across exit paths; forward MUST analysis with AND meet over a boolean lattice; replaces M-MOD-013) | [`src/m_cli/lint/flow/etrap_state.py`](../src/m_cli/lint/flow/etrap_state.py) | **Shipped** |
| **Phase 7 — `flow/dollar_test.py` + M-MOD-017** (stale $TEST read; forward MUST analysis tracking $T-setter freshness — IF/OPEN/LOCK/READ/JOB; was the only Phase 5 rule deferred) | [`src/m_cli/lint/flow/dollar_test.py`](../src/m_cli/lint/flow/dollar_test.py) | **Shipped** |
| Test gate: 935 passing, 1 skipped | `make check` | Green |

Profile structure today: `default` (26, curated daily lint) ⊂ `modern` (35, full M-MOD) ⊃ `pedantic` (4, the noisy style rules). Engine-neutral XINDEX legacy: `xindex` (34) + `vista` (8) = 42 ported rules. SAC subset: `sac` (23). Escape hatch: `all` (77).

**Phase 7 complete (2026-04-30).** All five originally-deferred rules ship: M-MOD-024 (read-of-undefined-local), M-MOD-025 (LOCK leak), M-MOD-026 (TSTART leak), M-MOD-027 ($ETRAP leak), M-MOD-017 (stale $TEST). Only Phase 9 (taint analysis MVP / M-MOD-036) remains as a stretch goal.

---

## 1. Phasing principles

Every phase below is a self-contained PR or PR-pair. Each rule that ships within a phase carries:

1. **Test fixtures** — at minimum one positive (must fire) and one negative (must not fire) test in [`tests/test_lint_rules.py`](../tests/test_lint_rules.py) or a sibling file.
2. **Profile membership** — pinned in [`tests/test_lint_profiles.py`](../tests/test_lint_profiles.py) so additions are deliberate.
3. **Cross-reference** — if it supersedes a legacy rule, `Rule.replaces=("M-XINDX-NN", ...)` declared and tested in [`tests/test_lint_replaces.py`](../tests/test_lint_replaces.py).
4. **Severity + category** assigned per the survey audit (§4) and the two-axis model.
5. **Modern-corpus validation** — runs cleanly under `make lint-modern` (Phase 1 sub-deliverable) without flooding false positives. Acceptable false-positive ceiling: ≤ 1% of files in any Tier 1 anchor (YDBTest, mgsql, YDBOcto-aux).
6. **Auto-fix linkage** declared via `fixer_id=...` when an `m fmt` rule can deterministically apply the fix.
7. **Performance budget** maintained: each rule reuses [`m_cli.lint._index.NodeIndex`](../src/m_cli/lint/_index.py); no fresh `tree.root_node` walks.

Severity defaults follow the survey audit (§7):

- Tier 1 rules → `Severity.ERROR`
- Tier 2 rules → `Severity.WARNING`
- Tier 3 metrics → `Severity.WARNING`
- Tier 4 hygiene → `Severity.STYLE`
- Tier 5 modernization → `Severity.INFO` for advisory; `Severity.STYLE` if auto-fixable

---

## 2. Phase-by-phase plan

### Phase 1 — `vista` profile split + `make lint-modern` gate

**Why first:** clears the path for non-VistA users to run `m lint --rules xindex` without inheriting eight VA-Kernel-specific rules. Also stands up the modern-corpus regression infrastructure that every subsequent phase needs.

**Sub-deliverable A: vista profile**

| Task | File |
|---|---|
| Add `vista` to `tags` of M-XINDX-029, 032, 034, 036, 044, 054, 056, 062 | [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) |
| Register `vista` profile in `profiles.py` | [`src/m_cli/lint/profiles.py`](../src/m_cli/lint/profiles.py) |
| Update `xindex` profile selector to **exclude** `vista`-tagged rules | profiles.py |
| Pin profile membership in tests | [`tests/test_lint_profiles.py`](../tests/test_lint_profiles.py) |
| Update `m lint --list-profiles` description | profiles.py |
| Update README + CLAUDE.md profile table | top-level docs |

**Acceptance:**
- `m lint --rules xindex` over a non-VistA repo emits zero VA-Kernel findings (CLOSE-via-ZISC, etc.).
- `m lint --rules vista` over VistA emits the eight VA-Kernel findings.
- `make lint-vista` baseline counts unchanged.

**Sub-deliverable B: `make lint-modern`**

| Task | File |
|---|---|
| New `scripts/lint_modern.py` driver (parallel to [`scripts/vista_lint.py`](../scripts/vista_lint.py)) | scripts/ |
| Walks `~/projects/m-modern-corpus/{ydbtest,mgsql,ydbocto-aux}` | scripts/lint_modern.py |
| Records baseline finding-count per repo in `scripts/lint_modern.baseline.json` | scripts/ |
| New `make lint-modern` target | [`Makefile`](../Makefile) |
| Document corpus setup steps (`git clone …`) | [`docs/m-corpus-catalog.md`](m-corpus-catalog.md) — already drafted |

**Acceptance:**
- `make lint-modern` runs end-to-end on a developer machine in <60s.
- Baseline JSON checked in; CI fails when finding-count diverges by >10% per repo (regression detector).

**Effort:** 1–2 days. **Risk:** low. **Performance impact:** none (no new rules; just retag).

---

### Phase 2 — Configurable thresholds (M-MOD-001 through M-MOD-004)

**Why:** retires the 1980s-era hard-coded byte limits (M-XINDX-019, M-XINDX-035, M-XINDX-058). Lands the first four M-MOD rules with the configuration plumbing every later phase will reuse.

**Config additions (`[lint.thresholds]`):**

```toml
[lint.thresholds]
line_length      = 200    # M-MOD-001 — replaces M-XINDX-019 (was 245 bytes)
code_line_length = 1000   # M-MOD-002 — replaces M-XINDX-058 (was 15000)
routine_lines    = 1000   # M-MOD-003 — replaces M-XINDX-035 (was 20000 bytes)
label_lines      = 50     # M-MOD-004 — new
```

**Per-rule shape:**

| ID | Title | Severity | Category | Replaces |
|---|---|---|---|---|
| M-MOD-001 | Line longer than configured limit | STYLE | style | M-XINDX-019 |
| M-MOD-002 | Code line longer than configured limit | STYLE | complexity | M-XINDX-058 |
| M-MOD-003 | Routine longer than configured LOC limit | STYLE | complexity | M-XINDX-035 |
| M-MOD-004 | Label body longer than configured LOC limit | STYLE | complexity | (new) |

**Plumbing:**

| Task | File |
|---|---|
| Add `lint_thresholds: dict[str, int]` to `Config` | [`src/m_cli/config.py`](../src/m_cli/config.py) |
| Validate threshold names against allow-list; reject negatives | config.py |
| Pass thresholds through `lint_source` via `LintContext` | new file or kwargs |
| Pin defaults in `m_cli.lint.thresholds` constants module | new [`src/m_cli/lint/thresholds.py`](../src/m_cli/lint/thresholds.py) |
| 4 rules implemented in [`src/m_cli/lint/_modern.py`](../src/m_cli/lint/_modern.py) (new file) | _modern.py |
| Test fixtures: positive + negative for each rule + threshold-override tests | tests/ |

**Decision: introducing `LintContext`.** Rather than adding kwargs to `lint_source`, introduce a small `LintContext` dataclass carrying `thresholds`, `target_engine`, `workspace`, `config` — passed to rules with `needs_context=True`. Mirrors the existing `needs_workspace` pattern but cleaner for forward growth.

**Acceptance:**
- Default thresholds applied when no config; override via TOML and CLI flag (`--threshold line_length=120`).
- All four rules pass on the modern corpus with default thresholds.
- M-XINDX-019 / 035 / 058 still fire under `xindex` profile; M-MOD-001/002/003 fire under `modern`.

**Effort:** 3–4 days. **Risk:** low (config plumbing is mechanical, rules are pure metric counting). **Performance impact:** negligible (line-iterate already cached in `NodeIndex`).

---

### Phase 3 — Tier 3 AST metrics (M-MOD-005 through M-MOD-009)

**Why:** pure AST counting; high signal at low complexity. No data-flow needed.

| ID | Title | Severity | Category | Default | Replaces |
|---|---|---|---|---|---|
| M-MOD-005 | Cyclomatic complexity per label > N | WARNING | complexity | 15 | (new) |
| M-MOD-006 | Cognitive complexity per label > N | WARNING | complexity | 20 | (new) |
| M-MOD-007 | Dot-block nesting depth > N | WARNING | complexity | 5 | (new) |
| M-MOD-008 | Argument count > N | WARNING | complexity | 7 | (new) |
| M-MOD-009 | Multiple commands per line > N | STYLE | style | 3 | (new) |

**Implementation notes:**

- **Cyclomatic complexity (M-MOD-005):** count decision points per label — `IF`, `ELSE`, `ELSEIF`, `FOR`, `$SELECT` arms, `$CASE` arms (if/when added), postconditional commands, `&&`/`||` in expressions. Standard McCabe formula: `decisions + 1`.
- **Cognitive complexity (M-MOD-006):** Sonar-style — base cost per decision, +1 per nesting level, no penalty for short-circuit operators (different from cyclomatic). Reference: SonarSource cognitive-complexity whitepaper.
- **Dot-block depth (M-MOD-007):** maximum subscript-depth of `.` continuation lines within a label.
- **Argument count (M-MOD-008):** AST inspection of `formal_args` node.
- **Multiple commands per line (M-MOD-009):** count top-level command nodes per source line.

**Tests:** `tests/test_lint_metrics.py` — fixtures cover the boundary case (exactly N → no fire; N+1 → fire) and configurable-threshold override.

**Effort:** 4–5 days. **Risk:** low. **Performance impact:** negligible (single AST pass, all five rules read from the shared `NodeIndex`).

---

### Phase 4 — Tier 1 concurrency / transaction rules, single-file cut (M-MOD-010 through M-MOD-014)

**Why:** the highest-value bug-prevention rules in the survey (§7 Tier 1). First-cut implementations are *intra-label* — they catch the obvious cases. Path-sensitive (multi-exit) versions wait for Phase 7 (data-flow infrastructure).

| ID | Title | Severity | Category | First-cut detection |
|---|---|---|---|---|
| M-MOD-010 | LOCK without timeout | ERROR | concurrency | `LOCK +^GBL` without `:N` clause; auto-fix to `:5` |
| M-MOD-011 | LOCK without matching UNLOCK in same label | ERROR | concurrency | text-scan within label; flag unbalanced |
| M-MOD-012 | TSTART without matching TCOMMIT/TROLLBACK in same label | ERROR | concurrency | same |
| M-MOD-013 | $ETRAP set without matching restore on label exit | ERROR | bug | scan label entry/exit |
| M-MOD-014 | OPEN without matching CLOSE in same label | WARNING | concurrency | same |

**Limitations of first-cut:** intra-label only. Cross-label and cross-routine forms (legitimate use-cases like setup/teardown labels) will report false positives. Acceptable trade-off for v1; Phase 7 graduates these to path-sensitive.

**Suppression directive:** users will need `; m-lint: disable=M-MOD-010` more often than for legacy rules. Document in CLAUDE.md.

**Auto-fix:** M-MOD-010 alone has a clean auto-fix (insert `:5` before the colon-less LOCK target). Wire `fixer_id="lock-add-default-timeout"` and add the corresponding `m fmt` rule.

**Effort:** 1 week. **Risk:** medium (false-positive tuning). **Performance impact:** minor; per-label scans.

---

### Phase 5 — Tier 2 control-flow + correctness rules (M-MOD-015 through M-MOD-020)

**Why:** correctness lints that don't need a flow analyzer; pure pattern matching against the AST.

| ID | Title | Severity | Category | First-cut |
|---|---|---|---|---|
| M-MOD-015 | $SELECT() without final default arm (`1:`) | WARNING | bug | inspect arm list of $SELECT call |
| M-MOD-016 | Postconditional with side-effecting argument | WARNING | bug | RHS contains `$$call()`, `$INCREMENT()`, etc. |
| M-MOD-017 | $TEST read after a command that resets it | WARNING | bug | track command sequence; commands that reset $T are documented |
| M-MOD-018 | FOR loop without explicit `Q:` exit | WARNING | bug | argumentless FOR with no Q-postconditional in body |
| M-MOD-019 | Pattern operator with `?.E` (accept-anything) | WARNING | bug | inspect pattern literal |
| M-MOD-020 | By-reference parameter never written in label body | WARNING | bug | argument prefixed `.` but never on LHS of SET |

**Effort:** 1 week. **Risk:** low. **Performance impact:** negligible.

---

### Phase 6 — Engine-aware allowlists (M-MOD-021 through M-MOD-023)

**Why:** unlocks the `--target-engine` knob shipped in §0. Replaces M-XINDX-002 / 028 / 031's absolute bans on Z-features with engine-aware allowlists.

**Schema:** new TSV files under [`src/m_cli/lint/engines/`](../src/m_cli/lint/engines/):

```
src/m_cli/lint/engines/
├── yottadb.tsv      # name<TAB>kind<TAB>since-version
├── iris.tsv
└── ansi.tsv         # M-1995 / ISO 11756 baseline
```

Each TSV lists `$Z*` ISVs and functions, plus `Z*` commands, that are *legitimate* on the named engine. Unknown tokens get flagged.

| ID | Title | Severity | Category | Replaces |
|---|---|---|---|---|
| M-MOD-021 | Z-command not in target engine's documented set | WARNING | portability | M-XINDX-002 |
| M-MOD-022 | $Z* ISV not in target engine's documented set | WARNING | portability | M-XINDX-028 |
| M-MOD-023 | $Z* function not in target engine's documented set | WARNING | portability | M-XINDX-031 |

**Plumbing:**

| Task | File |
|---|---|
| Loader `m_cli.lint.engines.allowed_z_tokens(engine, kind)` | new [`src/m_cli/lint/engines/__init__.py`](../src/m_cli/lint/engines/__init__.py) |
| Add `needs_engine: bool` to Rule (parallel to `needs_workspace`) | [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) |
| `LintContext.target_engine` — already plumbed in Phase 2 | n/a |
| TSV initial data: harvest from YottaDB and IRIS docs | TSVs |

**Decision: TSV maintenance.** Initial data lives in m-cli; if the lists grow large, consider upstreaming to [`m-standard`](https://github.com/m-dev-tools/m-standard) the way command/ISV/function tables already are.

**Acceptance:**
- `m lint --target-engine=yottadb` doesn't fire on `$ZHOROLOG` / `$ZTRNLNM` (legitimate YDB).
- `m lint --target-engine=iris` doesn't fire on `$ZF` / `$ZUTIL` (legitimate IRIS).
- `--target-engine=any` falls back to a strict ANSI allowlist (M-1995 only).

**Effort:** 1 week (most of it is TSV-data harvesting and verification). **Risk:** low–medium (TSV completeness). **Performance impact:** negligible.

---

### Phase 7 — Data-flow infrastructure + path-sensitive rules (M-MOD-024 through M-MOD-027 + M-MOD-017) — ✅ SHIPPED 2026-04-30

**Outcome:** the largest research subproject in the plan landed in five focused increments over a single day. Per-label CFG, per-command variable extraction, and four small per-resource analyzers replace what the original plan envisioned as a single `lock_state.py`. Mitigation strategy held: structural CFG shipped first and validated independently, then dataflow layered on top.

**Delivered module structure:**

```
src/m_cli/lint/flow/
├── __init__.py             # public API surface
├── cfg.py                  # per-label CFG (entry/command/exit blocks;
│                           #   fall/branch/skip/if-skip/exit edge kinds)
├── vars.py                 # per-command variable extraction
│                           #   (effects, effects_of_argument, formal_params,
│                           #    uses_in_subtree). By-reference (.X) → DEF
│                           #   in DO/JOB call args AND inside extrinsic-
│                           #   function args anywhere in expressions.
├── reaching.py             # definite-assignment forward MUST analyzer
│                           #   (intersection meet over set-of-names lattice)
├── lock_state.py           # forward MAY (union over set-of-names)
├── transaction_state.py    # forward MAY (max over bounded-integer lattice)
├── etrap_state.py          # forward MUST (AND over boolean lattice)
└── dollar_test.py          # forward MUST (AND over boolean lattice;
                            #   if-skip edge applies setter effect because
                            #   IF itself ran)
```

`liveness.py` was *not* shipped — none of the Phase 7 rules need it, so it's deferred until a consumer emerges. Reaching-defs uses set-of-names, not bit-vectors over def-sites; we don't need to identify which SET defined X, only whether X is definitely defined.

**Rules shipped:**

| ID | Title | Severity | Category | Analyzer | Replaces |
|---|---|---|---|---|---|
| M-MOD-024 | Read of local before any SET on every prior path | ERROR | bug | `flow.reaching` | — |
| M-MOD-025 | LOCK leak across exit paths | ERROR | concurrency | `flow.lock_state` | M-MOD-011 |
| M-MOD-026 | TSTART leak across exit paths | ERROR | concurrency | `flow.transaction_state` | M-MOD-012 |
| M-MOD-027 | $ETRAP leak across exit paths | ERROR | bug | `flow.etrap_state` | M-MOD-013 |
| M-MOD-017 | Stale $TEST read | WARNING | bug | `flow.dollar_test` | — |

**Edge-kind semantics encoded in the CFG:**

- `fall` — fall-through (default; command ran)
- `branch` — postconditional took true and command exited (Q:c → exit)
- `skip` — postconditional took false; command did NOT run
- `if-skip` — IF cond evaluated false; the IF *itself* ran (and thus *set $TEST*) but the rest of the line was skipped. The `dollar_test` analyzer is the only one that distinguishes if-skip from skip; for the others, IF doesn't touch their state so the difference is moot.
- `exit` — QUIT, HALT, GOTO (over-approximated as exit)

**Variable-extraction subtleties (not in original plan, surfaced in m-tools smoke):**

- DO/JOB call args: by-reference `.X` → DEF in caller's frame (callee may initialize). Without this, the m-tools test-framework idiom (`new pass,fail; do start^TESTRUN(.pass,.fail); do report^TESTRUN(pass,fail)`) generated 12 false positives on M-MOD-024.
- Per-argument running defs in SET: `S A=1, B=A` reads A in arg 2 *after* arg 1 set it — the rule walks arguments left-to-right with running state.
- Extrinsic-function by-reference: `S n=$$F(.X)` defines X in the caller. The extractor walks INTO `extrinsic_function` and `function_call` subtrees so by-reference operands anywhere become defs.

**Smoke results on m-tools (24 routines):**

| Rule | Findings | Notes |
|---|---|---|
| M-MOD-024 | 3 | Down from 17 after by-ref + per-arg fixes (82% noise reduction). Remaining: 1 real "shared local across labels" idiom + 2 grammar-ambiguous OPEN/CLOSE device parameters. |
| M-MOD-025 | 0 | No real LOCK leaks in the corpus. |
| M-MOD-026 | 0 | No real transaction leaks. |
| M-MOD-027 | 0 | No real $ETRAP leaks. |
| M-MOD-017 | 0 | No obvious staleness bugs. |

**Acceptance — met:**
- M-MOD-024 catches the canonical "read X before SET X" case across every branch in a fixture (11 test cases).
- M-MOD-025 catches LOCK held across one exit path but is silent on LOCK released on every path (7 test cases).
- M-MOD-026/027 same shape with their respective resources.
- 935 tests green; ruff + mypy clean.

**Documented limitations (Phase 7+ follow-ups):**

- GOTO targets within the routine are over-approximated as exits — cross-label dataflow is intentionally out of scope for this slice.
- FOR loops have no back-edge yet; the loop body is treated as straight-line and may under-report on a first-iteration read.
- YDB device parameters in OPEN/CLOSE syntax (`(newversion)`, `(delete)`) parse as local variables and produce false positives on I/O code — a tree-sitter-m grammar concern.
- `TROLLBACK n` (rollback to level *n*) is over-approximated as a single decrement; full level-tracking would need symbolic state.

---

### Phase 8 — Documentation + style polish rules (M-MOD-028 through M-MOD-035)

**Why:** rounds out Tiers 4 and parts of Tier 5 from the survey. Cheap rules; auto-fix candidates.

| ID | Title | Severity | Category | Auto-fix? |
|---|---|---|---|---|
| M-MOD-028 | Public label without docstring | INFO | documentation | no |
| M-MOD-029 | Comment density per label below N% (default 10%) | INFO | documentation | no |
| M-MOD-030 | TODO/FIXME without owner or ticket reference | INFO | documentation | no |
| M-MOD-031 | Magic numeric literal (other than -1, 0, 1, 2) | STYLE | style | no |
| M-MOD-032 | Single-letter variable outside FOR loop counter | STYLE | style | no |
| M-MOD-033 | Argumentless NEW (`NEW` alone) | WARNING | bug | no |
| M-MOD-034 | `SET X=X+1` for counters → `$INCREMENT(X)` | INFO | modernization | yes (replace AST) |
| M-MOD-035 | Use of `$ZD()` legacy abbreviation → `$ZDATETIME()` | INFO | modernization | yes |

**Effort:** 1 week. **Risk:** low. **Performance impact:** negligible.

---

### Phase 9 — Taint analysis MVP (M-MOD-036) — STRETCH GOAL

**Why:** the highest-value security rule in the survey (§7 Tier 1, rank 6). M's indirection (`@var`, `S @x=...`, `D @routine`) makes injection lethal; a working taint analyzer is the differentiating security feature versus other M lint efforts.

**Scope:** track values from "untrusted sources" to "sinks":

- **Sources:** `READ`, parameters of public labels (configurable allow-list), reads from `^TMP("USER", ...)`, etc.
- **Sinks:** any indirection — `@expr`, `S @expr=...`, `D @expr`, `G @expr`, `$$expr@@routine`, etc.
- **Sanitizers:** `$LENGTH`, `$EXTRACT`, `$TRANSLATE` with explicit allow-list arg, configurable via `[lint.taint]`.

**Status: research project.** Probably 3–4 weeks of design + implementation. May ship without it in M-MOD v1; the survey called this out as a stretch goal.

**Decision point:** revisit after Phase 7 ships. If `flow/` lands cleanly, taint reuses 80% of the infrastructure; if `flow/` is fragile, defer.

**Effort:** 3–4 weeks (if it ships). **Risk:** HIGH; cuttable.

---

## 3. Cross-cutting concerns

### 3.1 Test infrastructure

- **Per-rule unit tests** — every M-MOD rule lands with positive + negative fixtures in `tests/test_lint_modern.py` (or sibling). Fixture format: small `.m` source as a `bytes` literal in the test.
- **Property tests** — for the metric rules (Phase 3), add hypothesis-style threshold tests (assert that finding count is monotonic in source size).
- **Cross-rule consistency** — `tests/test_lint_replaces.py` validates that every M-MOD rule's `replaces` ids resolve to real M-XINDX rules.

### 3.2 Modern-corpus regression gate

`make lint-modern` (Phase 1B) walks the corpora catalogued in [`docs/m-corpus-catalog.md`](m-corpus-catalog.md):

- `~/projects/m-modern-corpus/ydbtest/` (4,049 `.m`)
- `~/projects/m-modern-corpus/mgsql/` (36 `.m`)
- `~/projects/m-modern-corpus/ydbocto-aux/` (21 `.m`)

Records baseline finding counts in `scripts/lint_modern.baseline.json`; CI fails on >10% per-repo divergence (regression sentinel).

**Setup script** `scripts/setup_modern_corpus.sh` clones the three repos shallowly into the conventional path. Idempotent.

### 3.3 Configuration surface evolution

| Section | Phase introduced | Keys |
|---|---|---|
| `[lint]` | shipped | `rules`, `disable`, `target_engine` |
| `[lint.severity]` | shipped | per-rule severity overrides |
| `[lint.thresholds]` | Phase 2 | `line_length`, `routine_lines`, `label_lines`, `code_line_length`, `cyclomatic`, `cognitive`, `dot_block_depth`, `argument_count`, `commands_per_line` |
| `[lint.taint]` (stretch) | Phase 9 | `sources`, `sinks`, `sanitizers` |
| `[fmt]` | shipped | `rules` |

All new keys ship with sensible defaults; absent config means "behave as if defaults were set."

### 3.4 Performance budget

| Milestone | VistA gate target | Modern gate target |
|---|---|---|
| Today (baseline) | 22.6 s (16 cores) | n/a |
| End of Phase 5 | ≤ 30 s | ≤ 15 s |
| End of Phase 7 (with flow) | ≤ 60 s | ≤ 30 s |

If any phase blows the budget, prioritize:
1. Single-pass `NodeIndex` reuse (no fresh tree walks).
2. Per-label flow analysis (don't construct routine-wide CFGs).
3. Lazy CFG construction — only when a `flow`-needing rule fires for that label.

### 3.5 LSP integration

Each new rule automatically appears in LSP diagnostics via the existing pipeline. Two LSP-specific concerns:

- **STYLE → Hint** mapping is shipped (Phase 0). Style-tier rules don't clutter the editor's Problems pane.
- **Code actions for auto-fixers**: the existing `fixer_id` linkage handles this. New rules with auto-fixers (M-MOD-010, 034, 035) get Quick Fix actions for free.

### 3.6 Documentation cadence

Every phase updates:
- [`CLAUDE.md`](../CLAUDE.md) — "Linter conventions" bullet list (rule count, profile membership)
- [`README.md`](../README.md) — rule-count table
- [`docs/m-linting-survey.md`](m-linting-survey.md) — strike through any rule that ships in the rank-ordered list
- This file — mark the phase done in §0

---

## 4. Sequencing and milestone targets

Milestones are working chunks; each ends in a deployable state.

| Milestone | Phases | Rules added | Wall-time estimate | Status |
|---|---|---|---|---|
| M1 | Phase 1 | 0 (vista profile + corpus gate) | 1–2 days | **✅ shipped** |
| M2 | Phase 2 + 3 | 9 (M-MOD-001..009) | 2 weeks | **✅ shipped** |
| M3 | Phase 4 + 5 | 11 (M-MOD-010..020) | 2 weeks | **✅ shipped** (10 rules; M-MOD-017 deferred to Phase 7) |
| M4 | Phase 6 + 8 | 11 (M-MOD-021..023, 028..035) | 2 weeks | **✅ shipped** |
| M5 | Phase 7 | 5 (M-MOD-024..027 + M-MOD-017) | 3 weeks (estimate); shipped in 1 day | **✅ shipped** (2026-04-30) |
| M6 (stretch) | Phase 9 | 1 (M-MOD-036) | 3–4 weeks | YES — stretch (decision pending) |

**Through M5 (now shipped):** 35 M-MOD rules, all originally-planned analyzers (CFG + per-command vars + reaching + lock_state + transaction_state + etrap_state + dollar_test).
**Total to M6 (stretch):** 36 rules; M6 cut/keep decision pending per §6 Q5.

---

## 5. Per-phase risk register

| Phase | Risk | Mitigation |
|---|---|---|
| 1 | corpus URLs change / repos disappear | `scripts/setup_modern_corpus.sh` pins commit SHAs |
| 2 | threshold defaults wrong for real-world code | run on modern corpus before locking defaults; expose CLI override |
| 3 | cyclomatic metric definition mismatch with industry tools | document the formula in rule docstring; provide test fixtures from McCabe paper |
| 4 | false positives on legitimate cross-label LOCK / TSTART | document `; m-lint: disable=` workflow; promise path-sensitive fix in Phase 7 |
| 5 | M-MOD-017 ($TEST tracking) needs full command-effect table | maintain `m_cli.lint.command_effects` table sourced from m-standard |
| 6 | TSV completeness; engines add new $Z* functions | quarterly resync; CI test that flags TSV staleness against m-standard |
| 7 | flow analysis perf blows the budget | per-label scoping; LRU cache; profile-as-you-go |
| 7 | flow analysis precision (false positives) | over-approximate at first (favor recall); add precision iteratively |
| 8 | comment-density rule is opinion-loaded | ship as INFO not WARNING; configurable threshold |
| 9 | taint analysis is research-grade | stretch goal; deferrable |

---

## 6. Open design questions

These are unresolved at plan-time. Each should be answered before its phase starts.

1. **`--rules=all` vs `replaces` interaction.** Today an M-MOD rule and its replaced M-XINDX rule both fire under `--rules=all`, causing double-reporting. Should the resolver auto-suppress legacy rules in favor of replacements? Pro: cleaner output. Con: less explicit. **Recommendation: keep both firing under `all`; the `modern` and `xindex` profiles are mutually exclusive in normal use.** Decide formally in Phase 2.

2. **`LintContext` shape.** The dataclass introduced in Phase 2 carries thresholds, target_engine, workspace, config. Should it also carry `target_engine` allowlists (loaded once per run) and the m-standard keyword tables? **Recommendation: yes — load once at lint_command entry, pass via context.** Decide formally in Phase 2.

3. **TSV maintenance: m-cli or m-standard?** Engine allowlists (Phase 6) could live in either project. m-standard already hosts command/ISV/function TSVs. **Recommendation: start in m-cli; promote to m-standard once stable and a second consumer emerges.** Decide in Phase 6.

4. **Flow-analysis precision target.** Phase 7's CFG over-approximates indirection (`@var` GOTO → "any target"). Is that good enough, or do we need value-tracking through indirection? **Decided (Phase 7 shipped):** over-approximation accepted. m-tools smoke FPs traced to a different source (by-reference parameter handling, fixed in `flow.vars`); indirection over-approximation has not yet generated noise on real corpora. Revisit if/when the modern-corpus baseline shows >5% FPs.

5. **Taint analysis: ship-or-cut decision.** After Phase 7 lands, is the residual effort for Phase 9 justified? Phase 7 landed cleanly in one day — far below the 3-week estimate — and the analyzer pattern (forward MAY/MUST over a per-resource lattice) is reusable. **Status: pending.** The flow infrastructure makes Phase 9 cheaper than originally feared, but it remains the only rule whose value-add is principally about *security* (every other M-MOD rule is correctness or style). Decide before opening the next M-MOD-036 spike.

---

## 7. Tracking

Each milestone closes when:

- ✅ All rules in the milestone have positive + negative tests
- ✅ All rules registered in the appropriate profile
- ✅ `make lint-modern` baseline updated and CI passing
- ✅ `make lint-vista` not regressed (count stable, perf within budget)
- ✅ `make check` (ruff + mypy + cov) green
- ✅ Survey doc (§7 rank-ordered list) updated to reflect what shipped
- ✅ This document's §0 status table updated

Status pinning happens in tests, not in this document. The plan describes intent; the test suite describes truth.

---

*This is a working plan. With M5 shipped, only the Phase 9 stretch goal remains to decide. The survey doc remains the design reference; this doc is the build sheet.*
