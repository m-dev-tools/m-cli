---
created: 2026-05-11
last_modified: 2026-05-11
revisions: 0
doc_type: [REFERENCE]
---

# m-cli — Documentation Index

> First-pass index generated 2026-05-11. Labels follow the shared vocabulary below; the same vocabulary is used across all m-dev-tools repos.

## Vocabulary

Each doc is labeled `[TYPE · type? · connection · connection?]`.

**Types** — `HISTORY` · `ARCHITECTURE` · `DESIGN` · `ADR` · `SPEC` · `REFERENCE` · `GUIDE` · `TUTORIAL` · `ROADMAP` · `PLAN` · `RESEARCH` · `SURVEY` · `GAP-ANALYSIS` · `STATUS` · `EXPLAINER` · `NOTES` · `WORKED-EXAMPLE` · `SETUP` · `INTEGRATION` · `PROPOSAL` · `BUILD-LOG` · `CHANGELOG` · `POSTMORTEM`

**Repo connections** — `history` · `function` · `design` · `architecture` · `planning` · `implementation`

## Top-level

- **`cli-menu-system.md`** — `[REFERENCE · function]` Master tabular reference of every `m <subcommand>` arranged in developer-journey order, tagged by lifecycle stage (env health / setup / inner loop / integration), with a 5-circle frequency rating per command and cross-cutting notes on exit codes, engine binding, and configuration.
- **`evolution.md`** — `[HISTORY · BUILD-LOG · history · implementation]` Chronological narrative of how m-cli was built tier by tier, milestone by milestone, with performance journey and deferred items.
- **`m-tdd-lifecycle-walkthrough.md`** — `[WORKED-EXAMPLE · TUTORIAL · SMOKE-TEST · function]` End-to-end transcript building `reqstats` (an HTTP-access-log summarizer) using STDCSV/STDMATH/STDJSON/STDASSERT. Doubles as a smoke gate that every `m <subcommand>` works on a docker-only host; finished app left at `~/m-work/reqstats/` for re-running any step.
- **`guide.md`** — `[GUIDE · REFERENCE · function · architecture]` Comprehensive user-facing reference covering every subcommand, configuration, profiles, and the four-tier framework m-cli implements.
- **`m-linting-user-guide.md`** — `[GUIDE · function]` How-to guide for `m lint`: profiles, severity, thresholds, output formats, inline disables, and CLI flags.
- **`plugin-development.md`** — `[GUIDE · SPEC · function · architecture]` Contract and walkthrough for registering out-of-tree subcommands via the `m_cli.plugins` entry-point group.
- **`pre-commit.md`** — `[GUIDE · INTEGRATION · function]` Downstream pre-commit integration recipe for `m-fmt-check`, `m-fmt`, and `m-lint` hooks via `language: system`.
- **`vista-meta-bootstrap.md`** — `[HISTORY · EXPLAINER · history · design]` Records how the vista-meta YottaDB container bootstrapped m-cli development and why m-cli is now engine-independent.
- **`worked-example-accsum.md`** — `[WORKED-EXAMPLE · TUTORIAL · function]` End-to-end TDD walkthrough building an `accsum` access-log summariser to demonstrate every `m` subcommand in context.

## `cli-frameworks/` — CLI ergonomics conventions and Python-framework landscape

- **`cli-frameworks/cli-ux-conventions-guide.md`** — `[RESEARCH · REFERENCE · GUIDE · design · function]` Canonical org-level rules for every `m <subcommand>` — dispatcher vs leaf taxonomy, bare-invocation behavior, `--help` to stdout, exit-code vocabulary (0 / 1 / 2), unknown-flag routing. Pinned by `tests/test_cli_ux_contract.py`. Vendored from the org `.github` repo.
- **`cli-frameworks/cli-ux-plan.md`** — `[PLAN · SUMMARY · planning · implementation]` Companion remediation plan for the conventions guide — findings, severity table, proposed changes, open editorial questions (Q1–Q8), and suggested seven-PR sequencing.
- **`cli-frameworks/cli-python-frameworks.md`** — `[RESEARCH · REFERENCE · SURVEY · design]` Comparative landscape of Python CLI frameworks (argparse / Click / Typer / Fire / docopt / cleo / argh / plac / rich-click) with current GitHub stars, 12-month activity metrics, feature matrix, decision tree, and the resolved position on why m-cli stays on argparse.

## `plans/` — design proposals, surveys, status reports, and implementation plans tracking m-cli's roadmap

- **`plans/iris-ydb-portability.md`** — `[PLAN · RESEARCH · planning · architecture]` Function-by-function IRIS vs YottaDB CLI comparison with an engine-adapter refactor plan for cross-engine dispatch.
- **`plans/language-cli-survey.md`** — `[SURVEY · GAP-ANALYSIS · planning · design]` Survey of Rust/Go/Python/JS/Java CLI toolchains scored on productivity and quality, closing with a rank-ordered m-cli gap analysis.
- **`plans/linter-profiles-guide.md`** — `[DESIGN · PROPOSAL · design · planning]` Proposes splitting the `sac` profile into four mechanism-grounded profiles (KIDS-build / vista / safety / sac-style) by gatekeeper.
- **`plans/m-cli-history-and-evolution.md`** — `[HISTORY · EXPLAINER · history · architecture]` Chronicles the six-week sprint birthing m-tools, vista-meta, m-standard, tree-sitter-m, m-cli, and m-stdlib as cooperating siblings.
- **`plans/m-corpus-catalog.md`** — `[REFERENCE · RESEARCH · planning]` Catalog of non-VistA open-source M corpora vetted as candidates for the M-MOD-NN regression gate.
- **`plans/m-env-implementation-plan.md`** — `[PLAN · planning · implementation]` Self-contained implementation guide for an `m-env` POC proving containerized YottaDB/IRIS environments before folding into m-cli.
- **`plans/m-environment-tool.md`** — `[PROPOSAL · DESIGN · design · planning]` Design proposal for `m init` / `m env` / `m doctor` commands managing Dev Container-based M execution environments.
- **`plans/m-linter-status-2026-04-30.md`** — `[STATUS · POSTMORTEM · implementation]` Comprehensive audit of every shipped lint rule against a 4,215-routine non-VA corpus with prioritized fixes and landed deltas.
- **`plans/m-linting-implementation-plan.md`** — `[PLAN · BUILD-LOG · planning · implementation]` Phase-by-phase tracker for the M-MOD-NN modernization track, vista split, thresholds, engine-aware rules, and data-flow research.
- **`plans/m-linting-survey.md`** — `[SURVEY · GAP-ANALYSIS · design · planning]` Audits the 42 XINDEX/SAC rules for modern relevance and proposes a rank-ordered greenfield rule set drawn from first principles.
