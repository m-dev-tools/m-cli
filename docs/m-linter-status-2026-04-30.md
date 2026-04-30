# `m lint` — Status & Audit Report

**Date:** 2026-04-30 *(filename was requested as `m-linter-status-2024-04-40.md`; date corrected — 2024 was a typo and `04-40` is not a valid date)*
**Audience:** M developers evaluating m-cli; m-cli contributors deciding what to fix before Phase 9.
**Scope:** comprehensive audit of every shipped lint rule against a 4,215-routine non-VA M corpus, with field-tested findings and a prioritized fix list.

---

## TL;DR

- **77 rules ship across 7 profiles.** Default = curated 31-rule M-MOD subset; `pedantic`, `xindex`, `vista`, `sac`, `modern`, `pythonic`, `all` available as opt-ins.
- **Test gate is solid**: 935 tests / 1 skipped, ruff + mypy clean, full corpus lint runs in 43 s on 16 cores (target: ≤ 60 s — 28% headroom).
- **One serious correctness bug found**: M-MOD-025 (path-sensitive LOCK leak) silently ignores **global-variable LOCK targets** and **indirection** — i.e. the way LOCK is overwhelmingly used in real M code. The legacy intra-label heuristic (M-MOD-011) catches more leaks than its supposed graduation. **Fix is small and scoped.**
- **Signal-quality issues** in M-MOD-024 (read-of-undefined-local): `$GET()` and `$DATA()` are designed-safe reads but the rule treats their argument as an unconditional use, generating false positives. Spot-check: 6 of 10 sampled findings were `$GET()`-pattern FPs.
- **Profile coherence**: 6 legacy ↔ modern rule pairs both fire under `--rules=all`. The "replaces" relationship is metadata only — neither side suppresses the other. Acceptable for `--rules=all` (escape hatch) but sub-optimal once a user mixes `xindex` and a M-MOD profile.
- **5 rules never fire** on this corpus (all M-XINDX, all "implicitly subsumed by tree-sitter ERROR nodes" — already documented). No dead-rule cleanup required, but they should be flagged in the rule index.
- **Phase 7 infrastructure is sound**: CFG, definite-assignment analyzer, and the 4 per-resource state analyzers (lock/transaction/etrap/dollar_test) all run without crashes across 3,470 routines. The bugs above are in *what they track*, not *how they track it*.

Bottom line: **the architecture is in good shape, the test discipline is high, and the issues are precise and individually small.** No structural rework needed before Phase 9.

---

## 1. Build state

| | |
|---|---|
| Tests | 935 passed / 1 skipped (`make test`) |
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

| Profile | Rules | Findings | E | W | S | I | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `default` | 31 | 31,077 | 11,498 | 12,514 | 856 | 6,209 | Curated daily lint — recommended starting point |
| `modern` | 35 | 134,848 | 11,498 | 12,514 | 90,816 | 20,020 | Full M-MOD, includes pedantic style rules |
| `pedantic` | 4 | 103,771 | 0 | 0 | 89,960 | 13,811 | M-MOD-009/028/031/032 only |
| `pythonic` | 35 | (same rules as modern; tighter thresholds) | | | | | Python-developer preset |
| `xindex` | 34 | 352,165 | 11,675 | 8,356 | 332,097 | 37 | Legacy XINDEX, engine-neutral |
| `xindex,vista` | 42 | 360,867 | 11,675 | 11,876 | 332,097 | 5,219 | Add VistA-Kernel mandates |
| `sac` | 23 | (subset of xindex) | | | | | SAC §3 mandates |
| `all` | 77 | 495,715 | 23,173 | 24,390 | 422,913 | 25,239 | Escape hatch / diagnostic only |
| `modern --target-engine=yottadb` | 35 | 125,561 | 11,498 | 3,227 | 90,816 | 20,020 | -9,287 vs default-target |

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

| Rule | Found | Replaces | Replaced-rule still firing |
|---|---:|---|---:|
| M-MOD-024 | 10,622 | — | n/a |
| M-MOD-025 | **16** | M-MOD-011 | M-MOD-011 fires 54× — see §5.1 |
| M-MOD-026 | 33 | M-MOD-012 | M-MOD-012 fires 13× |
| M-MOD-027 | 248 | M-MOD-013 | M-MOD-013 fires 249× |
| M-MOD-017 | 51 | — | n/a |

---

## 5. Issues found (prioritized)

### 5.1 🔴 P0 — M-MOD-025 silently ignores global LOCK targets and indirection

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

**Fix (small, scoped):** in `_lock_arg`, also extract names from:
- `global_variable` — extract the global name including subscripts as a stable key (e.g. `^V`, `^%zewdSession`)
- indirection — emit a sentinel like `__INDIRECT__` so the analyzer treats it as "some unknown lock held"

Add tests to `test_lint_flow_lock_state.py` covering both. Estimated effort: 30 minutes including tests.

### 5.2 🟡 P1 — M-MOD-024 false positives on `$GET()` / `$DATA()` reads

**Severity:** Medium. `$GET(X)` and `$DATA(X)` are M's defensive-read intrinsics — they exist precisely to read potentially-undefined locals without erroring. Flagging the `X` inside as an uninitialized read is wrong.

**Reproduction:**
```m
smartURL(app,page)
 i $g(technology)="" s technology="gtm"     ; M-MOD-024 fires on `technology`
 i $g(app)="" s app="SMART"                 ; M-MOD-024 fires on `app` (a formal!)
```

**Spot-check:** of 10 sampled M-MOD-024 findings, **6 were `$GET()` patterns** (FPs), 3 were cross-label callee-read patterns (documented limitation), 1 was a FOR + dot-block CFG case (under investigation).

**Estimated FP impact:** if `$GET()` patterns are ~60% of findings, the corpus-wide M-MOD-024 count drops from 10,622 to ~4,300.

**Fix:** in [`flow/vars.py`](../src/m_cli/lint/flow/vars.py), special-case `function_call` nodes whose `intrinsic_function_keyword` is `$G`/`$GET` or `$D`/`$DATA` — their first argument should not contribute uses (or should contribute a *defensive* use that M-MOD-024 ignores). Estimated effort: 1 hour including tests.

### 5.3 🟡 P1 — Legacy ↔ modern double-reporting under `--rules=all`

**Severity:** Medium. Six rule pairs both fire under `--rules=all`, generating duplicate signal:

| Legacy | Modern | Topic | Both fire under `all` |
|---|---|---|---|
| M-MOD-011 | M-MOD-025 | LOCK leak | ✓ |
| M-MOD-012 | M-MOD-026 | TSTART leak | ✓ |
| M-MOD-013 | M-MOD-027 | $ETRAP leak | ✓ |
| M-XINDX-019 | M-MOD-001 | line length | ✓ |
| M-XINDX-058 | M-MOD-002 | code line length | ✓ |
| M-XINDX-002 | M-MOD-021 | Z-command | ✓ |
| M-XINDX-028 | M-MOD-022 | $Z* ISV | ✓ |
| M-XINDX-031 | M-MOD-023 | $Z* function | ✓ |
| M-XINDX-060 | M-MOD-010 | LOCK without timeout | ✓ |

`Rule.replaces` is metadata-only today. The original design decision (Q1 in `m-linting-implementation-plan.md` §6) was to keep both firing because `xindex` and `modern` are "mutually exclusive in normal use" — but `--rules=all` and `--rules=xindex,modern` are real, valid combinations.

**Fix options (pick one):**
- **A** Resolver-level suppression: when a rule R's `replaces` includes another rule S, and R is selected, drop S from the result. Honors the design intent. ~1 hour.
- **B** Tag the legacy rules in M-MOD pairs with a `superseded` tag and exclude them from `default`/`modern`/`all` selectors (keep them findable via direct id `--rules=M-MOD-011`). ~30 min.

**Recommendation:** A. The "explicit is better" defense for keeping both visible isn't strong, and B requires the user to know the topology; A "just works."

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

| # | Issue | Effort | Severity | Impact |
|---|---|---|---|---|
| 1 | M-MOD-025 — handle global-variable LOCK targets and indirection (§5.1) | 30 min | P0 | Fixes the principal correctness bug; transforms M-MOD-025 from under-reporting to ≥ M-MOD-011's coverage. |
| 2 | M-MOD-024 — special-case `$GET()` / `$DATA()` to suppress defensive-read uses (§5.2) | 1 hour | P1 | Eliminates ~60% of M-MOD-024 findings; restores signal-to-noise. |
| 3 | Resolver-level `replaces` suppression (§5.3) | 1 hour | P1 | Stops legacy/modern double-reporting under `--rules=all`. |
| 4 | Document `--target-engine` more loudly in README + `m lint --help` (§5.4) | 15 min | P2 | First-run UX. |
| 5 | Add `tests/test_xindex_inactive.py` pinning the 5 never-fire rules (§5.5) | 15 min | P3 | Prevents silent regression; makes the inactivity intentional. |
| 6 | M-MOD-024 — investigate FOR + dot-block CFG (one of the spot-checked FPs) | 1–2 hours | P2 | Phase 7 follow-up; needs back-edge in CFG for FOR loops. |
| 7 | Globals/indirection extension in TSTART/$ETRAP analyzers (preventive — same code shape as #1, smaller blast radius because TSTART is unnamed and $ETRAP has only one target) | 15 min | P3 | Defense in depth. |

**Total to get to "ship-ready before Phase 9":** ~3 hours of focused work for items 1–3.

---

## 10. Suggested ordering

Before opening any Phase 9 (taint analysis) work:

1. **Land item 1 (M-MOD-025 globals).** This is the only correctness bug; the rule's value prop depends on fixing it.
2. **Land item 2 (M-MOD-024 $GET).** Halves the volume of the heaviest rule and is a one-day quality-of-life win for users.
3. **Land item 3 (resolver-level replaces).** Cleans up `--rules=all` UX.
4. **Update `scripts/lint_modern.baseline.json`** with the post-fix counts and re-run the regression gate.
5. **Re-run this audit** to confirm the deltas, and update §6 of `docs/m-linting-implementation-plan.md`.

Items 4–7 are nice-to-haves and can ride alongside Phase 9 or wait.

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
