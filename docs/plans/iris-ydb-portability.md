---
created: 2026-04-30
last_modified: 2026-05-10
revisions: 2
doc_type: [PLAN, RESEARCH]
---

# IRIS ↔ YottaDB CLI Comparison — Portability Plan for `m-cli`

> **Purpose.** A function-by-function comparison of the command-line surface
> exposed by **InterSystems IRIS** and **YottaDB** (the two M implementations
> `m-cli` would realistically target), with a concrete plan for refactoring
> `m-cli` so every subcommand can dispatch to either engine.
>
> **Audience.** `m-cli` maintainers planning the engine-adapter refactor.
>
> **Last updated.** 2026-04-29.
>
> **Honest caveats.** YottaDB is open source and the author can confirm
> behaviors against a local install. IRIS is commercial and version-gated —
> command names below reflect IRIS 2024.x; some IRIS-side defaults may have
> shifted in newer releases, and a small number of items (marked ⚠) should be
> verified against a live IRIS instance before being relied on for code.

---

## 1. Why this is non-trivial — the central architectural difference

The single biggest portability hurdle is not in any individual command — it's
in **where routines live**.

| Aspect | YottaDB | IRIS |
|---|---|---|
| **Routine source on disk** | `.m` files in directories listed by `$ydb_routines`. | Conventionally not on disk. Source lives **inside the database**, in the routine database for each namespace, accessed via system tools. |
| **Filesystem-friendly workflow** | Native. `vim foo.m && ydb -run ^FOO`. | Requires explicit **import** (`do $SYSTEM.OBJ.Load("foo.mac")`) and **export** (`do $SYSTEM.OBJ.Export("FOO.mac")`). The VS Code ObjectScript extension automates this round-trip; without it, the user does it by hand. |
| **Compile model** | Lazy: first call to a routine compiles `.m` → `.o` in `$ydb_routines`. Or eager via `mumps -compile`. | Compiles on `Load+Compile`; output is stored in the routine database (`.obj`/`.int` representations are DB-internal). |
| **Source extension** | `.m` (universal). | `.mac` (macro source — what humans write), `.int` (post-macro intermediate), `.inc` (include), `.cls` (ObjectScript class). M routines in IRIS are `.mac`. |
| **What `m-cli` operates on today** | `.m` files, parsed with `tree-sitter-m`. | `.mac` files (after a small grammar/tokenizer relaxation — IRIS-specific syntax extensions are a separate workstream). |

**Implication for `m-cli`.** The source-level subcommands (`m fmt`, `m lint`,
`m doc`, much of `m lsp`) are largely engine-agnostic — they read files from
disk regardless of whether those files later end up in `$ydb_routines` or get
loaded into IRIS. The runtime subcommands (`m test`, `m coverage`,
`m profile`, `m debug`, future `m run` / `m build`) need **engine adapters**:
either pipe the source into the engine's expected form, or delegate the
operation to engine-specific primitives.

The `m-cli` codebase is already shaped well for this — the YDB-specific
helpers (`_ydb_path`, `_build_env`, `_derive_ydb_routines` in
[src/m_cli/test/runner.py](../src/m_cli/test/runner.py)) are confined to the
runner modules. An `IrisEngine` parallel implementation can sit alongside
without touching the source-level layer at all.

---

## 2. CLI binary inventory

The two ecosystems ship roughly comparable suites of binaries. This table
maps them to each other so you can see the rough analogues at a glance —
section §3 onward goes function-by-function.

| Concern | YottaDB binary | IRIS binary | Notes |
|---|---|---|---|
| Run / interactive M shell | `ydb` (alias `mumps`) | `iris session <inst>` / `iris terminal <inst>` | YDB's `ydb` with no args drops into Direct Mode; IRIS needs an instance name and namespace. |
| Compile a routine file | `mumps -compile foo.m` | (no equivalent — must `Load+Compile` from inside) | IRIS forces an in-process step. |
| Execute a routine | `ydb -run ^FOO` | `iris run <inst> args` / `iris session <inst> -U NS FOO` | IRIS variant goes through a session; routine must already be loaded into the namespace. |
| Database admin (extract/load/integ/backup/journal) | `mupip` (sub-verbed) | `iris merge`, `^DATABASE`, `^JOURNAL`, `^BACKUP`, `^DBREST`, plus Mgmt Portal | IRIS scatters these across in-process utilities and the Management Portal. |
| Lock-table inspection | `lke` (LOCK SHOW / CLEAR) | `^LOCKTAB` (in-process) | |
| Database structure repair | `dse` | `^REPAIR` (in-process) | Both are "be very careful" tools. |
| Global-directory editor | `gde` | (no equivalent — IRIS uses Mgmt Portal / `^DATABASE` for the namespace/DB mapping) | YDB's gde edits a `.gld` file mapping global names → database files. |
| Instance lifecycle | `mupip rundown`, OS init scripts | `iris start <inst>`, `iris stop <inst>`, `iris force <inst>`, `iris restart <inst>` | IRIS has the much friendlier first-class lifecycle CLI. |
| Instance discovery | (none — env vars define the instance) | `iris list`, `iris all`, `iris stat`, `iris qlist` | IRIS allows multiple named instances per host, hence the discovery commands. |
| Web admin | (none) | Management Portal (HTTPS, GUI) | Outside the CLI scope, but worth flagging because lots of admin happens there. |

**Takeaway.** YDB's CLI is a tight set of Unix-style tools (`ydb`, `mumps`,
`mupip`, `lke`, `dse`, `gde`); IRIS's CLI is the lifecycle wrapper (`iris`)
plus a large set of in-process utilities invoked as `^XXX` from a session. To
script the same operation across both, `m-cli` will mostly drive
**`ydb -run` for YDB** and **`iris session <inst> -U <ns>` piping a small
script for IRIS**.

---

## 3. SDLC capability comparison — function by function

Same row order as [language-cli-survey.md §1.1](language-cli-survey.md#11-universal-capability-ranking),
restricted to the rows that mean something for an M implementation. Each row
states the YDB primitive, the IRIS primitive, the portability verdict, and
how `m-cli` wraps them today (or could).

### 3.1 Source-level capabilities (engine-agnostic in principle)

These read files from disk; the engine doesn't enter the picture.

| Capability | YDB | IRIS | Portable? | Current `m-cli` |
|---|---|---|:---:|---|
| **Format** | n/a — reads `.m` files | n/a — reads `.mac` files | ✅ Trivially. Same code path; just allow `.mac` extension. | `m fmt` — reads `.m`. Add `.mac` to the discovery glob. |
| **Lint** | n/a — parser + rules | n/a — parser + rules | ✅ Trivially for the rules already implemented. ⚠ IRIS adds ObjectScript-specific syntax (preprocessor macros, embedded SQL, class methods inside `.mac`); 100% lint coverage on IRIS code requires extending `tree-sitter-m`. | `m lint` — same caveat. |
| **Doc generator** | parses `;;` doc comments | same — `;;` doc comments + `///` for class members | ✅ For routines. Class docs are an IRIS-only extension. | Not yet built. |
| **Project scaffolder** | `.m` + `.gld` template | `.mac` + `iris.script` import template | ⚠ Same scaffolder, two output skeletons. | Not yet built. |
| **Editor / LSP — diagnostics, formatting, hover, completion, code lens** | Reads files; engine not involved | Same | ✅ All Stage 1–4b features are file-only. | `m lsp` — fully engine-agnostic today. |
| **LSP — go-to-definition / references / workspace symbol** | Walks `.m` files in workspace | Walks `.mac` files in workspace | ✅ Just glob both extensions. | `m lsp` — file glob is the only change. |

### 3.2 Runtime capabilities (engine-specific)

These need an engine adapter.

| Capability | YDB primitive | IRIS primitive | Portable? | Current `m-cli` |
|---|---|---|:---:|---|
| **Test runner — whole suite** | `ydb -run ^SUITE` | `iris session <inst> -U <ns> SUITE` (after `do $SYSTEM.OBJ.Load("SUITE.mac","ck")`) | ⚠ Requires an import step on IRIS. Same TESTRUN protocol works on both — TESTRUN.m is portable M. | `m test` — YDB only. |
| **Test runner — single label** | `ydb -run %XCMD "do tCase^SUITE(.pass,.fail) ..."` | `iris session <inst> -U <ns> '%SYS.PROCESS' < script` ⚠ — feed the equivalent xcmd via stdin, or wrap in a temporary routine. | ⚠ Subtly different invocation; same logical pattern. | `m test FILE.m::tLabel` — YDB only. |
| **Coverage — per-line hit counts** | `view "TRACE":1:"^GBL":""` + `view "TRACE":0` | `^%MONLBL` (Line Monitor) — `do Start^%MONLBL` / `Stop^%MONLBL`; reads counts from `^MONITOR` global | ⚠ Different global names, different setup ritual, but both produce per-line execution counts indexed by routine + line. | `m coverage` — YDB-only via `view "TRACE"` into `^ycov`. |
| **Compile / build** | implicit on first call, or `mumps -compile foo.m` | `do $SYSTEM.OBJ.Load("foo.mac","ck")` (the "ck" flags = compile + keep source) | ⚠ Different ritual. IRIS surfaces compile errors via `$SYSTEM.OBJ.GetErrorText`. | `m build` not yet built. |
| **Run / execute** | `ydb -run ^FOO` | `iris run <inst>` or `iris session <inst> -U <ns> FOO` | ⚠ IRIS needs instance + namespace. | `m run` not yet built. |
| **Watch** | filesystem polling | filesystem polling — but on IRIS, save→trigger needs `do $SYSTEM.OBJ.Load` to re-import | ⚠ Affinity logic is the same; the action on change differs. | `m watch` — YDB-only behavior implicit. |
| **Profile** | `view "TRACE"` (same as coverage; weight per line) | `^%MONLBL` (same global; reports both counts and time-per-line) | ⚠ Both reuse the coverage primitive. | Not yet built. |
| **Debugger / DAP** | `ZBREAK label^routine`, `ZSTEP`, `ZSHOW` (engine-level) | `ZBREAK` works (compatible), plus `^%DEBUG` and the Studio debugger | ✅ At the language level. The DAP server design needs to wrap whichever engine is running. | Deferred. |
| **Benchmark** | `$ZH` for high-resolution time | `$ZH` works; IRIS also has `$ZHOROLOG`, `$NOW`, `$SYSTEM.SQL.Functions.NOW()` | ✅ Same primitive. | Not yet built. |

### 3.3 Database admin (out of scope for `m-cli`, but worth knowing)

`m-cli` is a developer-tool CLI, not a DBA CLI — it does not wrap backup,
journal, or integ today and shouldn't grow into one. Listed here for
completeness so the boundary is explicit.

| Concern | YDB | IRIS |
|---|---|---|
| Backup | `mupip backup` | `^BACKUP` / external + IRIS Online Backup |
| Restore | `mupip restore` | `^DBREST` |
| Integ check | `mupip integ` | `^DATABASE` Integrity Check |
| Journal | `mupip journal` (extract / show / recover / rollback) | `^JOURNAL` |
| Extract / load globals | `mupip extract` / `mupip load` | `^%GO` / `^%GI` (same names!) |
| Reorg | `mupip reorg` | `^DATABASE` Compact / Truncate |

The global extract format `^%GO`/`^%GI` is the same routine name on both
engines — a useful coincidence that makes data portable in many cases even
though the database files themselves are not interchangeable.

---

## 4. Storage and addressing model

Differences here only matter to `m-cli` if a future subcommand needs to read
or write globals directly. None do today; documenting in case a `m-cli admin`
ever appears.

| Concern | YDB | IRIS |
|---|---|---|
| Database file | One or more `.dat` files (B-tree per region) | One `IRIS.DAT` per database |
| Mapping global → file | Global directory (`.gld`), edited via `gde` | Namespace + global mapping, configured via Mgmt Portal or `^%NSP` |
| Workspace concept | Environment: `$ydb_dir`, `$ydb_gbldir`, `$ydb_routines` | Instance + namespace pair; `$ZNSPACE` |
| Multiple environments per host | One `$ydb_dir` at a time per shell | First-class — `iris list` shows them all; switch via `iris session <inst>` |
| Lock space | One per region | One per system (configurable) |

For `m-cli`: the practical surface is just "what env vars does the engine
need to find code and globals?". That's exactly what `_build_env` already
encapsulates for YDB — the IRIS adapter parallels it with `IRIS_INSTANCE`
and namespace.

---

## 5. Tracing and coverage primitives — closer look

This is the single most engine-specific area `m-cli` already touches, so it
gets its own subsection.

### YDB — `view "TRACE"`

```m
view "TRACE":1:"^ycov":""    ; enable, write counts into ^ycov
do ^SUITE
view "TRACE":0:"^ycov":""    ; disable
```

After execution, `^ycov(routine, label, offset_from_label) = count`. The
`m_cli.coverage.runner` module decodes the third subscript: offset N from
label `lbl` maps to absolute line `decl_line(lbl) + N`, giving precise
per-line coverage. See
[src/m_cli/coverage/runner.py:185–360](../src/m_cli/coverage/runner.py).

### IRIS — `^%MONLBL`

```m
do Start^%MONLBL("ROUTINE,*")    ; start; "*" or wildcards select routines
do ^SUITE
do Stop^%MONLBL
do Display^%MONLBL                ; or read ^MONITOR globals directly
```

`^%MONLBL` (Line-by-line Monitor) records, per line:

- execution count
- total time spent on the line
- (optionally) globals references / commands executed

Output is keyed by `^MONITOR(routine, line_number)` — already absolute
(no label-relative offset to decode). Slightly **simpler** to consume than
YDB's trace, at the cost of needing to start the monitor as a system service
(it's a measured-instrumented mode, not a free flag).

### Implication for `m-cli`

The existing `m_cli.coverage.runner` does two things: (a) compose a script
that toggles the trace global, runs the suite, and reads back counts; (b)
reconcile YDB's label-relative offsets with absolute line numbers. The IRIS
adapter shrinks (a) to a different script and **eliminates** (b) entirely.
Refactoring opportunity: factor the offset reconciliation into a
YDB-specific decoder so the IRIS adapter can use a near-identical pipeline
without that step.

The same primitives back `m profile` (not built yet) — both engines report
time-per-line, just under different APIs. Reuse the coverage scaffolding.

---

## 6. Test runner — protocol-level comparison

Both engines are M implementations and run `TESTRUN.m` unchanged. The
**protocol** (TESTRUN's stdout dialect — `  PASS  desc` / `  FAIL  desc` /
`Results: N tests P passed F failed`) is identical because it's pure M.
What differs is the **invocation**.

### YDB invocation today

```bash
ydb -run ^SUITE                                     # whole suite
ydb -run %XCMD "new pass,fail … do tCase^SUITE(.pass,.fail) … do report^TESTRUN"   # single label
```

Env: `$ydb_routines` set to suite-dir + sibling `routines/`. See
`m_cli.test.runner._build_env` and `_derive_ydb_routines`.

### IRIS invocation (proposed)

```bash
# 1. Import the suite into the namespace once per file change
iris session IRIS -U USER <<EOF
do \$SYSTEM.OBJ.Load("$PWD/SUITE.mac","ck")
EOF

# 2. Run the suite
iris session IRIS -U USER SUITE

# 3. Single-label variant — same pattern but feed the xcmd via stdin
iris session IRIS -U USER <<EOF
new pass,fail
do tCase^SUITE(.pass,.fail)
do report^TESTRUN
EOF
```

A cleaner long-term variant uses `iris session ... -B '<routine call>'`
where supported. ⚠ Verify against the target IRIS version — the
`-B`/`-U`/`-N` flag set has shifted across releases.

### What to abstract

The runner needs three engine-specific operations. Everything else stays in
shared code:

```python
class Engine(Protocol):
    def ensure_loaded(self, suite_path: Path) -> None: ...
    def run_suite(self, suite_name: str) -> tuple[str, int]: ...           # stdout, exit_code
    def run_xcmd(self, xcmd: str, ydb_routines_like: str) -> tuple[str, int]: ...
```

`YdbEngine.ensure_loaded` is a no-op (YDB compiles on first call).
`IrisEngine.ensure_loaded` runs `do $SYSTEM.OBJ.Load(...,"ck")`. Everything
above this — discovery, single-label selection, TESTRUN parsing, text/TAP/JSON
formatting — is already engine-agnostic in the codebase.

---

## 7. Engine adapter design recommendation

Concrete proposal for refactoring `m-cli` to support IRIS without disturbing
the YDB path. Six points; each maps to a specific module.

### 7.1 Introduce an `engine` package

```
src/m_cli/engine/
├── __init__.py        # detect_engine(), get_engine()
├── base.py            # Engine ABC
├── ydb.py             # YdbEngine — moves _ydb_path, _build_env, _derive_ydb_routines here
└── iris.py            # IrisEngine — new
```

The ABC declares:

```python
class Engine(ABC):
    name: str                                 # "ydb" or "iris"
    @abstractmethod
    def build_env(self, source_root: Path) -> dict[str, str]: ...
    @abstractmethod
    def ensure_loaded(self, sources: list[Path]) -> None: ...
    @abstractmethod
    def run_routine(self, routine: str, args: list[str] = []) -> tuple[str, int]: ...
    @abstractmethod
    def run_xcmd(self, xcmd: str) -> tuple[str, int]: ...
    @abstractmethod
    def trace_start(self, target_global: str) -> str: ...   # returns prologue M code
    @abstractmethod
    def trace_stop(self, target_global: str) -> str: ...    # returns epilogue M code
    @abstractmethod
    def trace_decode(self, raw: dict) -> dict[tuple[str, int], int]: ...   # → {(routine, abs_line): count}
```

### 7.2 Engine detection

`detect_engine()` consults, in order:

1. `--engine=ydb|iris` CLI flag.
2. `[engine] kind = "ydb"` in `.m-cli.toml` (extends the existing
   [Phase A config](../CLAUDE.md#project-configuration-m-clitoml--toolm-cli)).
3. `$M_ENGINE` environment variable.
4. Heuristics: `$ydb_dist` set → ydb; `$ISC_PACKAGE_INSTALLDIR` set or
   `iris` on `$PATH` → iris.
5. Fall back to ydb (preserves current behavior).

### 7.3 Move the YDB-specific logic into `engine/ydb.py`

`m_cli.test.runner._ydb_path`, `_build_env`, `_derive_ydb_routines` move
unchanged. Their callers go through `get_engine().build_env(...)` etc. The
runner module shrinks to engine-agnostic discovery + invocation +
TESTRUN-parse + formatting.

### 7.4 IRIS-specific shape

`IrisEngine.build_env` populates `IRIS_HOST_TEMPDIR` (where `Load` looks for
import files) and chooses an instance via `--instance` CLI flag or
`[engine.iris] instance = "IRIS"` in config. Default namespace `USER`,
overridable.

`IrisEngine.run_routine` shells out:

```bash
iris session $instance -U $namespace $routine
```

`IrisEngine.run_xcmd` writes a temp `.mac` file and runs it, OR pipes
commands via `iris session $instance -U $namespace <<EOF ... EOF` (see
§6 — pick one based on which is more deterministic across IRIS versions).

`IrisEngine.ensure_loaded(sources)` emits:

```m
for path in sources:
    do $SYSTEM.OBJ.Load("$path","ck")
```

`IrisEngine.trace_start/stop` wrap `^%MONLBL`. `trace_decode` reads the
`^MONITOR` global (no offset reconciliation needed).

### 7.5 Source-level subcommands stay engine-agnostic

`m fmt`, `m lint`, `m lsp`, future `m doc`, `m new`, `m fix` need exactly
one change: extend the file glob from `*.m` to `*.{m,mac}`. The parser
config and rules don't change — `tree-sitter-m`'s grammar accepts `.mac`
content modulo IRIS-specific extensions, which are a separate workstream.

### 7.6 Tests

Add a marker-based skip: `pytest.mark.requires_ydb` and
`pytest.mark.requires_iris`. The existing test suite stays YDB-only by
default; an IRIS-marked subset runs only when `M_ENGINE=iris` and an IRIS
container / instance is reachable. Don't gate the main test suite on IRIS
availability.

---

## 8. Subcommand-by-subcommand portability matrix

Summary table for the m-cli maintainer's perspective. "Effort" is the
incremental work to add IRIS support beyond the engine-adapter scaffolding.

| Subcommand | Engine-agnostic? | What needs IRIS work | Effort |
|---|:---:|---|:---:|
| `m fmt` | ✅ | Add `.mac` to file glob. | XS |
| `m lint` | ✅ | Add `.mac` glob. ⚠ IRIS-specific syntax (preprocessor, embedded SQL, classes) needs grammar extensions before lint coverage is complete. | S–M |
| `m lsp` | ✅ | Same as `m lint` for the file watch. | XS |
| `m test` | ❌ | `IrisEngine.ensure_loaded` + `run_routine` + `run_xcmd`. Verify TESTRUN.m runs unchanged on IRIS. | S |
| `m coverage` | ❌ | Wrap `^%MONLBL`. Drop the offset-reconciliation step (IRIS reports absolute lines). | M |
| `m watch` | ⚠ | Trigger an IRIS `Load+Compile` on save before invoking the test path; otherwise IRIS runs stale source. | XS |
| `m new` (planned) | ✅ | Two skeleton variants — pick at scaffold time based on `[engine]`. | XS |
| `m doc` (planned) | ✅ | Source-level — engine-agnostic. | (none) |
| `m doctor` (planned) | ❌ | Detects both engines; reports the active one and what's missing. | XS |
| `m run` (planned) | ❌ | Thin wrapper over `Engine.run_routine`. | XS |
| `m build` (planned) | ❌ | Wraps `mumps -compile` (YDB) vs `do $SYSTEM.OBJ.Load(...,"ck")` (IRIS). | S |
| `m profile` (planned) | ❌ | Reuses coverage trace plumbing; engine difference identical to coverage. | (subsumed by `m coverage` adapter) |
| `m bench` (planned) | ⚠ | Same invocation as `m test` after `ensure_loaded`. | XS once test runner is engine-aware. |
| `m fix` (planned) | ✅ | Source-level. | (none) |
| `m debug` (planned) | ❌ | DAP server has to know which engine's debug primitives to talk to. ZBREAK is the common substrate. | absorbed into the m-debug project scope. |
| `m ci init` (planned) | ✅ | Generated workflow YAML can target either engine via env var. | XS |

**Reading the matrix.** Six of fifteen subcommands are pure source-level
work and need only the file-glob extension. Five need a thin engine-adapter
call. Only three (`m coverage`, `m build`, `m debug`) carry meaningful new
engine-specific code — and `m debug` is already its own project.

---

## 9. Implementation roadmap for IRIS support

Phased plan. Sequenced so each phase delivers something useful and the next
phase can be paused or scope-cut without leaving the codebase in an
intermediate state.

### Phase I-0 — Engine scaffolding (1 week)

- Introduce `src/m_cli/engine/{base,ydb,iris}.py`.
- Move YDB helpers into `engine/ydb.py` with no behavior change.
- Add `--engine` flag, `[engine]` config block, `detect_engine()`.
- All existing tests still pass; a new `tests/test_engine_detection.py`
  pins the detection rules.

**Exit:** zero feature change for YDB users; the scaffolding is in place
for parallel IRIS work.

### Phase I-1 — Source-level IRIS support (1 week)

- Extend file globs in `m fmt`, `m lint`, `m lsp`, `m doc` (when built) to
  `*.{m,mac}`.
- Add `tests/fixtures/iris/` with a few `.mac` samples covering the M
  subset that current rules already handle.
- Document any IRIS-specific syntax that current `tree-sitter-m` grammar
  cannot yet parse — feeds the grammar-extension backlog.

**Exit:** `m fmt`, `m lint`, `m lsp` work on `.mac` files containing the
common M subset.

### Phase I-2 — IRIS test runner (1–2 weeks)

- Implement `IrisEngine.ensure_loaded`, `run_routine`, `run_xcmd`.
- Verify TESTRUN.m runs unchanged on IRIS.
- `m test` smokes against both engines via marker-based pytest skips.
- Document the `iris session` invocation that worked, including the IRIS
  version it was tested on.

**Exit:** `M_ENGINE=iris m test FILE.mac` works against an IRIS instance.

### Phase I-3 — IRIS coverage (2 weeks)

- Implement `IrisEngine.trace_start/stop/decode` over `^%MONLBL`.
- Refactor coverage runner to push the YDB offset-reconciliation into
  `YdbEngine.trace_decode`, leaving the runner skeleton engine-agnostic.
- Add IRIS smoke fixtures (small `.mac` suite, expected per-line counts).

**Exit:** `m coverage` produces matching lcov output on both engines for the
same input suite.

### Phase I-4 — Polish and parity (ongoing)

- Extend `m watch` to trigger IRIS `Load+Compile` on save.
- Wire IRIS into `m doctor` (Phase 3a from
  [language-cli-survey.md §6.2](language-cli-survey.md#62-phased-roadmap)).
- Track IRIS-specific syntax extensions as separate `tree-sitter-m` issues.

**Exit:** day-to-day IRIS development through `m-cli` is on par with YDB.

### Decision points

- **Test against IRIS Community Edition or full IRIS?** Community Edition is
  freely downloadable and adequate for runtime testing; pin the version in
  CI documentation. ⚠ Verify license terms allow CI usage before shipping a
  Dockerfile.
- **Bundle an IRIS Docker image in the dev environment?** Recommended for
  Phase I-2 onward. `intersystemsdc/iris-community:latest` is the usual
  starting point. Don't make it a hard dependency for the YDB-only path.
- **Caché support?** Caché is the IRIS predecessor; its CLI was `ccontrol`
  (preserved in IRIS as a legacy alias). If real demand appears, an
  `IrisEngine` subclass for Caché should be cheap. Not on the roadmap until
  asked for.

---

## 10. Open questions worth resolving before Phase I-2

These are flagged as ⚠ in earlier sections; collecting them here so they
don't get lost.

1. **`iris session` flag stability across versions.** `-U` (namespace) and
   `-B` (batch) have shifted across IRIS releases. Decide on a minimum
   supported IRIS version (suggest 2023.1+) and pin tests accordingly.

2. **Stdin-script vs temp-file invocation.** Two ways to feed an XCMD to
   IRIS; one is more deterministic on Windows hosts, the other on Linux.
   Pick one and document the limitation.

3. **`^%MONLBL` license / availability.** The Line Monitor is part of base
   IRIS but wrapping it requires `%SYS` namespace privileges. Confirm this
   is granted by default on Community Edition.

4. **Class-source (`.cls`) handling.** Out of scope for `m-cli` Tier 2/3 —
   `m-cli` is M-routine-focused, not ObjectScript-class-focused. State this
   limit explicitly so users don't expect class refactoring support.

5. **IRIS-specific lint rules.** XINDEX is YDB / GT.M heritage. Some
   XINDEX rules don't apply to IRIS code (different reserved word lists,
   different ISVs). The lint runner should support an
   `[lint] dialect = "ydb" | "iris" | "ansi"` toggle to suppress
   non-applicable rules.

---

## 11. Bottom line

`m-cli` was built around a clean abstraction without IRIS in mind, and the
engine boundary is already in the right place — confined to the test and
coverage runner modules, behind a small set of helpers. The work to support
IRIS is **less an architectural pivot than a parallel implementation**:

- ~2 weeks of focused work for a usable IRIS test runner.
- ~3–4 weeks total for test + coverage parity.
- Source-level features (fmt, lint, LSP) port for free with a glob change.

The biggest non-trivial item — IRIS-specific M dialect support in the
parser — is a `tree-sitter-m` workstream that progresses independently of
`m-cli` itself.

Recommended sequencing:

1. Land the engine-adapter scaffolding (Phase I-0) **before** any of the
   Tier-3 quick-wins from [language-cli-survey.md §6.2](language-cli-survey.md#62-phased-roadmap),
   so new subcommands inherit engine-awareness from day one.
2. Then proceed with Phase 3a (quick wins) — these are mostly engine-agnostic
   and a `--engine` flag is a free win for them.
3. Add Phase I-1 / I-2 / I-3 in parallel with Phase 3b (codemod / profile /
   bench), since both phases touch the test/coverage runners.
4. `m debug` (Phase 3c) ships engine-aware from the start, since it has no
   prior implementation to migrate.

The result is a CLI where the user types `m test`, `m coverage`,
`m profile` — and `m-cli` figures out from config or environment whether
that means YDB or IRIS underneath.
