---
created: 2026-05-06
last_modified: 2026-05-10
revisions: 2
doc_type: [DESIGN, PROPOSAL]
---

# Linter Profiles Guide

**Status:** design / review artifact. **Drafted 2026-05-06**, rewritten same day after the realization that the right organizing axis for SAC rules is *which gatekeeper enforces them*, not *which era they came from*. This doc proposes splitting today's `sac` profile into four mechanism-grounded profiles and reorganizing tags accordingly.

For usage / how-to, see [`m-linting-user-guide.md`](m-linting-user-guide.md). This doc is the design rationale + the tier proposal — the user guide gets updated *after* this lands.

---

## 1. The framing

A routine that ships into VistA passes through four real gatekeepers, in order. Each rejects code for different reasons:

| # | Gatekeeper | What it enforces | What happens on violation |
|---|---|---|---|
| 1 | **KIDS build / install** (`^XPDI`, `^XPDIT`) | Routine name = first label, 2nd-line patch marker, routine size, line length, `;;` data-line shape | Install fails, KIDS rejects, or the routine silently corrupts on reload |
| 2 | **VA Kernel runtime** (`^XU*`, `^%ZIS`, TASKMAN) | Use `G ^XUSCLEAN` for HALT, `^%ZIS` for OPEN, TASKMAN for JOB, `%`-global namespace, SSVN restrictions | Runtime: device lock-up, no cleanup, security flag, audit failure |
| 3 | **M engine semantics** | LOCK/READ timeouts, exclusive-Kill scoping, no BREAK in prod, non-incremental LOCK | Code runs, behaves badly: deadlocks, hangs, scope leaks, debugger drops |
| 4 | **VA cultural reviewer** | Uppercase commands, standard abbreviations, lowercase locals, no extended refs, label naming | PR rejected, nothing technically broken — taste-driven |

Today's `--rules=sac` profile is a **mash-up of all four**. That's the underlying problem this doc resolves. `M-XINDX-019` (line > 245) and `M-XINDX-047` (lowercase commands) are tagged the same way but fail at totally different layers — one is KIDS install machinery, the other is reviewer taste. Splitting them lets each profile mean something testable.

This supersedes the earlier era-based tier proposal (evergreen/legacy/counterproductive). The era axis was a less precise version of the gatekeeper axis: every "hardware-legacy" rule was really a KIDS-build constraint, every "counterproductive" rule was really sac-style or vista-Kernel coupling. Mechanism is sharper than judgment.

---

## 2. Decision tree — which profile do I want?

```
Are you packaging M code as a KIDS distribution for VistA install?
├── YES → kids-build  (mechanical install constraints)
│         AND vista     (if your code calls into VA Kernel)
│         AND safety    (engine-neutral hazards)
│         AND sac-style (only if your reviewer enforces VA conventions)
│         convenience: --rules=sac is the meta-profile expanding to all four
└── NO  → Are you maintaining VistA-derived code outside VistA itself?
         (CPRS, RPMS, DHP, federal contractors using KIDS-style packaging)
         ├── YES → kids-build + vista + safety
         │         (drop sac-style; you don't owe the VA reviewer)
         └── NO  → You're greenfield M (YottaDB, IRIS, m-stdlib, hobby).
                 ├── Daily editing  → default          (curated M-MOD)
                 ├── Strict review  → modern           (full M-MOD)
                 ├── Concurrency / lifecycle floor
                 │   without VA culture
                 │                  → default + safety (NEW; PROPOSED)
                 └── Distributed YDB cluster
                     using extended refs
                                    → default + safety; do NOT add sac-style
                                      (sac-style bans extended refs by design)
```

The `safety` profile is the genuinely new affordance for non-VA shops. Today they have nothing between `default` (M-MOD only, no concurrency rules) and `sac` (full VA submission gate including hostile rules).

---

## 3. Profile inventory (proposed)

| Profile | Count | Audience | Rationale |
|---|---:|---|---|
| `default` | 26 | Daily editing on greenfield M | Curated M-MOD subset minus the 4 pedantic style rules. ~3 findings/routine on 4K non-VA corpus. **Unchanged.** |
| `modern` | 30 | Strict review on greenfield M | Full M-MOD set. **Unchanged.** |
| `pedantic` | 4 | Style-policing isolate | The 4 high-noise pedantic rules. **Unchanged.** |
| `xindex` | 34 | Engine-neutral XINDEX | Engine-neutral subset of `^XINDEX`. **Unchanged in membership;** internal tag re-org. |
| **`kids-build`** | **~7** | **Anyone packaging for VistA install** | **NEW.** Rules KIDS mechanically enforces at build/install time. Violation = install fails. |
| `vista` | ~6 | VA-Kernel-runtime environments | **Unchanged in spirit;** clarified to mean "VA Kernel runtime coupling," not "VA-flavoured generally." |
| **`safety`** | **~11** | **Any M dev who wants concurrency / lifecycle floor** | **NEW.** Engine-neutral hazards: LOCK/READ timeouts, Kill/NEW scope, BREAK ban, hygiene. Deserves to exist independent of VA. |
| **`sac-style`** | **~8** | **VA submission to satisfy reviewer culture** | **NEW.** Pure VA cultural conventions — uppercase commands, abbreviations, no extended refs. KIDS doesn't care; runtime doesn't care; reviewer cares. |
| `sac` | 31 | Convenience meta-profile | **REFRAMED.** Resolves to `kids-build,vista,safety,sac-style`. Single-flag UX for VA submission preserved; the underlying sets are now individually addressable. |
| `all` | 77 | Diagnostic / triage only | Every registered rule. **Unchanged.** Do not use as a working configuration. |

**Net new code:** 3 new profiles (`kids-build`, `safety`, `sac-style`), 1 reframed (`sac` becomes a meta). 31 SAC-tagged rules get redistributed across the four buckets via tags.

---

## 4. Tag taxonomy

| Axis | Values | Meaning | Status |
|---|---|---|---|
| Provenance | `xindex`, `modern` | Where the rule came from | Existing |
| **Gatekeeper** | **`kids-build`, `vista`, `safety`, `sac-style`** | **Which real-world gatekeeper enforces this rule** | **NEW** (replaces / subsumes the existing single `sac` tag for the 31 SAC-tagged rules) |
| Engine | (via `--target-engine`) | YDB-only / IRIS-only / ANSI-only | Existing |

The `sac` tag becomes derived: `--rules=sac` resolves to "any rule with a gatekeeper tag in `{kids-build, vista, safety, sac-style}`." That preserves backward compatibility (single-flag VA submission still works) while making the structure honest underneath.

The dropped `sac-era` axis from the prior draft (evergreen/legacy/counterproductive) is **not** added. Mechanism > judgment.

---

## 5. Rule classification (the redline target)

31 rules carry the `sac` tag today. Below is the proposed gatekeeper assignment, with one-sentence rationale per rule. **Treat this as a redline draft.** The `?` column flags ones I'm least sure about.

### 5.1 `kids-build` — KIDS install/build machinery (~7 rules)

These rules are **technical install gates**. Violating them means KIDS distribution fails, the routine won't reload, or `^XPD*` rejects the package. Not stylistic — mechanically enforced.

| Rule | Title | Why KIDS cares | ? |
|---|---|---|:-:|
| `M-XINDX-017` | First-line label NOT routine name | KIDS expects routine name as the first label of `ROUTINE.m` for install / re-export. ZL/ZS reload fails otherwise. |  |
| `M-XINDX-019` | Line longer than 245 bytes | M routine line buffer + KIDS `;;` export envelope have hard limits. Long lines truncate or wrap on install. |  |
| `M-XINDX-035` | Routine exceeds SACC max 20000 bytes | DSM/Cache routine table fixed-slot constraint that KIDS validates. (YottaDB lifts this, but VistA's KIDS still enforces.) |  |
| `M-XINDX-058` | Routine code exceeds SACC max 15000 bytes | Same family — KIDS code-section size constraint. |  |
| `M-XINDX-044` | 2nd line of routine violates the SAC | KIDS install reads the patch marker from line 2; non-conforming layout breaks build envelope. |  |
| `M-XINDX-056` | Patch number missing from 2nd line | KIDS uses this for upgrade tracking and patch-stack ordering. |  |
| `M-XINDX-062` | First line of routine violates the SAC | KIDS expects routine name as the first executable token; violations break header parsing. |  |

### 5.2 `vista` — VA Kernel runtime coupling (~6 rules, all already in the `vista` profile)

Code that calls into the VA Kernel runtime. Inert outside that environment — the rules don't apply if you don't have `^XU*` and `^%ZIS` available.

| Rule | Title | Why Kernel cares |
|---|---|---|
| `M-XINDX-029` | CLOSE should be invoked through `D ^%ZISC` | `^%ZIS` is the VA device handler; bypassing it leaks device state. |
| `M-XINDX-032` | HALT should be invoked through `G ^XUSCLEAN` | XUSCLEAN runs Kernel cleanup (locks, signons, audit). Bare HALT skips it. |
| `M-XINDX-034` | OPEN should be invoked through `^%ZIS` | Same — Kernel device contract. |
| `M-XINDX-036` | Should use TASKMAN instead of JOB | TASKMAN is the VA job scheduler; bare JOB doesn't get tracked. |
| `M-XINDX-045` | Set to a `%`-global | `%`-globals are Kernel-namespace; writes need Kernel privilege checks. |
| `M-XINDX-054` | Access to SSVN's or `$SYSTEM` restricted to Kernel | Security-audit boundary. |

### 5.3 `safety` — engine-neutral concurrency / lifecycle / hygiene (~11 rules)

Real defects in any M dialect. These are best-practice rules that happen to be in SAC because the SAC authors knew M's hazards. They deserve to exist independent of VA — and that's the whole point of pulling them out into a profile non-VA shops can credibly run.

| Rule | Title | Hazard | ? |
|---|---|---|:-:|
| `M-XINDX-013` | Trailing whitespace | Hygiene; auto-fixable. |  |
| `M-XINDX-022` | Exclusive Kill (`K (X,Y)`) | Clobbers caller's locals. |  |
| `M-XINDX-023` | Unargumented Kill (`K`) | Wipes the entire local symbol table. |  |
| `M-XINDX-024` | Kill of unsubscripted global | Drops the entire global tree. |  |
| `M-XINDX-025` | BREAK in code | Drops to debugger in production. |  |
| `M-XINDX-026` | Exclusive / Unargumented NEW | Same scope hazard as exclusive Kill. |  |
| `M-XINDX-033` | READ without timeout | Process hangs forever on stdin. |  |
| `M-XINDX-060` | LOCK without timeout | Deadlock surface. |  |
| `M-XINDX-061` | Non-incremental LOCK | Releases held locks before re-acquiring; race window. |  |
| `M-XINDX-020` | VIEW command | Engine-internal state mutation; rarely correct in app code. | ? |
| `M-XINDX-027` | `$VIEW` function | Same — reading internal state, behaviour engine-defined. | ? |

The `?` on `-020`/`-027` flags rules where the placement is defensible but pending engine-targeting refinement (decision logged in §6.1). YottaDB and IRIS both expose documented `VIEW`/`$VIEW` operations that are legitimate. **Decision: keep in `safety`**; address the false-positive rate via engine-targeting allowlists in a follow-up, not by demotion.

### 5.4 `sac-style` — VA cultural conventions, no other gatekeeper enforces (~8 rules)

These rules will produce *wrong* findings on non-VA modern M code. They stay in the `sac` meta-profile because VA submission requires them, but `sac-style` is the honest name — pure reviewer-culture preferences with no underlying technical bite.

| Rule | Title | Why it's culture, not safety |
|---|---|---|
| `M-XINDX-047` | Lowercase command(s) used in line | M is case-insensitive on commands; `set` and `SET` parse identically. SAC §3.3 prefers uppercase, that's all. |
| `M-XINDX-057` | Lower/mixed case in local variable name | M is case-*sensitive* on variables. Forcing case can silently break code that uses `X` and `x` as distinct. Worst rule of the bunch — not just culture, actively unsafe. |
| `M-XINDX-050` | Extended reference (`^\|"node"\|G(…)`) | The **idiomatic** YottaDB cross-node access pattern. SAC bans it for VA portability; it's correct everywhere else. |
| `M-XINDX-030` | LABEL+OFFSET syntax | SAC bans for fragility under `$TEXT`-relative addressing churn. Legitimately useful in introspection / debugging. |
| `M-XINDX-002` | Non-standard `Z*` command | `Z*` is the **vendor-extension namespace** by ANSI design. YottaDB ships `ZBREAK`, `ZSTEP`, `ZWRITE`. |
| `M-XINDX-028` | Non-standard `$Z*` special variable | `$ZHOROLOG`, `$ZJOB` are documented YDB / IRIS extensions. |
| `M-XINDX-031` | Non-standard `$Z*` function | `$ZSEARCH`, `$ZFILE` are real engine features. |
| `M-XINDX-041` | Star or pound READ used (`R *X`, `R #`) | `R *X` is the standard ANSI single-keystroke read. SAC bans for portability; legitimate elsewhere. |

---

## 6. Design decisions

The 6 open questions from the prior draft are resolved as follows. Each entry records the **decision**, the **rationale**, and the **practical impact** for users and implementers — so future review can re-litigate any one of these without losing the original reasoning. Decisions ratified 2026-05-06.

### 6.1 `M-XINDX-020` (VIEW) and `M-XINDX-027` ($VIEW) stay in `safety`

**Decision.** Both rules tagged `gatekeeper=safety`.

**Rationale.** The *typical* use of VIEW / $VIEW is engine-internal-state mutation, which is nearly always wrong in app code — that's a real safety concern, not a stylistic one. The legitimate cases (YottaDB process introspection, IRIS transaction-level peek) are real but narrow. Demoting the rule to `sac-style` would mean non-VA shops never see the warning, which loses the typical-case value. Better to keep it in `safety` and refine the false-positive rate later via engine-targeting.

**Practical impact.** Non-VA YDB/IRIS shops running `--rules=safety` get findings on legitimate VIEW/$VIEW operations until engine-targeting suppression lands. Workarounds available today: per-rule disable via `[lint.disable]` in `.m-cli.toml`, or inline `;m-cli: disable=M-XINDX-020`.

**Future work (not blocking this proposal).** Add an `engine_view_allowed` allowlist to the rule, gated on the existing `target_engine` config knob. Tracked separately from the gatekeeper-split implementation.

### 6.2 `M-XINDX-019` (line > 245) stays hardcoded; configurable line-length is a separate rule

**Decision.** `M-XINDX-019` keeps its 245-byte hardcoded threshold. It is **not** exposed as configurable in `[lint.thresholds]`.

**Rationale.** KIDS enforces 245 mechanically; making it configurable would suggest the user has a choice. They don't — KIDS will reject the routine on install. A configurable "modern line length" with a 100–200 char default is a different rule serving a different purpose (reviewability, not install gate); it belongs in the M-MOD modernization track with its own threshold key.

**Practical impact.** `kids-build` is a hard gate with zero knobs. Modern shops who want a soft line-length warning need a future `M-MOD-NN` rule (not yet shipped). Today they can either run `--rules=safety,kids-build` and accept the 245 limit, or skip line-length checking entirely.

**Future work (not blocking this proposal).** New `M-MOD-NN` "modern line length" rule with configurable threshold (default ~100), tagged `style` not `gatekeeper`. Separate work item.

### 6.3 Profile and tag value are both named `safety`

**Decision.** Profile name: `safety`. Tag value: `safety`. Not `m-safety` or `engine-safety`.

**Rationale.** Short and clear. No collision with the existing namespace (other tags are short — `xindex`, `vista`, `modern`). Anchoring the name to the user-visible concept is more useful than disambiguating with prefixes that nobody would type.

**Practical impact.** None — pure naming. CLI: `--rules=safety`. Config: `[lint] rules = "default,safety"`. Tag in `rules.py`: `tags=("xindex", "safety")`. The name is testable and stable.

### 6.4 `default` stays strictly M-MOD; `default + safety` is the documented greenfield combo

**Decision.** `safety` rules are **not** pulled into `default`. `default` membership unchanged from today (26 curated M-MOD rules).

**Rationale.** Provenance discipline. `default` has been "the curated M-MOD modernization track" since the profile split shipped; pulling XINDEX-derived rules in would muddle the meaning. Users reading `--list-profiles` would have to ask "wait, why are XINDEX rules in `default` now?" Better: keep `default` provenance-clean and document `default + safety` as the recommended invocation for non-VA shops.

**Practical impact.** Greenfield users who want concurrency / lifecycle floor must opt in:

```bash
m lint --rules=default,safety Routines/
```

Or alias once in `.m-cli.toml`:

```toml
[lint]
rules = "default,safety"
```

The user guide (`m-linting-user-guide.md`) gets updated to document this combo as the recommended baseline for non-VA shops. Single-flag UX is a config alias, not a profile membership change.

### 6.5 `M-XINDX-013` (trim trailing whitespace) is tagged `safety`

**Decision.** `M-XINDX-013` gets `gatekeeper=safety` despite being hygiene rather than concurrency.

**Rationale.** The auto-fix already exists (`trim-trailing-whitespace`), the rule is universal, and grouping it with the other auto-fixable / engine-neutral rules in `safety` is more useful than carving out a separate one-rule "hygiene" gatekeeper. Stretch fit on the name, but the practical grouping is right.

**Practical impact.** `--rules=safety` includes trailing-whitespace cleanup, so the recommended `default + safety` combo gives greenfield users the trim-on-save story automatically. `trim-trailing-whitespace` also remains in `canonical_rules()` for `m fmt --rules=canonical` — the fmt auto-fix path is unchanged, only the lint-rule grouping is sharpened.

### 6.6 `sac` profile membership unchanged; gatekeeper tags layer beneath it

**Decision.** `--rules=sac` continues to resolve to exactly today's 31 rules. The four new profiles (`kids-build`, `vista`, `safety`, `sac-style`) are additive overlays, each picking up the subset of those 31 rules carrying the matching gatekeeper tag.

**Rationale.** Backward compatibility for VA users. Anyone running `--rules=sac` for VA submission today should see no behaviour change. The structural improvement is honest categorization underneath; the single-flag VA-submission UX stays intact.

**Practical impact.**

- `--rules=sac` — unchanged 31 rules, behaviour identical to today.
- `--rules=kids-build,vista,safety,sac-style` — equivalent invocation; the union of the four gatekeeper subsets equals today's `sac` set, by construction.
- `--rules=sac` is preserved as a registered profile (not a derived alias) so `--list-profiles` continues to surface it as a top-level concept, and the existing `tests/test_lint_profiles.py::TestSacClassification` keeps pinning the 31-rule membership.

**Test pin (added in implementation).** `tests/test_lint_profiles.py::test_sac_equals_union_of_gatekeepers` will assert `select_rules("sac") == select_rules("kids-build,vista,safety,sac-style")` so the equivalence can't drift.

---

## 7. Implementation sketch (post-signoff)

1. **`src/m_cli/lint/rules.py`** — extend each of the 31 SAC-tagged rules with the appropriate gatekeeper tag (`kids-build`, `vista`, `safety`, or `sac-style`). Existing `sac` and `xindex` tags retained. ~31 line edits.
2. **`src/m_cli/lint/profiles.py`** — register `kids-build`, `safety`, `sac-style` profiles, each selecting rules by gatekeeper tag. `vista` profile membership unchanged but its docstring sharpened to "VA Kernel runtime coupling." `sac` profile unchanged in membership. ~30 lines.
3. **`tests/test_lint_profiles.py`** — add `TestGatekeeperClassification` pinning each rule's gatekeeper. Add `test_sac_equals_union_of_gatekeepers` (per §6.6) asserting `select_rules("sac") == select_rules("kids-build,vista,safety,sac-style")`. Round-trip tests that each new profile returns its expected rule set. ~80 lines.
4. **`docs/m-linting-user-guide.md`** §2 — append the three new profiles to the table; add a "VA submission" subsection documenting `kids-build`/`vista`/`sac-style` composition; add a "non-VA greenfield baseline" subsection documenting `--rules=default,safety` per §6.4.
5. **`CLAUDE.md`** — bump profile count from 7 to 10 in the project descriptor; add the gatekeeper tag axis to the linter conventions section.
6. **`README.md`** (m-cli) — one-line update to the profile table if it appears.

No fmt-rule changes. No CLI flag changes. No LSP changes. Backward compatible — `--rules=sac` membership unchanged, VA users see no behaviour difference.

ETA: ~2 hours TDD-paced.

---

## 8. Cross-references

- [`docs/m-linting-user-guide.md`](m-linting-user-guide.md) — how-to / usage guide
- [`docs/m-linting-implementation-plan.md`](m-linting-implementation-plan.md) — Phase 1A (vista profile split), broader rule-organization roadmap
- [`docs/m-linting-survey.md`](m-linting-survey.md) §7 — the M-MOD-NN greenfield rule list
- [`tests/test_lint_profiles.py`](../tests/test_lint_profiles.py) — `TestSacClassification` is the existing pin; the proposed `TestGatekeeperClassification` will be its sibling
- [`src/m_cli/lint/rules.py`](../src/m_cli/lint/rules.py) module docstring — current SAC tag policy rationale (will be rewritten to describe the gatekeeper axis)
