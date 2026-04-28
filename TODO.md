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

Tier 1 is complete and lint perf is under budget. Remaining work is XINDEX rule expansion and integrations.

## XINDEX rule expansion (Step 2.x)

The 30 XINDEX rules NOT yet implemented need deeper analysis than a single AST walk:
- Data-flow / scope tracking (uninitialized vars, naked references, write-only / read-only globals)
- Cross-routine resolution (call-to-missing-label across files, not just within file)
- Control-flow (dead code, unreachable QUIT, FOR without QUIT body)

These are deferred to a later linter phase. **Do not** chase 100% XINDEX parity before Steps 3–5 ship — Tier 1 is a breadth-first pass.

The 8 currently-silent registered rules (M-XINDX-002, 015, 018, 021, 027, 028, 031, 054) fire on patterns rare in VistA but common in other corpora — leave them registered.

## Performance follow-up (Step 2.x) — DONE

- [x] **Single-pass AST walk via `NodeIndex`.** Walk once per file, bucket by node type, dispatch rules off the bucket. VistA gate **166 s** (was ~1458 s — 8.7× faster).
- [x] **Parallelize across routines** with `concurrent.futures.ProcessPoolExecutor`. `m lint --jobs N` (default `os.cpu_count()`). 16-core host: VistA gate **22.6 s** — 5.3× under the 120 s budget, 64.5× faster than the original baseline.
- [ ] Cache parsed trees for incremental lint (only meaningful with a daemon / LSP — defer until LSP work).

## Smaller cleanups / nice-to-haves

- [ ] **Publish m-cli + tree-sitter-m.** Pre-commit hooks (repo-pull style) and any future `pip install m-cli` workflow are blocked on this. Steps: (1) decide a host for m-cli (GitHub `rafael5/m-cli`?); (2) publish tree-sitter-m to PyPI (it has a `cibuildwheel` config already); (3) update m-cli's `pyproject.toml` to allow `tree-sitter-m` from PyPI in addition to the local-path override.
- [ ] **`m fmt` canonical-layout — first two rules shipped.** `trim-trailing-whitespace` and `uppercase-command-keywords` opt-in via `--rules=canonical`. Backed by `make vista-canonical` (idempotency + AST shape). Future candidates: comma/colon spacing normalization, abbreviation→canonical (e.g. `S`→`SET`, behind a flag), null-line removal (M-XINDX-042 auto-fix). Each new rule must pass the canonical gate.
- [x] **LSP Stage 1: diagnostics push.** `m lsp` starts a pygls-based server over stdio; didOpen/didChange/didSave/didClose handlers wire `m_cli.lint` to `textDocument/publishDiagnostics`. Optional `[lsp]` extra. Live smoke confirmed: open `/tmp/hello.m`, get 6 diagnostics back with `fixer_id` data on the auto-fixable ones.
- [x] **LSP Stage 2: formatting.** `textDocument/formatting` runs `format_source(src, rules=canonical_rules())` and returns a full-document `TextEdit`. `documentFormattingProvider: True` advertised. Empty list on already-canonical or parse-error sources. (`textDocument/rangeFormatting` deferred — uppercase-command-keywords needs the AST so per-range becomes awkward; revisit if/when a more text-local rule lands.)
- [ ] **LSP Stage 3: code actions.** Hook `textDocument/codeAction` to the `Rule.fixer_id` linkage already exposed via the `data` field on diagnostics.
- [ ] **LSP Stage 4 (optional polish):** workspace configuration (override `--rules` / `--error-on`), hover (rule descriptions), completion (M command keywords from `standard_commands()`).
- [x] **Pre-commit hook scaffold.** `.pre-commit-hooks.yaml` exposes `m-fmt-check`, `m-fmt`, and `m-lint` hooks. Schema gated by tests. Docs: `docs/pre-commit.md`. Activation of the repo-pull style waits on m-cli + tree-sitter-m being published; the `language: system` style works today.
- [ ] `--rules=sac` tag — currently only `xindex` and `all` are exercised; `sac`-tagged rules exist (012, 035, 044, 062) but the tag selector hasn't been smoke-tested

## Known issues / quirks

- 376/39,330 VistA routines fail to parse (skipped from both round-trip and lint). These match the tree-sitter-m corpus boundary — see `project_tree_sitter_m_vista_corpus.md` memory.
- `make vista` and `make lint-vista` use absolute paths to `~/vista-meta/...`; portability across machines is not a Tier 1 concern.
- Branch is `master` not `main` — different from most repos under `~/projects/`.
