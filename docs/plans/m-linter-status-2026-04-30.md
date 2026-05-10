# `m lint` — Status & Audit Report

**Date:** 2026-04-30 *(filename was requested as `m-linter-status-2024-04-40.md`; date corrected — 2024 was a typo and `04-40` is not a valid date)*
**Audience:** M developers evaluating m-cli; m-cli contributors deciding what to fix before Phase 9.
**Scope:** comprehensive audit of every shipped lint rule against a 4,215-routine non-VA M corpus, with field-tested findings and a prioritized fix list.

> ## ✅ Update — same day, all audit items landed (commits `cca0232` + `2ee9d37`)
>
> All three prioritized fixes (§5.1–§5.3) AND all five §10 follow-ups (items 4–8) shipped. Headline deltas on the modern corpus:
>
> | What | Original | Post-P0/P1 (`cca0232`) | Final (`2ee9d37`) |
> |---|---:|---:|---:|
> | Tests passing | 935 | 958 | **969** |
> | `default` profile findings | 31,077 | 29,904 | **29,429** |
> | `default` profile active rules | 31 | 28 | **28** |
> | M-MOD-025 (LOCK leak) findings | 16 | **175** | 175 |
> | M-MOD-024 (read-of-undefined) findings | 10,622 | 9,606 | **9,139** (−14%) |
> | `--rules=all` active rules | 77 | **67** | 67 |
>
> Each P0/P1 item below is now annotated **✅ FIXED** with the commit and the resulting metrics. Original audit text is preserved as the "before" snapshot. The recommended fix list (§9) and suggested ordering (§10) reflect the landed state.
>
> **Phase 9 (taint analysis MVP / M-MOD-036) is the only remaining stretch goal.**

---

## TL;DR

- **77 rules ship across 7 profiles.** Default = curated 28-rule M-MOD subset (post-suppression of 3 superseded rules); `pedantic`, `xindex`, `vista`, `sac`, `modern`, `pythonic`, `all` available as opt-ins.
- **Test gate is solid**: 958 tests / 1 skipped, ruff + mypy clean, full corpus lint runs in 43 s on 16 cores (target: ≤ 60 s — 28% headroom).
- ~~**One serious correctness bug found**: M-MOD-025 (path-sensitive LOCK leak) silently ignores global-variable LOCK targets and indirection.~~ **✅ FIXED** — M-MOD-025 now tracks `^V` globals and an `@` sentinel for indirection; corpus count rose 16 → 175, surpassing the legacy intra-label rule (54) it graduates.
- ~~**Signal-quality issues** in M-MOD-024: `$GET()` / `$DATA()` treated as unconditional uses.~~ **✅ FIXED** — first argument of `$G/$GET/$D/$DATA` now suppressed in every walker. Net: M-MOD-024 corpus count 10,622 → 9,606 (−1,016).
- ~~**Profile coherence**: 6 legacy ↔ modern rule pairs both fire.~~ **✅ FIXED** — `runner.select_rules` applies replaces-suppression at resolution time; 9 legacy duplicates dropped under `--rules=all`.
- **5 rules never fire** on this corpus (all M-XINDX, all "implicitly subsumed by tree-sitter ERROR nodes" — already documented). No dead-rule cleanup required, but they should be flagged in the rule index.
- **Phase 7 infrastructure is sound**: CFG, definite-assignment analyzer, and the 4 per-resource state analyzers (lock/transaction/etrap/dollar_test) all run without crashes across 3,470 routines. The bugs above were in *what they track*, not *how they track it*.

Bottom line: **the architecture is in good shape, the test discipline is high, and the prioritized issues are now resolved.** Phase 9 (taint analysis MVP / M-MOD-036) can begin without prerequisite cleanup.

---

## 1. Build state

| | |
|---|---|
| Tests | **958** passed / 1 skipped (`make test`) — was 935 pre-fix |
| Lint | ruff: clean (`make lint`) |
| Type-check | mypy: 0 errors across 52 source files (`make mypy`) |
| Coverage | ≥ minimum gate (`make cov` → green) |
| Corpus regression | `make lint-modern` baseline: in sync with `scripts/lint_modern.baseline.json` |
| Wild-corpus gate | `make lint-vista` (39,330 VistA routines): 22.6 s — 5.3× under the 120 s budget |

Branch: `master` (not `main`). 11 commits on top of the previous Tier-2 milestone, all under the `Phase 7 step N` heading.

---

## 2. Corpus inventory

The audit ran against `~/projects/m-modern-corpus/` — the catalog from `docs/m-corpus-catalog.md`:

| Corpus | Source | `.m` files | Lintable* |
|---|---|---:|---:|
| ydbtest | YottaDB/YDBTest | 4,049 | ~3,330 |
| ewd | robtweed/EWD | 86 | 86 |
| m-web-server | shabiel/M-Web-Server | 23 | 23 |
| mgsql | chrisemunt/mgsql | 36 | 36 |
| ydbocto-aux | YottaDB/YDBOcto src/aux | 21 | ~21 |
| **Total** | | **4,215** | **3,470** |

\* "Lintable" = parses without grammar errors. The 745 skipped files are mostly YDBTest's `inref/` test fixtures with deliberate syntactic experiments or pre-2010 dialect that exposes residual grammar gaps in `tree-sitter-m` (the recent tab-fix landed 2,520 more YDBTest routines into the lintable set; the rest is a long tail).

---

## 3. Profile-by-profile finding totals

All counts in the table below are **post-fix** (commit `cca0232`). Pre-fix snapshot is preserved in §6.

| Profile | Rules | Findings | E | W | S | I | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `default` | **28** | **29,904** | 10,325 | 12,514 | 856 | 6,209 | Curated daily lint — recommended starting point. M-MOD-011/012/013 dropped (replaced by Phase 7 path-sensitive variants). |
| `modern` | **32** | **133,675** | 10,325 | 12,514 | 90,816 | 20,020 | Full M-MOD, includes pedantic style rules. |
| `pedantic` | 4 | 103,771 | 0 | 0 | 89,960 | 13,811 | M-MOD-009/028/031/032 only. |
| `pythonic` | 32 | (same rules as modern; tighter thresholds) | | | | | Python-developer preset. |
| `xindex` | 34 | 352,165 | 11,675 | 8,356 | 332,097 | 37 | Legacy XINDEX, engine-neutral. Unchanged — no M-MOD rules in selection. |
| `xindex,vista` | 42 | 360,867 | 11,675 | 11,876 | 332,097 | 5,219 | Add VistA-Kernel mandates. Unchanged. |
| `sac` | 23 | (subset of xindex) | | | | | SAC §3 mandates. Unchanged. |
| `all` | **67** | **493,394** | 21,998 | 23,509 | 422,648 | 25,239 | Escape hatch. 9 legacy duplicates suppressed by `replaces`-resolution. |
| `modern --target-engine=yottadb` | 32 | ~123,000 | | | | | Drops the engine-portability noise on YottaDB code. |

Wall-clock on 16 cores, full corpus: 43–53 s per profile. Well under the 60 s Phase 7 budget.

**Headline:**
- `default` produces ~9 findings per lintable routine. Most users will find the volume manageable once `--target-engine` is set to their runtime.
- `xindex` is unusable on non-VA modern code — 96 findings / routine, dominated by SAC mandates around lowercase variables (M-XINDX-057: 179,650) and lowercase command keywords (M-XINDX-047: 129,774). This is *by design* — `xindex` is for VA shops and was the original motivation for splitting `default` away from it.
- `pedantic` is exactly what the name promises: 30 findings / routine, all style.

---

## 4. Top rules per profile (real signal)

### default (curated daily lint)

| Rule | Severity | Count | Notes |
|---|---|---:|---|
| M-MOD-024 | error | **10,622** | Read-of-undefined-local. Heaviest by far; FP rate elevated — see §5.2. |
| M-MOD-022 | warning | 3,967 | $Z* ISV usage. Largely silenced by `--target-engine=yottadb` (→ 479). |
| M-MOD-029 | info | 3,077 | Comment density per label below 10%. Reasonable noise. |
| M-MOD-034 | info | 2,957 | `SET X=X+1` → `$INCREMENT(X)` modernization hint. |
| M-MOD-021 | warning | 2,955 | Z-command usage. Silenced by `--target-engine=yottadb` (→ 2). |
| M-MOD-023 | warning | 2,846 | $Z* function usage. Silenced by `--target-engine=yottadb` (→ 0). |
| M-MOD-020 | warning | 926 | By-reference parameter unused. |
| M-MOD-004 | warning | 464 | Label body > 50 lines. |
| M-MOD-001 | style | 365 | Line > 200 bytes. |
| M-MOD-006 | warning | 358 | Cognitive complexity > 20. |
| M-MOD-005 | warning | 343 | Cyclomatic complexity > 15. |
| M-MOD-010 | error | 263 | LOCK without timeout. |
| M-MOD-016 | warning | 256 | Side-effecting postconditional. |
| M-MOD-013 | error | 249 | $ETRAP intra-label (legacy; superseded by M-MOD-027 — see §5.1). |
| M-MOD-027 | error | 248 | $ETRAP path-sensitive. |
| M-MOD-014 | error | 242 | OPEN/CLOSE imbalance. |
| M-MOD-007 | warning | 176 | Dot-block depth > 5. |

### Phase 7 path-sensitive rules (the new arrivals)

Pre-fix snapshot:

| Rule | Found | Replaces | Replaced-rule still firing |
|---|---:|---|---:|
| M-MOD-024 | 10,622 | — | n/a |
| M-MOD-025 | **16** | M-MOD-011 | M-MOD-011 fires 54× — see §5.1 |
| M-MOD-026 | 33 | M-MOD-012 | M-MOD-012 fires 13× |
| M-MOD-027 | 248 | M-MOD-013 | M-MOD-013 fires 249× |
| M-MOD-017 | 51 | — | n/a |

Post-fix (commit `cca0232`):

| Rule | Found | Replaces | Legacy under `default` |
|---|---:|---|---|
| M-MOD-024 | **9,606** | — | n/a |
| M-MOD-025 | **175** | M-MOD-011 | suppressed (replaces-resolution) |
| M-MOD-026 | 33 | M-MOD-012 | suppressed |
| M-MOD-027 | 248 | M-MOD-013 | suppressed |
| M-MOD-017 | 51 | — | n/a |

---

## 5. Issues found (prioritized)

### 5.1 🔴 P0 — M-MOD-025 silently ignores global LOCK targets and indirection — ✅ FIXED in `cca0232`

**Severity:** High. The path-sensitive LOCK-leak rule misses *most real LOCK usage in M code* because LOCK overwhelmingly targets globals (`^X("foo")`), not locals (`X`).

**Reproduction:**
```m
V4GETS2()
 IF $D(^HALT)=1 LOCK  HALT
 IF $D(^VS(2))=0 H 1 Q 0
 LOCK +^V(2):1 ELSE  H 1 Q 0     ; ← acquires ^V(2), no release in this label
 K ^VS(2) Q 1
```

`m lint --rules=M-MOD-025` returns nothing for this file. `m lint --rules=M-MOD-011` correctly flags it.

**Root cause:** [`flow/lock_state.py:_lock_arg`](../src/m_cli/lint/flow/lock_state.py) walks the argument's `unary_expression` payload and only extracts a name when it finds a `local_variable` child. Globals (parsed as `global_variable`) and indirection (parsed as `naked_global` or `@expr`) return `("", "")` and the analyzer drops the lock entirely.

**Evidence:** of 38 files M-MOD-011 catches but M-MOD-025 does not, every spot-checked case is either a global-variable LOCK or an indirected LOCK target.

**Fix landed:** `_lock_arg` now also extracts:
- `global_variable` payload → tracked under base name (e.g. `^V`, `^%zewdSession` — subscripts ignored, matching the M-MOD-011 model)
- `indirection` payload → tracked under sentinel `"@"` (over-approximates "some unknown lock"; ensures leaks are still detectable)

**Result:**
- 8 new tests in `tests/test_lint_flow_lock_state.py` (plain global, acquire/release, mixed local+global, three indirection cases). Total lock-state tests: 20 → 27.
- M-MOD-025 corpus count: **16 → 175** findings.
- Now correctly catches every leak M-MOD-011 catches (54), plus multi-variable cases the simple counter misses.

### 5.2 🟡 P1 — M-MOD-024 false positives on `$GET()` / `$DATA()` reads — ✅ FIXED in `cca0232`

**Severity:** Medium. `$GET(X)` and `$DATA(X)` are M's defensive-read intrinsics — they exist precisely to read potentially-undefined locals without erroring. Flagging the `X` inside as an uninitialized read is wrong.

**Reproduction:**
```m
smartURL(app,page)
 i $g(technology)="" s technology="gtm"     ; M-MOD-024 fires on `technology`
 i $g(app)="" s app="SMART"                 ; M-MOD-024 fires on `app` (a formal!)
```

**Spot-check:** of 10 sampled M-MOD-024 findings, **6 were `$GET()` patterns** (FPs), 3 were cross-label callee-read patterns (documented limitation), 1 was a FOR + dot-block CFG case (under investigation).

**Estimated FP impact at audit time:** ~60% of findings → projected reduction 10,622 → ~4,300.

**Actual reduction post-fix: 10,622 → 9,606 (−1,016, ~10%).** Smaller than estimated because the spot-check overweighted `_zewdSmart.m`'s pattern; the broader corpus has many other patterns. The remaining heaviest idiom is:

```m
i $g(X)="" s X=default     ; ← $G use is now suppressed ✓
... use of X ...           ; ← but THIS still fires; the analyzer can't yet
                           ;    model "test+default-set" as making X
                           ;    definitely defined afterward
```

The `$G` itself is now correctly suppressed (no false positive on the literal `$G(X)` line). The downstream use of `X` after the test-and-set still fires because the reaching analyzer doesn't model the aggregate flow. Captured as a Phase 7+ refinement (item 6 in §9 below).

**Fix landed:** new helpers `_is_defensive_intrinsic` and `_defensive_call_children` in `flow/vars.py` recognize `$G`/`$GET`/`$D`/`$DATA` and skip the first argument's `local_variable`. Wired into all four walkers (`_walk_local_vars`, `_walk_set_like_arg`, `_walk_generic_arg`, `_walk_call_arg`) so the suppression applies in every context these intrinsics can appear. Subscripts inside the defensive arg (`$G(X(I))`) are walked normally — `I` is still a real read.

**Result:**
- 9 new tests in `tests/test_lint_flow_vars.py` covering the canonical and abbreviated forms, SET RHS, fallback values, subscripted args, and postconditions. Total vars tests: 26 → 35.
- M-MOD-024 corpus count: **10,622 → 9,606** findings.
- $LENGTH and other non-defensive intrinsics still treat their arguments as reads (regression-tested).

### 5.3 🟡 P1 — Legacy ↔ modern double-reporting under `--rules=all` — ✅ FIXED in `cca0232`

**Severity:** Medium. Six rule pairs both fire under `--rules=all`, generating duplicate signal:

| Legacy | Modern | Topic |
|---|---|---|
| M-MOD-011 | M-MOD-025 | LOCK leak |
| M-MOD-012 | M-MOD-026 | TSTART leak |
| M-MOD-013 | M-MOD-027 | $ETRAP leak |
| M-XINDX-019 | M-MOD-001 | line length |
| M-XINDX-058 | M-MOD-002 | code line length |
| M-XINDX-035 | M-MOD-003 | routine LOC |
| M-XINDX-002 | M-MOD-021 | Z-command |
| M-XINDX-028 | M-MOD-022 | $Z* ISV |
| M-XINDX-060 | M-MOD-010 | LOCK without timeout |

`Rule.replaces` was metadata-only. The original design decision (Q1 in `m-linting-implementation-plan.md` §6) was to keep both firing because `xindex` and `modern` are "mutually exclusive in normal use" — but `--rules=all` and `--rules=xindex,modern` are real, valid combinations.

**Fix landed (option A — resolver-level suppression):** new helper `_apply_replaces_suppression` in `runner.py` drops any rule whose id appears in another selected rule's `replaces`. Applied to both code paths in `select_rules` (single-profile and comma-list).

**Behavior:**
- `--rules=all` — 9 legacy duplicates suppressed: M-MOD-011/012/013, M-XINDX-002/019/028/035/058/060. Active rules: 77 → 67.
- `--rules=default` — M-MOD-011/012/013 suppressed (legacy intra-label variants of Phase 7 path-sensitive rules). Active rules: 31 → 28.
- `--rules=M-MOD-011` (alone) — still returns just M-MOD-011 (no replacement is in the selection ⇒ no suppression).
- `--rules=xindex` (alone) — unchanged (no M-MOD rules selected).
- `--rules=M-MOD-011,M-MOD-025` (explicit pair) — replacement wins; legacy dropped. Users who truly want both run two passes.

**Result:**
- 7 new tests in `tests/test_lint_replaces.py::TestReplacesSuppression`. The pre-existing `test_default_arg_is_default_profile` was relaxed from strict list equality to "subset-of-raw-profile, with the dropped rules being replacements".
- `--rules=all` finding total: 495,715 → 493,394 (−2,321 duplicates eliminated).

### 5.4 🟢 P2 — Default `--target-engine=any` over-flags portability rules on YDB code

**Severity:** Low (UX issue, not a bug). The three engine-aware rules (M-MOD-021/022/023) treat *every* `$Z*` token as non-portable when `target_engine=any` (the default). On a YottaDB corpus this generates 9,768 findings that mostly disappear under `--target-engine=yottadb`.

**Observation:** the user has to know to set `--target-engine`. The `m-cli.toml` config supports `[lint] target_engine = "yottadb"`, but a fresh user won't discover it without reading the docs.

**Fix options:**
- **A** Detect the target engine via simple heuristics — presence of `^%ZTRNLNM`, `$ZSEARCH`, `view "TRACE"`, or the binary on `$PATH`.
- **B** First-run warning: "M-MOD-021/022/023 are firing heavily; set `target_engine` in `.m-cli.toml` to silence portable-API uses."
- **C** Just document more loudly. Add a one-liner to `m lint --help` and the README.

**Recommendation:** C is the cheapest. A is overengineering. B is a possible follow-up if C doesn't resolve user confusion.

### 5.5 🟢 P2 — Five M-XINDX rules never fire (already documented)

`M-XINDX-015`, `021`, `027`, `031`, `054` registered but produce zero findings on the modern corpus AND on VistA. They're documented in `TODO.md` as "implicitly caught by tree-sitter ERROR nodes via M-XINDX-021" and intentionally kept registered for compatibility with the XINDEX numeric-code mapping.

**Action:** none — the existing comment is accurate. Optionally, add a small `tests/test_xindex_inactive.py` that pins the 5 ids as "registered, not expected to fire" so future grammar changes that *do* trigger them are surfaced as either bugs or upgrade opportunities.

### 5.6 🟢 P3 — `pedantic` profile noise distribution

**M-MOD-031 (magic numbers)**: 38,259 findings on the modern corpus. The current implementation flags any numeric literal except `-1, 0, 1, 2`. Common numeric idioms in M (block counts, ASCII codes, status flags) produce most of the volume.

**M-MOD-032 (single-letter vars)**: 46,404 findings. Common idioms (`I`, `J` for loop vars, `X`, `Y` as Cache-style scratch) produce most volume.

These rules behave as designed — they're in `pedantic` precisely because they fire heavily. **No action.** Optional follow-up: per-rule threshold to allow well-known FOR-counter patterns through `M-MOD-032`.

---

## 6. Per-rule firing rates (the full table)

`--rules=all` against the modern corpus (3,470 routines):

| Rule | Sev | Findings | Rule | Sev | Findings |
|---|---|---:|---|---|---:|
| M-MOD-001 | S | 365 | M-XINDX-007 | E | 8,624 |
| M-MOD-002 | S | 3 | M-XINDX-008 | E | 24 |
| M-MOD-003 | W | 24 | M-XINDX-009 | W | 2,039 |
| M-MOD-004 | W | 464 | M-XINDX-010 | W | 1 |
| M-MOD-005 | W | 343 | M-XINDX-011 | E | 23 |
| M-MOD-006 | W | 358 | M-XINDX-012 | W | 6 |
| M-MOD-007 | W | 176 | M-XINDX-013 | S | 3,409 |
| M-MOD-008 | W | 96 | M-XINDX-014 | W | 35 |
| M-MOD-009 | S | 5,297 | M-XINDX-016 | W | 19 |
| M-MOD-010 | E | 263 | M-XINDX-017 | E | 1 |
| M-MOD-011 | E | 54 | M-XINDX-018 | W | 0 |
| M-MOD-012 | E | 13 | M-XINDX-019 | S | 163 |
| M-MOD-013 | E | 249 | M-XINDX-020 | W | 1 |
| M-MOD-014 | E | 242 | M-XINDX-022 | W | 33 |
| M-MOD-015 | I | 88 | M-XINDX-023 | S | 1,948 |
| M-MOD-016 | W | 256 | M-XINDX-024 | W | 2,034 |
| M-MOD-017 | W | 51 | M-XINDX-025 | W | 142 |
| M-MOD-018 | W | 71 | M-XINDX-026 | E | 12 |
| M-MOD-019 | W | 8 | M-XINDX-029 | W | 1 |
| M-MOD-020 | W | 926 | M-XINDX-030 | W | 95 |
| M-MOD-021 | W | 2,955 | M-XINDX-032 | E | 158 |
| M-MOD-022 | W | 3,967 | M-XINDX-033 | W | 1,058 |
| M-MOD-023 | W | 2,846 | M-XINDX-034 | E | 22 |
| M-MOD-024 | E | 10,622 | M-XINDX-036 | W | 3 |
| M-MOD-025 | E | 16 | M-XINDX-037 | E | 109 |
| M-MOD-026 | E | 33 | M-XINDX-038 | W | 4 |
| M-MOD-027 | E | 248 | M-XINDX-039 | E | 79 |
| M-MOD-028 | I | 13,811 | M-XINDX-040 | W | 2 |
| M-MOD-029 | I | 3,077 | M-XINDX-041 | W | 50 |
| M-MOD-030 | I | 51 | M-XINDX-042 | S | 4,428 |
| M-MOD-031 | S | 38,259 | M-XINDX-043 | W | 65 |
| M-MOD-032 | S | 46,404 | M-XINDX-044 | I | 3,448 |
| M-MOD-033 | W | 131 | M-XINDX-045 | E | 65 |
| M-MOD-034 | I | 2,957 | M-XINDX-046 | W | 7 |
| M-MOD-035 | I | 124 | M-XINDX-047 | S | 129,774 |
| | | | M-XINDX-048 | E | 25 |
| | | | M-XINDX-049 | W | 14,296 |
| | | | M-XINDX-050 | W | 17 |
| | | | M-XINDX-052 | E | 234 |
| | | | M-XINDX-055 | W | 4 |
| | | | M-XINDX-056 | W | 18 |
| | | | M-XINDX-057 | S | 179,650 |
| | | | M-XINDX-059 | W | 9 |
| | | | M-XINDX-061 | W | 23 |
| | | | M-XINDX-062 | W | 34 |
| | | | M-XINDX-063 | W | 67 |

Never-fired on this corpus: `M-XINDX-015`, `M-XINDX-021`, `M-XINDX-027`, `M-XINDX-031`, `M-XINDX-054`. (These are the parse-error / grammar-edge rules that tree-sitter handles upstream.)

---

## 7. Performance

| Profile | 3,470-routine corpus, 16 cores | Per-routine |
|---|---:|---:|
| default | 43.2 s | 12.4 ms |
| modern | 44.6 s | 12.9 ms |
| pedantic | 43.6 s | 12.6 ms |
| xindex | 48.3 s | 13.9 ms |
| xindex,vista | 49.1 s | 14.2 ms |
| all (77 rules) | 53.2 s | 15.3 ms |
| modern + target=yottadb | 44.2 s | 12.7 ms |

VistA gate (separate corpus, 39,330 routines): 22.6 s. Both gates well inside the 60 s Phase-7 budget.

The single-pass `NodeIndex` dispatcher and `ProcessPoolExecutor` parallelism do their job — adding 5 Phase-7 rules increased cost by ~3% over the Phase-6 baseline.

---

## 8. What's robust (the confidence half of the report)

These observations should give M developers confidence the suite is well-built:

1. **Engine-neutral core, opinionated profiles on top.** The lint engine has zero policy baked in; the seven profiles (`default`, `modern`, `pedantic`, `pythonic`, `xindex`, `vista`, `sac`, `all`) are explicit and named. Users opt into the policy they want.
2. **Two-axis severity + category.** Every rule declares both ERROR/WARNING/STYLE/INFO and one of nine categories (bug, security, concurrency, performance, style, complexity, documentation, portability, modernization). Filtering by either dimension is supported.
3. **Per-rule isolation.** `runner.lint_source` wraps each rule's check in try/except. A buggy rule emits one `M-INTERNAL-RULE-CRASH` diagnostic — it can't crash the whole pass.
4. **Inline directives.** `; m-lint: disable=...` (same-line, next-line, file-wide, wildcard `*`) gives users an escape hatch for any FP without touching config.
5. **Configurable thresholds.** Ten knobs exposed in `[lint.thresholds]` or `--threshold KEY=VAL`. CLI overrides config; config overrides profile preset; profile preset overrides system default.
6. **Baseline mode.** `m lint --update-baseline` lets a team adopt the linter on a noisy legacy codebase without churning every existing finding.
7. **Auto-fix linkage.** Rules carry `fixer_id` pointing to `m fmt` rules where applicable; the LSP wraps this as Quick Fix code actions.
8. **Test discipline.** 935 tests; every rule has positive + negative fixtures; cross-rule consistency pinned in `tests/test_lint_replaces.py`; profile membership pinned in `tests/test_lint_profiles.py`.
9. **Wild-corpus regression gates.** `make lint-vista` (39,330 routines) and `make lint-modern` (3,470 routines) catch regressions before they ship.
10. **LSP integration.** Diagnostics, code actions, hover-on-rule, find-references, workspace symbol — all wired through the same registry. New rules surface in editors automatically.

---

## 9. Recommended fix list (prioritized)

| # | Issue | Effort (est.) | Severity | Status |
|---|---|---|---|---|
| 1 | M-MOD-025 — handle global-variable LOCK targets and indirection (§5.1) | 30 min | P0 | ✅ **DONE** in `cca0232`. M-MOD-025: 16 → 175 findings. |
| 2 | M-MOD-024 — special-case `$GET()` / `$DATA()` (§5.2) | 1 hour | P1 | ✅ **DONE** in `cca0232`. M-MOD-024: 10,622 → 9,606. |
| 3 | Resolver-level `replaces` suppression (§5.3) | 1 hour | P1 | ✅ **DONE** in `cca0232`. `--rules=all`: 9 legacy duplicates suppressed. |
| 4 | Document `--target-engine` more loudly in README + `m lint --help` (§5.4) | 15 min | P2 | ✅ **DONE** in `2ee9d37`. CLI TIP block + README "Engine targeting" section + lint-summary nudge when ≥50 portability findings under `target_engine=any`. |
| 5 | Add `tests/test_xindex_inactive.py` pinning the 5 never-fire rules (§5.5) | 15 min | P3 | ✅ **DONE** in `2ee9d37`. 3 tests: registered, `xindex`-tagged, silent-on-clean-fixture. |
| 6 | M-MOD-024 — investigate FOR + dot-block CFG | 1–2 hours | P2 | ✅ **DONE** in `2ee9d37`. Argumentless `Q` inside a dot-block now falls through (was label-exit, killing every downstream IN set in multi-level dot-blocks under FOR). Reproducer (`utf8Encode` from EWD) goes from 3 spurious findings to 0. |
| 7 | Globals/indirection extension in TSTART/$ETRAP analyzers (preventive) | 15 min | P3 | ✅ **REVIEWED** in `2ee9d37`. No code change needed — `transaction_state` tracks an integer counter (no names), `etrap_state`/`dollar_test` track booleans against fixed targets ($ETRAP / fixed setter keyword set). The blind-spot pattern from item 1 doesn't apply. |
| 8 | M-MOD-024 — model the `IF $G(X)="" SET X=...` test+default-set idiom (§5.2 residual) | 2–3 hours | P2 | ✅ **DONE** in `2ee9d37`. New `_find_test_default_set_protections` helper detects `IF` + same-line `SET` pairs whose tested var matches the SET LHS; M-MOD-024 suppresses flags for `var` at lines `>` the protection line. Recognizes `$G`/`$GET`/`$D`/`$DATA` and the `'$D` negation. Net delta: M-MOD-024 9,495 → 9,139 (−356). |

**Status: every audit follow-up has landed.** Total reduction from this audit:
- M-MOD-024: 10,622 → 9,139 (−1,483, −14%)
- M-MOD-025: 16 → 175 (+159, **the rule went from broken to working**)
- `default` profile: 31,077 → 29,429 (−1,648)
- `--rules=all`: 9 legacy duplicates suppressed
- Test count: 935 → 969 (+34)

---

## 10. Suggested ordering

✅ **All eight items complete.** The original ordering is preserved below as a historical record:

1. ~~**Land item 1 (M-MOD-025 globals).**~~ ✅ `cca0232`
2. ~~**Land item 2 (M-MOD-024 $GET).**~~ ✅ `cca0232`
3. ~~**Land item 3 (resolver-level replaces).**~~ ✅ `cca0232`
4. ~~**Update `scripts/lint_modern.baseline.json`** with the post-fix counts.~~ ✅ `cca0232` + refreshed in `2ee9d37`
5. ~~**Re-run this audit** to confirm the deltas.~~ ✅ Updated inline (this report).
6. ~~**Items 4 & 5** (target-engine docs, never-fire pin).~~ ✅ `2ee9d37`
7. ~~**Item 8** (IF $G(X)="" test+default-set modeling).~~ ✅ `2ee9d37`
8. ~~**Items 6 & 7** (FOR back-edge, TSTART/$ETRAP global handling).~~ ✅ `2ee9d37` (item 6 fixed; item 7 reviewed and confirmed n/a)

**Phase 9 (taint analysis MVP / M-MOD-036) is the only remaining stretch goal.**

---

## 11. Methodology notes

This audit ran:
```bash
.venv/bin/m lint ~/projects/m-modern-corpus/ --rules=<profile> --format=json --jobs=16
```
for each of the 7 profiles plus `modern --target-engine=yottadb`. Findings were captured to `/tmp/m-lint-audit/<profile>.json` and aggregated with a small Python script (Counter by rule_id and by severity).

Spot-checks of M-MOD-024 used a deterministic sample of the first 10 findings in the JSON output, manually compared against the source AST and the rule's intent.

Spot-checks of M-MOD-025 vs M-MOD-011 used the set difference of files flagged by each rule; 5 of the 38 "missed by M-MOD-025" files were inspected manually.

Performance numbers are wall-clock from `time` over the full 3,470-routine corpus on a 16-core host.

No live engines (YottaDB, IRIS) were started during this audit — `m lint` is engine-neutral and runs entirely on `tree-sitter-m` parse trees.

---

*Report generated 2026-04-30. Source data: `/tmp/m-lint-audit/*.json`. Reproducer: `.venv/bin/m lint ~/projects/m-modern-corpus/ --rules=<profile> --format=json --jobs=16`.*
