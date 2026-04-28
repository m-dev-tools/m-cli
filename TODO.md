# m-cli — TODO

Pick up from this list. Top section is "next session" — concrete, ordered. Lower sections are deferred / parking lot.

## STATUS — Tier 1 DONE; Tier 2 IN PROGRESS

**Tier 1 — DONE (2026-04-27).** All five inner-loop capabilities ship: `m fmt`, `m lint --rules=xindex` (37/66 XINDEX rules — breadth-first per [m-tooling-tier1.md §3.6](../m-tools/docs/m-tooling-tier1.md#36-out-of-scope-intentional)), `m test`, single-test selection, `m watch`. All four §3.5 validation gates pass.

**Tier 2 — formally started.** Per [m-tool-gap-analysis.md §8](../m-tools/docs/m-tool-gap-analysis.md#8-rank-ordered-developer-impact-where-to-invest-first):

| # | Capability | Status | Notes |
|---|---|:---:|---|
| 6 | CI script | 🟡 Partial | Project Makefile + pre-commit scaffold cover the main use cases. No dedicated `m ci` planned. |
| 7 | **Coverage** | 🟡 First slice shipped | `m coverage` — Phase C. Label-level via ZBREAK; live smoke 85/123 (69.1%) against m-tools, byte-identical to ycover. Line-level instrumentation deferred. |
| 8 | Linter (style) | ✅ Done | Bundled with `m lint`; `--rules=sac` for SAC-tagged subset. |
| 9 | Pre-commit hooks | ✅ Done | `.pre-commit-hooks.yaml` shipped. |
| 10 | Debugger | ⏸️ Deferred | DAP integration is a separate, large effort. Not on near-term roadmap. |

**Next session — pick from:**

1. **Coverage line-level (Phase C deepening).** `m coverage --lines` via tree-sitter-driven source instrumentation: identify executable lines per routine, emit a counter increment per line, run, parse. Bigger build than the label-level slice but reuses everything in `m_cli.coverage` plus the workspace index.
2. **Coverage LCOV output.** Add `--format=lcov` for CI integration. Mechanical follow-up; label-level data maps to LCOV's `DA:line,count` records.
3. **Phase D (deferred XINDEX rules).** The 30 not-yet-ported rules; far easier now that Phase B's reference index is in place — cross-routine "call to undefined label" / "label never referenced" lints land in a few lines each on top of `WorkspaceIndex.references_to`.
4. **Publish to PyPI.** Unblocks `language: repo` pre-commit and downstream `pip install m-cli`.

---

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
- [x] **LSP Stage 3: code actions.** `textDocument/codeAction` groups in-context diagnostics by `fixer_id` and returns one Quick Fix per distinct fixer; each action's `WorkspaceEdit` runs the single fmt rule file-wide so duplicates collapse into one click. Skips no-op fixers and parse-error sources. `codeActionProvider: True` advertised.
- [x] **VS Code editor wiring.** `tree-sitter-m-vscode` carries a `vscode-languageclient` integration that spawns `m lsp`. Settings: `m-cli.enabled`, `m-cli.path`, `m-cli.args`, `m-cli.trace.server`. Self-install via `npm run package` + `code --install-extension`. See that repo's `docs/lsp-setup.md`.
- [x] **LSP Stage 4: hover + completion + rule-filter override.** `textDocument/hover` resolves M commands / ISVs / intrinsic functions against m-standard's TSVs and returns Markdown (canonical name, abbreviation, syntax format, standard status). `textDocument/completion` returns the full keyword universe (323 items) as `CompletionItem`s with kind/detail set; client filters by prefix. `m lsp --rules <filter>` overrides the default `xindex` rule filter at startup. The deeper LSP `workspace/configuration` round-trip (per-rule disable, severity overrides) is intentionally deferred — the CLI flag covers the immediate need without async plumbing.
- [x] **LSP Stage 4b: document structure + navigation.** Five handlers added in one pass:
  - `textDocument/documentSymbol` — outline view, one `SymbolKind.Function` per label; range covers body until next label, formals appended to display name (`INNER(a,b)`).
  - `textDocument/codeLens` — `▶ Run test <label>` above each `t<UpperCase>(pass,fail)` test label in `*TST.m` files. Lens carries a `m-cli.runTest` command with `[uri, label]` args; the VS Code extension is expected to register that command and shell out to `m test FILE.m::tLabel` (extension-side wiring is the next handoff).
  - `textDocument/foldingRange` — fold each multi-line label body and each contiguous dot-block run.
  - `textDocument/signatureHelp` — inside `$FN(...)`, returns the m-standard syntax format as a single signature. Trigger chars `(` and `,`. ISV-only / user-label calls return None.
  - `textDocument/documentHighlight` — same-file occurrences of the identifier under cursor, strict word-boundary matching, case-sensitive (M's variable case rules), single-char tokens skipped.
  - Structure helpers in `m_cli.lsp.structure` (`find_labels`, `find_dot_blocks`); CodeLens reuses `m_cli.test.discovery.find_test_cases` so the LSP and `m test` runner agree on what a test label is. 36 new tests, full check gate green, coverage 80.7%.
- [x] **VS Code extension wiring for `m-cli.runTest`.** Extension registers the command, opens/reuses an "m test" terminal, and runs `m test <file>::<label>` with `env -u ydb_routines -u ydb_gbldir -u ydb_dir` to scrub stale shell env that would otherwise prevent m-cli from deriving the right routines path. Verified click-to-pass on `HELLOTST::tGreetWorld`. Uncommitted in `~/projects/tree-sitter-m-vscode/`.
- [x] **Phase B (first slice) — workspace symbol index + textDocument/definition.** New module `m_cli.workspace`: `WorkspaceIndex` (routine → labels, case-insensitive lookup), `build_index(roots)`, `reference_at(line, character)` for parsing `LABEL^ROUTINE` / `^ROUTINE` / `LABEL` / `$$LABEL^ROUTINE` / `$$LABEL` under the cursor. LSP `textDocument/definition` resolves cross-routine refs via the index, falls back to same-document scan for label-only refs. Index built at LSP startup from `Path.cwd()`. 19 workspace tests + 8 LSP-definition tests; live smoke confirmed against a synthetic two-file workspace. Capability advertised: `definitionProvider: True`. Open follow-ups (deliberate splits, not blockers): incremental `didChangeWatchedFiles` updates, `textDocument/references`, `workspace/symbol`, and cross-routine lint rules (M-XINDX-004 etc.).
- [x] **Phase A — project config files.** `.m-cli.toml` (preferred) and `[tool.m-cli]` in `pyproject.toml` (fallback) drive `m fmt`, `m lint`, and `m lsp`. Discovery walks up from cwd, stops at `.git`. Schema: `[lint] rules / disable / severity`, `[fmt] rules`. CLI flags override config; unknown keys ignored; invalid values raise. Implementation in `m_cli.config`. Verified end-to-end via lint CLI + live LSP — disable drops the rule, severity overrides remap the published LSP severity. 19 new config tests + 4 LSP-config tests; 366 pass / 0 fail.
- [ ] **Deferred from Stage 4 / 4b** if self-trial demands it: `workspace/configuration` for per-rule disable / severity remap; hover-on-diagnostic showing rule descriptions; CodeLens `resolveProvider` (lazy command resolution) if the eager populate becomes a perf concern.
- [x] **Pre-commit hook scaffold.** `.pre-commit-hooks.yaml` exposes `m-fmt-check`, `m-fmt`, and `m-lint` hooks. Schema gated by tests. Docs: `docs/pre-commit.md`. Activation of the repo-pull style waits on m-cli + tree-sitter-m being published; the `language: system` style works today.
- [ ] `--rules=sac` tag — currently only `xindex` and `all` are exercised; `sac`-tagged rules exist (012, 035, 044, 062) but the tag selector hasn't been smoke-tested

## Known issues / quirks

- 376/39,330 VistA routines fail to parse (skipped from both round-trip and lint). These match the tree-sitter-m corpus boundary — see `project_tree_sitter_m_vista_corpus.md` memory.
- `make vista` and `make lint-vista` use absolute paths to `~/vista-meta/...`; portability across machines is not a Tier 1 concern.
- Branch is `master` not `main` — different from most repos under `~/projects/`.
