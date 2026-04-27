# m-cli — TODO

Pick up from this list. Top section is "next session" — concrete, ordered. Lower sections are deferred / parking lot.

## Tier 1 Step 3 (`m test`) — DONE

Shipped: `src/m_cli/test/` with discovery, runner, output formatters (text/tap/json), and CLI integration. Smoke-tested against `m-tools/routines/tests/` — 11 suites, 224/224 assertions pass against real ydb. Single-test selection (`SUITE::tLabel`) folds Step 4 into the same release.

Deferred from Step 3:
- [ ] **`m test --watch`** — inotify-based; deferred to Step 5 below.
- [ ] **JUnit XML output** — useful for CI integrations; not needed yet.
- [ ] **Per-label results in whole-suite mode.** Today `m test` parses TESTRUN's `PASS`/`FAIL` lines but cannot map them back to labels because TESTRUN doesn't emit a per-label header. Either (a) modify `TESTRUN.m` to emit headers, or (b) make whole-suite runs internally invoke each label separately when fine-grained reporting is requested. Option (a) is cleaner but lives in m-tools.
- [ ] **Set up env in `m test` itself.** Right now you must `source scripts/ydb-env.sh` first. Worth a `--ydb-dist` / `--routines-path` flag pair so `m test` can stand alone. Check if `m_cli.test.runner._build_env` is good enough to drop the bash sourcing entirely.

## Tier 1 Step 5 (`m watch`) — DONE

Shipped: `src/m_cli/watch/` with mtime-polling change detection, source→suite affinity, and CLI integration. Default poll interval is 0.5 s. Source-file changes (`foo.m`) map to `FOOTST.m`; suite-file changes re-run only themselves; non-mappable changes re-run every suite. Discovery dedups overlapping paths. Live-watch smoke against m-tools confirmed.

Deferred from Step 5:
- [ ] **Inotify upgrade.** Polling burns CPU on idle for large trees. If/when latency or efficiency matters, swap `Poller` for a `watchdog`-based implementation behind the same interface — affinity / CLI don't need to change.
- [ ] **Debounce window.** Fast saves (editor backups, formatter passes) can fire several events in a row; today each becomes a separate run. A 200–300 ms debounce that batches changes would cut redundant runs without affecting interactive feel.
- [ ] **Cross-routine call graph for richer affinity.** When `foo.m` changes, also re-run any suite whose source calls `^foo`. Needs a simple call-graph index built once at startup; out of scope for Tier 1.

## After Tier 1 — performance and tooling polish

## Next session — pick from below

Tier 1 is complete. The remaining work is split across linter coverage, performance, and integrations.

## XINDEX rule expansion (Step 2.x)

The 30 XINDEX rules NOT yet implemented need deeper analysis than a single AST walk:
- Data-flow / scope tracking (uninitialized vars, naked references, write-only / read-only globals)
- Cross-routine resolution (call-to-missing-label across files, not just within file)
- Control-flow (dead code, unreachable QUIT, FOR without QUIT body)

These are deferred to a later linter phase. **Do not** chase 100% XINDEX parity before Steps 3–5 ship — Tier 1 is a breadth-first pass.

The 8 currently-silent registered rules (M-XINDX-002, 015, 018, 021, 027, 028, 031, 054) fire on patterns rare in VistA but common in other corpora — leave them registered.

## Performance follow-up (Step 2.x)

- [x] **Single-pass AST walk via `NodeIndex`.** Walk once per file, bucket by node type, dispatch rules off the bucket. Landed: VistA gate **166 s** (was ~1458 s — 8.7× faster). Microbenchmark: 3.75 ms/file (was 32.94 ms/file).
- [ ] **Parallelize across routines** with `concurrent.futures.ProcessPoolExecutor`. Each routine's `lint_source` is independent. With 4 workers we should land well under the 120 s budget. Pass `--jobs N` (default `os.cpu_count()`).
- [ ] Cache parsed trees for incremental lint (only meaningful with a daemon / LSP — defer until LSP work).
- [ ] Profile with `make lint-vista` before/after each change — never optimise blind.

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
