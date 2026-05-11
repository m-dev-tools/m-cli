---
created: 2026-04-30
last_modified: 2026-05-10
revisions: 2
doc_type: [SURVEY, GAP-ANALYSIS]
---

# M Linting Survey & Greenfield Recommendations

**Status:** the four open questions in the original draft (§9) are now
resolved and shipped: corpus catalog, M-MOD-NN prefix + cross-reference,
two-axis severity/category model, and engine-targeting config. The
per-rule audit and rank-ordered greenfield list (§4 and §7) remain
discussion inputs for the M-MOD rollout.

**Audience:** m-cli contributors and downstream users evaluating which rules to enable.
**Scope:** the 42 XINDEX/SAC-derived rules m-cli ships today, modern engine reality, lint practice in the five largest programming languages, and a rank-ordered greenfield rule set.

**Companion documents:**
- [`docs/m-corpus-catalog.md`](m-corpus-catalog.md) — non-VistA M corpora
  for the modern-rule regression gate.
- [`CLAUDE.md`](../CLAUDE.md) "Linter conventions" — the engine-vs-profiles
  separation, severity/category model, and rule ID prefix policy.

---

## 1. Executive summary

m-cli ships 42 lint rules ported from the VA VistA Toolkit's `^XINDEX` scanner. 31 of those map to a documented section of the VA SAC (Standards & Conventions); the other 11 are XINDEX-internal smells. **A meaningful fraction of the SAC rules enforce 1980s-era physical constraints** — terminal widths, MUMPS-77 routine size limits, paper-tape-era patch-tracking conventions — that no longer apply to YottaDB or IRIS code written after roughly 2005. Eight more are direct VA Kernel mandates (`OPEN→ZIS`, `HALT→XUSCLEAN`, etc.) that have no meaning outside VistA.

This survey:

1. **Audits the 42 rules** for relevance on modern engines, with a per-rule KEEP / RELAX / STYLE / DEPRECATE-VA / DEPRECATE recommendation.
2. **Surveys lint practice** in the five largest programming languages (Python, JS/TS, Java, C/C++, C#) to identify rule categories M doesn't yet cover.
3. **Catalogs M's unique features** that warrant their own dedicated rules — naked references, indirection, postconditionals, $ETRAP, transactions, LOCK semantics.
4. **Proposes a rank-ordered, greenfield rule set** of ~50 rules derived from first principles. Some overlap with the legacy XINDEX set (those rules earn their keep on modern grounds too); many are new.

The headline recommendations:

- **20 of the 42 rules are KEEP-as-is** — they catch real, contemporary bugs.
- **6 should be RELAXED** to configurable thresholds with modern defaults (line length, routine size).
- **5 are STYLE rules** that belong in an opt-in style profile, not the default.
- **8 are VA-Kernel-specific** and should move to a `vista` profile, never running outside that context.
- **1 (`*/#` READ format)** is low-signal enough to deprecate entirely.
- **The greenfield list adds ~30 rules** in concurrency, transaction safety, security, data-flow, complexity, and modern engine usage — categories the XINDEX baseline barely touches.

---

## 2. Background: the SAC / XINDEX / M-standard lineage

Three different things are easy to confuse:

| Layer | What it is | Authority | Scope |
|-------|------------|-----------|-------|
| **M-1995 / ISO 11756** | The *language standard*. Engine-neutral; says nothing about style or coding conventions. | ANSI / ISO | Universal |
| **VA SAC (Standards & Conventions)** | A *policy document*. VA-mandated coding rules for VistA M code: line length ≤ 245, uppercase variables, NEW required for new locals, banned commands, banner formats, etc. | VA SAC Committee (SACC) | VA / VistA only |
| **^XINDEX** | A *tool*. M routine in the VistA Toolkit that scans .m files and flags violations. Mostly enforces SAC, but also surfaces parse errors, dead-label refs, and other smells SAC says nothing about. | VA | VA / VistA only |

**Why the SAC limits exist.** Most of the numeric thresholds in SAC trace to specific historical constraints:

| SAC limit | Origin |
|-----------|--------|
| Line ≤ 245 bytes | DSM/Caché early-90s line buffer; VT100 + some control-byte slack |
| Routine ≤ 20,000 bytes | MUMPS-77 routine size cap; paper-tape distribution |
| Code lines ≤ 15,000 bytes | Compiled-token-table size in some engines |
| Patch number on second line | VA's KIDS install pipeline parses banner text |
| `OPEN`/`CLOSE`/`HALT`/`JOB` Kernel mandates | VA Kernel APIs (XUS*, XQT*) provide auditing, namespace, queueing |
| `$ZD()`/`$ZTRNLNM()` discouraged | DSM-specific intrinsics not in MUMPS-77 |
| Banner format | KIDS expects regex-like fields on lines 1–2 |

When XINDEX was written (early 1990s, refined through the 2000s), every one of these constraints was real for the platforms VistA ran on. Today YottaDB has no practical routine size limit, IRIS routines run well past 20KB, and modern terminals/IDEs handle 200+ byte lines fine. **The SAC document is still maintained for VistA backward compatibility**, but a greenfield M project on YottaDB or IRIS has no reason to inherit most of these limits.

---

## 3. Today's engine reality: YottaDB ∩ IRIS

A modern M linter can assume this baseline (features in **both** engines):

**Language features both support:**

- Standard MUMPS-95 commands and intrinsics
- Structured exception handling: `$ETRAP`, `$ZTRAP` (legacy), `$STACK`, `$ZERROR`
- Transactions: `TSTART` / `TCOMMIT` / `TROLLBACK`, including nested
- Long strings (>>32K)
- Triggers (different syntax — IRIS class-based, YDB `^%TRIGGER`/`^%YGBLSTAT`)
- `$INCREMENT()` for atomic counters
- `$ZHOROLOG`, `$ZDATETIME` — high-resolution time
- `$ZHASH` / cryptographic primitives (engine-specific names)
- ZWRITE for structured dumps
- LOCK with timeout argument
- Indirection (name, pattern, argument, subscript)
- Cross-routine call graphs (DO/GOTO/$$/extrinsic)

**Effectively-unlimited or very-large limits both support:**

| Limit | YottaDB | IRIS |
|-------|---------|------|
| Routine size | No hard limit (configurable; default very large) | 32K objectscript routine; classes much larger |
| Line length | 8,192 default, configurable up to engine maximum | Up to 32K depending on encoding |
| Local variable size | Long-string mode: ~1MB | Long-string mode enabled by default in modern installs |
| Subscript depth | 31+ | 31+ |

**Engine-specific (NOT to assume):**

- Caché/IRIS has class-based ObjectScript with `Property`, `Method`, `Parameter`, `ClassMethod` syntax — not portable to YDB
- IRIS has SQL via `&sql(...)`; YDB uses %YGBLSTAT or SQL drivers
- YDB has `$ZSEARCH` (filesystem); IRIS uses `%File`
- Z-command and `$Z*` ISV/function sets differ wildly between engines
- Integer/float defaults: IRIS `$DECIMAL`/$DOUBLE; YDB IEEE
- `$VIEW`/`VIEW` arguments are entirely engine-specific

**Implication for a modern linter:** the rules that ban "non-standard" Z* features should be *engine-aware* rather than absolute — flag use of `$ZTRNLNM` (DSM legacy) on either engine, but allow `$ZHOROLOG` (YDB) or `$ZDATETIME` (both) without complaint.

---

## 4. Per-rule audit: the 42 XINDEX/SAC rules

Legend: **KEEP** (still earns its keep on modern engines) · **RELAX** (good idea, modernize threshold or scope) · **STYLE** (opinion-based; opt-in profile) · **DEPRECATE-VA** (VA Kernel-specific; ship under a `vista` profile only) · **DEPRECATE** (low-value entirely).

| ID | Title | Rec. | Rationale |
|----|-------|------|-----------|
| 002 | Non-standard 'Z' command | RELAX | Engines differ; flag against the *target engine's* documented Z-command set, not absolutely. |
| 007 | Call to undefined routine | KEEP | Cross-routine bug detection; tree-sitter index makes it cheap. |
| 008 | Call to undefined label in another routine | KEEP | Same. |
| 009 | Dead code after QUIT/HALT/GOTO | KEEP | Real refactor-leftover bug; high signal. |
| 013 | Trailing whitespace | KEEP | Universal hygiene; auto-fixable. |
| 014 | Call to missing label in this routine | KEEP | Bug detection. |
| 015 | Duplicate label | KEEP | M silently uses the first; second is dead. |
| 017 | First-line label != routine name | KEEP | Engines assume `D ^FOO` jumps to label `FOO` in routine `FOO.m`. |
| 018 | Control character | KEEP | Hygiene; tab is allowed. |
| 019 | Line > 245 bytes | RELAX | The 245 limit is a 1990s terminal artifact. Make configurable; default ~200 for readability, no hard cap. |
| 020 | VIEW command used | KEEP | VIEW is implementation-specific and non-portable; even for engine-specific code, worth flagging once with an opt-out. |
| 021 | Parse error | KEEP | Fundamental. |
| 022 | Exclusive KILL `K (X,Y)` | STYLE | Surprising semantics ("keep only X,Y") but legitimate. Move to style profile. |
| 023 | Unargumented KILL | KEEP | Wipes entire local symbol table; in shared code this destroys callers' state. |
| 024 | KILL of unsubscripted global | KEEP | `KILL ^GBL` nukes a whole global tree — catastrophic if accidental. |
| 025 | BREAK command | KEEP | Production code shouldn't pause for the debugger. |
| 026 | Exclusive/Unargumented NEW | STYLE | Confusing scope semantics but legitimate. Move to style profile. |
| 027 | $VIEW function | KEEP | Same reasoning as 020. |
| 028 | $Z* ISV used | RELAX | Many $Z* ISVs are legitimate on both engines (`$ZHOROLOG`); flag against an engine-aware allowlist instead. |
| 029 | CLOSE → ZISC | DEPRECATE-VA | VA Kernel-specific; meaningless outside VistA. |
| 030 | LABEL+OFFSET reference | KEEP | Fragile to edits; never a good idea. |
| 031 | $Z* function used | RELAX | Same as 028. |
| 032 | HALT → XUSCLEAN | DEPRECATE-VA | VA Kernel-specific. |
| 033 | READ without timeout | KEEP | Hangs on missing input; a real bug. |
| 034 | OPEN → ZIS | DEPRECATE-VA | VA Kernel-specific. |
| 035 | Routine > 20,000 bytes | RELAX | Modern engines tolerate orders of magnitude more. Replace with line-of-code or function-count metric (default 1,000 LOC, configurable). |
| 036 | JOB → TASKMAN | DEPRECATE-VA | VA Kernel-specific. |
| 041 | Star/pound READ format | DEPRECATE | Old format; rarely encountered; low signal. |
| 042 | Null line | STYLE | Pure subjective hygiene. |
| 044 | 2nd line violates SAC | DEPRECATE-VA | VA banner format. |
| 045 | SET to %global | KEEP | `%` globals are reserved by both engines; writing to them collides with system code. |
| 047 | Lowercase commands | STYLE | Engines accept either; pure style. |
| 049 | Unused label | KEEP | Dead-code detection. |
| 050 | Extended global reference | KEEP | Cross-environment refs are real and dangerous; warrant a justification comment. |
| 051 | Empty IF/ELSE no body | KEEP | Logic bug. |
| 054 | $SYSTEM access (Kernel-only) | DEPRECATE-VA | VA-policy specific. |
| 056 | Patch number on second line | DEPRECATE-VA | VA KIDS-pipeline specific. |
| 057 | Lower/mixed case local variable | STYLE | M is case-sensitive for variables; consistency is style, not bug. |
| 058 | Code line > 15,000 bytes | RELAX | Engines allow more, but this is still pathological. Configurable; default ~1,000. |
| 060 | LOCK without timeout | KEEP | Deadlock prevention. Strengthen — see §7. |
| 061 | Non-incremental LOCK | KEEP | Resource discipline. |
| 062 | First-line violates SAC | DEPRECATE-VA | VA banner format. |

**Summary:** 20 KEEP · 6 RELAX · 5 STYLE · 8 DEPRECATE-VA · 1 DEPRECATE · *= 40* (+2 STYLE-leaning rules already counted under STYLE).

**Recommendation:** introduce two new profiles in `m_cli.lint.profiles`:

- `vista` — the 8 VA-Kernel-specific rules that only make sense in VistA. Today's `xindex` profile would split: portable rules stay in `xindex`, VistA-only rules move to `vista`.
- `modern` — `xindex` minus DEPRECATE-VA minus DEPRECATE-entirely, with RELAX rules getting modern thresholds. This becomes a candidate for the new `default`.

---

## 5. Lint practice in the five largest programming languages

A snapshot of what the dominant linters check, by category. The goal is to identify rule categories M's linter doesn't yet cover.

### 5.1 Python (ruff / pylint / mypy / bandit)

ruff alone implements ~800 rules across these categories:

- **Bug-prone patterns** (pyflakes, bugbear) — undefined names, unused imports, mutable default args, except-without-handler
- **Style** (pycodestyle / PEP8) — naming, whitespace, line length (configurable, default 88)
- **Complexity** (mccabe) — cyclomatic complexity threshold per function
- **Security** (bandit, dlint) — eval/exec, weak crypto, hardcoded passwords, SQL injection patterns, pickle-of-untrusted
- **Performance** (perflint, comprehensions) — list comprehension where possible, avoid quadratic patterns
- **Modernization** (pyupgrade) — use `f"…"` over `"…".format()`, dict-comprehension over dict()
- **Type checking** (mypy) — type errors, narrowing, generics
- **Documentation** (pydocstyle) — docstring presence, format

### 5.2 JavaScript / TypeScript (ESLint / Biome / TypeScript)

ESLint: ~250 core rules + thousands in plugins. Categories:

- **Possible errors** — no-cond-assign, no-dupe-keys, no-unreachable
- **Best practices** — eqeqeq, no-eval, no-with, no-implicit-globals
- **Variables** — no-shadow, no-undef, no-unused-vars
- **Stylistic** — indent, quotes, semi (Biome handles most of these)
- **ES6+** — prefer-const, arrow-body-style, no-var
- **Security** (eslint-plugin-security) — detect-eval-with-expression, detect-non-literal-fs-filename
- **React/TypeScript-specific plugins** — exhaustive-deps, no-explicit-any

### 5.3 Java (Checkstyle / PMD / SpotBugs / SonarLint)

Combined: ~600+ rules. Categories:

- **Naming** — class/method/var conventions
- **Imports** — unused, ordering
- **Bugs** (SpotBugs ~400 patterns) — null deref, equals/hashCode, infinite loop, SQL injection, time-of-check time-of-use
- **Code smells** (PMD) — God class, long method, cyclomatic complexity, cognitive complexity
- **Concurrency** — synchronization on mutable, double-checked locking
- **Performance** — string concatenation in loops, unnecessary boxing
- **Security** — XML external entity, weak random, weak crypto, deserialization

### 5.4 C / C++ (clang-tidy / cppcheck / MISRA)

clang-tidy: ~200 checks. cppcheck: ~1,000. MISRA C: ~140 rules (safety-critical industries).

- **Memory** — leaks, use-after-free, double-free, uninitialized read, buffer overflow
- **Undefined behavior** — signed overflow, strict aliasing, sequence points
- **Concurrency** — race conditions, atomicity violations, deadlock
- **Modernization** — use-auto, use-nullptr, use-override, use-default-member-init
- **Readability** — magic numbers, function size, parameter count
- **Performance** — unnecessary-copy, move-const-arg
- **Portability** — implementation-defined behavior

### 5.5 C# (Roslyn analyzers / StyleCop / SonarLint)

~300 first-party rules + many third-party.

- **Bug-prone** — null-flow, async/await misuse, IDisposable
- **Performance** — string-builder for loops, struct-in-collection
- **Style** (StyleCop) — naming, ordering, documentation
- **Security** — TaintAnalysis (data-flow from untrusted source to sink), weak crypto, path traversal

### 5.6 Common categories M's linter currently lacks

Mapping the union of the above against m-cli's 42 rules:

| Category | M-cli today | Gap |
|----------|-------------|-----|
| Parse errors | ✓ | — |
| Dead code (after unconditional) | ✓ | — |
| Unused symbols | ✓ (labels) | Variables, parameters |
| Style consistency | partial (lowercase commands) | Naming, indentation, line-end |
| Cyclomatic complexity | ✗ | Major gap |
| Cognitive complexity | ✗ | Major gap |
| Function size metric | line-byte (legacy) | Modern LOC / depth metrics |
| Magic numbers / strings | ✗ | Major gap |
| Security: untrusted-input flow | ✗ | Critical gap (M's indirection makes this lethal) |
| Concurrency: lock discipline | partial (timeout) | Lock-leak across paths, granularity |
| Concurrency: transaction discipline | ✗ | TSTART/TCOMMIT pairing, ETRAP unwind |
| Resource leaks | ✗ | OPEN/CLOSE pairing, JOB tracking |
| API misuse / deprecation | ✗ | Engine-specific allowlists |
| Documentation completeness | ✗ | Public-label docstrings |
| Data-flow: read-of-undefined | ✗ | Major gap (needs flow analysis) |
| Modernization | ✗ | Use of legacy DSM/Caché-isms on modern engines |
| Type-mismatch / pattern soundness | ✗ | M-unique opportunities |

The columns marked "Major gap" or "Critical gap" inform the rank-ordering in §7.

---

## 6. M's strengths, weaknesses, and unique features

A useful M linter does more than port general-purpose patterns — it leverages what makes M *M*.

### 6.1 Strengths the linter should not punish

- **Globals as native persistent storage** — globals are not "evil"; they're the data layer. Don't lint them away wholesale. Do lint reckless writes (KILL, naked, extended ref).
- **String-arithmetic duality** — `"123"+1=124` is idiomatic; rules from typed languages don't apply.
- **Sparse arrays** — `S X(1,5,99)=…` skipping intermediate subscripts is fine. `$ORDER` traversal is the standard idiom.
- **$ORDER + transactions** — this is M's killer feature for hierarchical data. Reward, don't restrict.
- **Postconditionals** — `D:condition foo()` is concise and idiomatic when used carefully. The lint target is *side-effecting* postconditionals, not postconditionals themselves.
- **Late-bound names via indirection** — powerful when used for legitimate metaprogramming. The lint target is *unsanitized user input* through indirection.

### 6.2 Weaknesses (high-leverage lint targets)

- **No type system** — variables hold whatever; type confusion is silent. Lint can pattern-check expected shapes (e.g., a variable always read with `+` should have been SET to a number).
- **Implicit scope** — without `NEW`, locals leak between routines. Lint missing `NEW` on routine entry that touches local vars.
- **Naked references** — `^GBL(1,2)` then `^(3)` reuses the prior global's prefix. One stray `S ^OTHER(...)` between resets the naked indicator silently.
- **$ETRAP semantics** — old-style error trap. Easy to leak (set in entry, not restored on QUIT). New code should prefer try/catch idioms (where supported).
- **Indirection** — `@var`, `S @x=...`, `D @routine` — lint can identify the unsafe forms (input not validated).
- **LOCK without timeout** — silent deadlocks.
- **Argumentless commands** — `K`, `D`, `G` with no argument are dangerous in shared code.
- **Single-letter variables** — `S X=1, Y=X+2` is dense; M's small symbol-table cost is no longer a meaningful constraint.
- **Abbreviated commands** — `S W K D G Q` are write-only readability problems in checked-in code.

### 6.3 Unique features needing dedicated rules

These are M idioms with no analog in mainstream languages — they each warrant their own rule:

| Feature | Lint target |
|---------|-------------|
| Naked reference | Used across non-trivial control flow → fragility |
| `@var` indirection | Argument from outside trust boundary → injection |
| `$TEST` | Read after a command that resets it → wrong branch |
| Postconditional on commands with side effects on `$T` | Order-of-evaluation traps |
| Argumentless `KILL` | In shared code → wipes caller's locals |
| Argumentless `NEW` (`NEW`) | Stack-saves all locals; almost always a mistake |
| Argumentless `DO` / `GOTO` with `$T` | Implicit conditional flow |
| `LOCK` without timeout | Deadlock |
| `LOCK` non-incremental | Resource discipline |
| `TSTART` without paired `TCOMMIT`/`TROLLBACK` | Transaction leak |
| `$ETRAP` set without restoration on every exit | Error-handler leak |
| `$SELECT()` with no final default arm | Coverage bug |
| Pattern operator with overly-broad pattern (`?.E`) | Accept-anything anti-pattern |
| `MERGE` between globals without transaction | Inconsistent intermediate state |
| Side-effecting expression inside `$SELECT()` arm | Order-of-eval traps |

---

## 7. Greenfield rank-ordered rule recommendations

Derived independently of legacy XINDEX/SAC; some overlap with current rules (which confirms they earn their keep on first principles).

**Ranking criteria, in order:**
1. **Bug consequence** — does the bug cause data loss, deadlock, or security vulnerability?
2. **True-positive rate** — how often is a finding a real bug vs. noise?
3. **Detection feasibility** — does m-cli's tree-sitter + WorkspaceIndex make it cheap?
4. **Auto-fix availability** — bonus for rules with deterministic fixes.

### Tier 1 — Concurrency, transaction, and data-safety bugs (highest value)

| # | Rule | Reasoning |
|---|------|-----------|
| 1 | **LOCK without timeout** | Silent deadlocks. Strict; auto-fix to add `:5` default. |
| 2 | **TSTART without matching TCOMMIT/TROLLBACK in same lexical scope** | Transaction leak; orphan held locks. |
| 3 | **$ETRAP set without restore on every exit path** | Error-handler leak; stale traps fire on caller. |
| 4 | **KILL of unsubscripted global (`KILL ^GBL`)** | Catastrophic data loss. Require explicit subscript or comment override. |
| 5 | **Naked reference outside the SET that established it** | One stray write resets the naked indicator silently. |
| 6 | **Indirection of unsanitized input** (`@untrusted`, `S @x=...` where `x` traces to user input) | Code injection. Needs taint analysis. |
| 7 | **Argumentless KILL in shared/library code** | Wipes caller's local symbol table. |
| 8 | **GOTO into another routine (`^routine`)** | Non-local jump; debugger and reasoning hostile. |
| 9 | **OPEN device without matching CLOSE on every exit path** | Resource leak. |
| 10 | **READ without timeout** | Hang. |
| 11 | **Read of local variable not SET on every prior path** (data-flow) | Undefined value. |
| 12 | **MERGE between globals without surrounding transaction** | Observable inconsistent intermediate state. |

### Tier 2 — Correctness, control-flow, and API discipline

| # | Rule | Reasoning |
|---|------|-----------|
| 13 | **Empty IF/ELSE/FOR body without explicit `;intentional` comment** | Refactor leftover bug. (Already in m-cli; keep + extend.) |
| 14 | **Dead code after unconditional QUIT/HALT/GOTO** | Refactor leftover. (Already shipped.) |
| 15 | **Cross-routine call to undefined routine/label** | Typo. (Already shipped.) |
| 16 | **Duplicate label** | Second is dead. (Already shipped.) |
| 17 | **$SELECT() without final default (1:…) arm** | Returns undefined on no match. |
| 18 | **Postconditional with side-effecting argument** (`S:$$check() X=…`) | Order-of-evaluation traps. |
| 19 | **`$TEST` read after a command that resets it** | Wrong branch on stale `$T`. |
| 20 | **FOR loop with no terminating expression** (`F` with no bound) | Infinite loop unless `Q:` inside. Require `Q:`. |
| 21 | **Engine-non-portable feature without `; engine: yottadb\|iris` directive** | Portability. |
| 22 | **Direct global write where domain has API** (configurable allow-list per global) | Bypasses validation/auditing. |
| 23 | **Pattern operator with `?.E` or unanchored broad pattern** | Accept-anything anti-pattern. |
| 24 | **Parameter declared by reference (`.var`) but never written** | Confusing intent — should be by value. |

### Tier 3 — Maintainability and cognitive load

| # | Rule | Reasoning | Default threshold |
|---|------|-----------|-------------------|
| 25 | **Cyclomatic complexity per label > N** | Reviewability; test coverage difficulty. | 15 |
| 26 | **Cognitive complexity per label > N** (Sonar-style) | Compounds nesting, jumps, recursion. | 20 |
| 27 | **Routine length > N lines** | Replace SAC's 20,000-byte rule. | 1,000 LOC |
| 28 | **Label body length > N lines** | Encourage decomposition. | 50 LOC |
| 29 | **Dot-block nesting depth > N** | Readability. | 5 |
| 30 | **Argument count > N** | Readability. | 7 |
| 31 | **Multiple commands per line beyond N** | Readability. | 3 |
| 32 | **Magic numeric literal** (other than -1, 0, 1, 2) outside `; const` directive | Maintainability. | — |
| 33 | **Single-letter variable outside FOR loop counter** | Readability. | — |
| 34 | **Argumentless NEW (`NEW`) anywhere** | Stack-saves all locals — almost always a mistake. | — |
| 35 | **Public label without docstring on the next line** | Documentation. | — |

### Tier 4 — Hygiene and style (configurable, opt-in by profile)

| # | Rule | Reasoning |
|---|------|-----------|
| 36 | **Trailing whitespace** | Hygiene. Auto-fix. (Already shipped.) |
| 37 | **Control character in source** | Hygiene. (Already shipped.) |
| 38 | **Line longer than N bytes** (configurable, modern default 200) | Replaces SAC 245 with sensible default. |
| 39 | **Code line longer than N bytes** (configurable, default 1,000) | Replaces SAC 15,000. |
| 40 | **Routine name does not match first label** | Engines assume this. (Already shipped.) |
| 41 | **Abbreviated commands (S, W, K, D, G, Q) in checked-in code** | Readability; opt-in style profile. |
| 42 | **Lowercase commands** | Style; opt-in. |
| 43 | **Lower/mixed-case local variables** | Style; opt-in (M is case-sensitive). |
| 44 | **Comment density per label below N%** | Documentation. |
| 45 | **TODO/FIXME without ticket or owner** | Process. |

### Tier 5 — Modern engine usage

| # | Rule | Reasoning |
|---|------|-----------|
| 46 | **Use of `$ZD()` legacy abbreviation** | Replace with `$ZDATETIME()`. |
| 47 | **Use of `$ZTRNLNM()`** (DSM legacy) | Non-portable; use `$ZGETENV` (YDB) / `$SYSTEM.Util.GetEnviron()` (IRIS). |
| 48 | **`SET X=X+1` for a counter** | Use `$INCREMENT(X)` for atomicity. |
| 49 | **`$ZHASH` / hand-rolled checksum** | Use engine-current crypto API. |
| 50 | **Use of `Z`-command not in target engine's documented set** | Engine-aware allowlist; replaces M-XINDX-002 absolute ban. |

### Cross-cutting recommendations

- **Profiles.** Ship four profiles: `default` (Tiers 1–3 + auto-fixable Tier 4), `strict` (everything), `style` (Tier 4 only), `vista` (the 8 VA-Kernel rules + this `default`).
- **Severity.** Tier 1 → FATAL. Tier 2 → STANDARD. Tier 3–4 → WARNING. Tier 5 → INFO.
- **Auto-fix linkage.** Rules 1, 13, 36, 38, 41, 42, 43, 46, 47, 48 can ship auto-fixers.
- **Configuration.** All numeric thresholds (lines 25–31, 38, 39, 44) read from `[lint.thresholds]` in `.m-cli.toml`.

---

## 8. Implementation roadmap (suggested)

A defensible order of operations for getting from today's 42-rule baseline to the greenfield set:

1. **Profile split (current PR).** Tag every rule `xindex` (provenance) + `sac` (policy) where applicable. **Done.**
2. **Add the `vista` profile.** Move the 8 VA-Kernel rules out of `default`. Drop them from the `xindex` profile too — they are XINDEX rules but VA-Kernel-policy, not portable lints. Keep them runnable for VA shops via `m lint --rules vista`.
3. **Modernize thresholds** (Rules 38, 39, 27, 28). Replace 245-byte hard-coded line limit with configurable `[lint.thresholds] line_length = 200`. Same for routine size.
4. **Tier 1 expansions** (one or two per release):
   - **Strengthen LOCK rule** (Rule 1) — track LOCK across all paths to UNLOCK.
   - **TSTART/TCOMMIT pairing** (Rule 2) — needs control-flow analysis.
   - **Naked reference flow** (Rule 5) — track naked indicator across the AST.
5. **Tier 3 metrics** (Rules 25–28). Cyclomatic and cognitive complexity, routine/label length. These are mostly counting; tree-sitter makes them straightforward.
6. **Data-flow rule kit** (Rules 11, 18, 19). Build a small flow analyzer over labels; reuse for future taint analysis.
7. **Taint analysis MVP** (Rule 6). Indirection-of-untrusted is high-value but harder; warrants its own design doc.
8. **Engine-aware Z-command allowlist** (Rules 50, 21). Per-engine TSV like `m-standard` ships, with explicit `target_engine` in `.m-cli.toml`.
9. **Documentation rules** (Rules 35, 44, 45). Lightweight; mostly text scanning.
10. **Style profile polish** (Tier 4). Auto-fix wiring for abbreviated-commands rule, etc.

Throughout, every new rule lands behind:

- Real `.m` test fixtures (positive + negative)
- A line in the rule taxonomy in `lint/rules.py` module docstring
- A profile membership check in `tests/test_lint_profiles.py`
- The standard wild-corpus regression check for the relevant profile (VistA for `vista` and `xindex`; a chosen modern corpus for `modern`/`default` once we identify one)

---

## 9. Resolutions

The four open questions raised in the original draft of this document
have been addressed. Recap of the decisions and what shipped:

### 9.1 Wild-corpus for the modern profile — RESOLVED

**Decision:** catalog post-2000, non-VistA M code as the regression gate
for the M-MOD-NN ruleset. Keep VistA (`make lint-vista`) as the legacy
gate for `xindex`/`sac`/`vista` profiles.

**Shipped:** [`docs/m-corpus-catalog.md`](m-corpus-catalog.md) — verified
non-VistA repos (all live as of 2026-04-29), tiered by suitability,
restricted to repos with parseable `.m`/`.mac` content.

**Important correction (2026-04-29):** the original draft listed
InterSystems `.cls` repos (`intersystems/ipm`, `intersystems/isc-rest`,
`intersystems/isc-codetidy`) as Tier 1 anchors with a notional
"`.cls` extraction shim" caveat. That was wrong: **`.cls` is
ObjectScript, not MUMPS**. ObjectScript is a *superset* of M (per
[InterSystems' own documentation](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GCOS_syntax))
that adds class declarations (UDL), OO operators (`..method`,
`##class`, `$$$macro`, `$THIS`, relative-dot syntax, typed `As %Type`
parameters), and embedded SQL/HTML/JS islands. Even after extracting
method bodies from the class wrapper, the bodies retain non-MUMPS
tokens that `tree-sitter-m` does not parse. m-cli's lint rules
cannot usefully run against `.cls` files — they would emit parse
errors and false positives. All `.cls`-predominant repos have been
moved to a "Future / out-of-scope" section in the catalog and become
candidates only when a `tree-sitter-objectscript` (or equivalent)
ships.

Recommended seed for `make lint-modern` (post-correction):

  1. **`YottaDB/YDBTest`** — 4,049 `.m` files; the largest non-VistA M
     corpus, written by the YottaDB engine authors against modern idioms
     (TSTART/TCOMMIT, $INCREMENT, $ETRAP, triggers, indirection).
  2. **`chrisemunt/mgsql`** — 36 `.m` files, Apache-2.0; engine-neutral
     M written to run unchanged on YottaDB, IRIS, and Caché. The
     **portability anchor**: any rule that fires here likely points at
     a real engine-portability problem. Different author voice from
     YottaDB-org.
  3. **`YottaDB/YDBOcto src/aux/`** — 21 hand-written runtime helpers,
     AGPL; production YottaDB-author code, tightly idiomatic.

Tier 1/2 supplements (also pure `.m`): `robtweed/EWD` (86 `.m`),
`shabiel/M-Web-Server` (23 `.m`), `YottaDB/YDB-Web-Server` (17 `.m`),
`lparenteau/DataBallet` (18 `.m`). Tier 3 (historical) is the FreeM
ecosystem and small ANSI-M references.

**Caveats** captured in the catalog: `.cls` excluded entirely (see
above); `.mac` is best-effort because InterSystems supports mixing
ObjectScript and MUMPS in `.mac` bodies; YDBTest deliberately
includes edge-case syntax for engine testing (some directories
should be exempted); GitHub's `language:M` Linguist tag conflates
MUMPS with MATLAB / Mathematica / Power Query / Objective-C and is
unreliable.

### 9.2 Rule ID prefix for new rules — RESOLVED

**Decision:** introduce **`M-MOD-NN`** for the greenfield modernization
track. Preserve `M-XINDX-NN` for ports (provenance-honest); future
prefixes `M-IRIS-NN`, `M-YDB-NN`, `M-ANSI-NN` are reserved for
engine- or standard-specific rule sets.

**Shipped:**
- `Rule.replaces: tuple[str, ...]` field for cross-referencing modern
  rules to the legacy XINDEX rules they supersede. Example:
  `Rule(id="M-MOD-001", ..., replaces=("M-XINDX-019",))`.
- New `modern` profile in `m_cli.lint.profiles` (selector by tag
  `modern`, currently empty pending the first M-MOD rule).
- Tests in `tests/test_lint_replaces.py` pin the cross-reference shape:
  every `replaces` id must resolve to a registered rule; M-MOD rules
  must carry the `modern` tag and not the `xindex`/`sac` provenance
  tags.
- M-MOD-NN convention documented in `m_cli.lint.rules` module docstring.

`Rule.replaces` is metadata: the runtime does not auto-suppress the
legacy rule when both apply (users pick a profile). The cross-reference
is for documentation, migration tooling, and downstream consumers
that want to bridge results between profiles.

### 9.3 Severity scheme — RESOLVED

**Decision:** decouple **actionability** (severity) from **kind**
(category). Replace the muddy FATAL/STANDARD/WARNING/INFO scheme
(where "STANDARD" leaked SAC policy into the severity name) with:

| Severity | Meaning | LSP map | Actionable? |
|----------|---------|---------|-------------|
| `ERROR`   | must fix; CI gate fails | `Error` | yes |
| `WARNING` | should fix; configurable CI gate | `Warning` | yes |
| `STYLE`   | auto-fix preferred; cosmetic / convention | `Hint` | yes |
| `INFO`    | informational; no action expected | `Information` | **no** |

The actionable / non-actionable line is `Severity.is_actionable` —
only INFO is non-actionable.

A new orthogonal `Category` enum captures *kind*: `bug` · `security` ·
`concurrency` · `performance` · `style` · `complexity` ·
`documentation` · `portability` · `modernization`. Every `Rule`
declares both severity AND category at registration.

**Migration of the 42 existing rules:**

| Old | → | New | Count |
|-----|---|-----|-------|
| `FATAL` | → | `ERROR` | 5 |
| `STANDARD` (most) | → | `WARNING` | 19 |
| `STANDARD` (data-destruction) | → | `ERROR` | 1 (M-XINDX-024 KILL ^GBL) |
| `STANDARD` (style-leaning) | → | `STYLE` | 7 |
| `STANDARD` (VA-banner / patch) | → | `INFO` | 3 |
| `WARNING` (auto-fix hygiene) | → | `STYLE` | 4 |
| `WARNING` (likely bug) | → | `WARNING` | 4 |
| `INFO` | → | `INFO` | 1 |

**Total: 6 ERROR · 23 WARNING · 11 STYLE · 4 INFO** (note: M-XINDX-024
was promoted from STANDARD to ERROR for stronger CI signal on
catastrophic data loss).

**LSP severity mapping** is now semantically aligned: STYLE → `Hint`
matches LSP's "subtle suggestion / refactor opportunity" convention,
which is exactly what auto-fixable style rules are.

The old summary line `0F 1S 2W 3I` becomes `0E 1W 2S 3I`. JSON
severity values are now `"error"` / `"warning"` / `"style"` / `"info"`.
Config `[lint.severity]` overrides accept the new names.

### 9.4 Engine targeting — RESOLVED

**Decision:** add `[lint] target_engine` config + `--target-engine`
CLI flag. Default `"any"` (no engine filter, fully portable); named
engines `"yottadb"` and `"iris"` unlock engine-aware rules as they
ship.

**Shipped:**
- `Config.lint_target_engine: str | None` field, parsed from
  `[lint] target_engine` in `.m-cli.toml`. Validates against
  `KNOWN_ENGINES = ("any", "yottadb", "iris")`; unknown values raise
  `ValueError` with the list of accepted names.
- `m lint --target-engine {any,yottadb,iris}` — argparse choices flag.
  CLI wins over config; config wins over the default.
- `_resolve_target_engine(args, config)` helper in `m_cli.lint.cli`
  with the resolution-order tests.
- The summary line includes the target engine when not `"any"`:
  `... (--rules=default, --target-engine=yottadb)`.

The plumbing for rules to *consume* the target engine (via a
`needs_engine` flag on `Rule`, parallel to today's `needs_workspace`)
is deferred to the first engine-aware rule's PR — that way the
infrastructure is testable end-to-end at the moment it ships, not
sitting unused.

---

*The four resolutions above unblock the M-MOD-NN rule rollout. The
per-rule audit (§4), the top-5 language survey (§5), and the
rank-ordered greenfield list (§7) remain the design inputs for that
work; the implementation roadmap (§8) is otherwise unchanged.*
