# m-cli — TODO

Pick up from this list. Top section is "next session" — concrete, ordered. Lower sections are deferred / parking lot.

## Next session — Tier 1 Step 3: `m test`

Parser-aware port of the legacy `ytest` shell script (see `~/projects/m-tools/bin/ytest` for reference). Test-runner adapter is YottaDB-specific (unlike `fmt` and `lint` which are engine-neutral).

- [ ] **Read the reference.** `~/projects/m-tools/bin/ytest` and `~/projects/m-tools/routines/tests/TESTRUN.m`. Understand the discovery/run/report contract before designing.
- [ ] **Spec the discovery rule.** YottaDB convention is `routines/tests/<NAME>TST.m` containing labels `tXxx`. Should `m test` walk a configurable test root, or follow ydb_routines? Decide; document in CLAUDE.md.
- [ ] **Write tests first.** `tests/test_runner.py`: discovery (find suites + labels via tree-sitter, not regex), single-suite invocation, single-test selection (`m test SUITE::tCase`), TAP output, JSON output.
- [ ] **Implement `src/m_cli/test/`.**
  - `discovery.py` — parse routines via `m_cli.parser`, yield (suite, label) pairs from `label` AST nodes matching `tXxx`
  - `runner.py` — exec `ydb -run ^TESTRUN <SUITE>` (or single-test variant if available), capture stdout, parse pass/fail
  - `cli.py` — argparse: `m test [PATH...]`, `--filter`, `--format=tap|json`, `--list`
- [ ] **Wire into `m_cli/cli.py`.** Register `test` subcommand alongside `fmt` and `lint`.
- [ ] **Smoke-test against m-tools/routines/tests/.** That repo has real `*TST.m` suites (HELLOTST, GLOBALTST, etc.) — use as a fixture; don't fabricate one.
- [ ] **Single-test selection (Step 4).** Fold into the same PR: `m test SUITE::tLabel` runs a single label. May require a small helper routine in M (see if `^TESTRUN` already supports it; if not, add it to m-tools).
- [ ] **Commit as `Tier 1 Step 3: m test runner`** when green.

## After Step 3 — Tier 1 Step 5: `m watch`

- [ ] Inotify-based file watcher; on `*.m` save → re-run affected suites
- [ ] Debounce + suite-affinity (only re-run suites whose source changed)
- [ ] Reference: legacy `make watch` uses `entr`; consider whether to wrap or replace

## XINDEX rule expansion (Step 2.x)

The 30 XINDEX rules NOT yet implemented need deeper analysis than a single AST walk:
- Data-flow / scope tracking (uninitialized vars, naked references, write-only / read-only globals)
- Cross-routine resolution (call-to-missing-label across files, not just within file)
- Control-flow (dead code, unreachable QUIT, FOR without QUIT body)

These are deferred to a later linter phase. **Do not** chase 100% XINDEX parity before Steps 3–5 ship — Tier 1 is a breadth-first pass.

The 8 currently-silent registered rules (M-XINDX-002, 015, 018, 021, 027, 028, 031, 054) fire on patterns rare in VistA but common in other corpora — leave them registered.

## Performance follow-up (Step 2.x)

Lint is **12× over the 120 s budget** at 36 rules. Order of attack:
- [ ] Parallelize across routines (multiprocessing pool — each routine is independent)
- [ ] Single-pass AST walk: collect node types once, dispatch to rules indexed by node type (kills the 36× redundant `_walk(tree.root_node)`)
- [ ] Cache `Language()` and `Parser()` (already done) but consider caching parsed trees for incremental lint
- [ ] Profile with `make lint-vista` before/after each change — never optimise blind

Do not start before Tier 1 Steps 3 and 5 ship.

## Smaller cleanups / nice-to-haves

- [ ] Add a remote for this repo (currently local-only; `git remote add origin ...` once a home is decided)
- [ ] `m fmt` — start layering canonical-layout rules on top of identity (per README "Roadmap" section). Each rule needs hand-test + VistA gate.
- [ ] LSP wrapper for `m lint` — JSON output is already LSP-shaped; need a thin server stub for VS Code via `tree-sitter-m-vscode`
- [ ] Pre-commit hook scaffold for downstream M projects to opt into `m fmt --check` and `m lint --error-on=fatal`
- [ ] `--rules=sac` tag — currently only `xindex` and `all` are exercised; `sac`-tagged rules exist (012, 035, 044, 062) but the tag selector hasn't been smoke-tested

## Known issues / quirks

- 376/39,330 VistA routines fail to parse (skipped from both round-trip and lint). These match the tree-sitter-m corpus boundary — see `project_tree_sitter_m_vista_corpus.md` memory.
- `make vista` and `make lint-vista` use absolute paths to `~/vista-meta/...`; portability across machines is not a Tier 1 concern.
- Branch is `master` not `main` — different from most repos under `~/projects/`.
