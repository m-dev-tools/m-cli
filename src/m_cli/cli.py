"""`m` CLI dispatcher.

Single binary `m` with subcommands (`m fmt`, future: `m lint`, `m test`).
Mirrors `cargo`/`go`/`git` style.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli import __version__
from m_cli._overview import print_overview
from m_cli.build import build_command
from m_cli.capabilities import capabilities_command
from m_cli.ci import ci_command
from m_cli.coverage.cli import add_arguments as add_coverage_arguments
from m_cli.doc import doc_command
from m_cli.doc.errors import errors_command
from m_cli.doc.examples import examples_command
from m_cli.doc.manifest import manifest_command
from m_cli.doc.search import search_command
from m_cli.doctor import doctor_command
from m_cli.fmt import fmt_command
from m_cli.lint import lint_command
from m_cli.lsp import lsp_command
from m_cli.new import new_command
from m_cli.plugins import plugins_command, register_plugins
from m_cli.run import run_command
from m_cli.test import test_command
from m_cli.watch import watch_command


def build_parser() -> argparse.ArgumentParser:
    """Construct the full `m` argparse parser.

    Factored out of :func:`main` so `m capabilities` can introspect the
    same tree that `main` dispatches against. Plugin discovery runs
    here, so contributed subcommands appear in the capabilities output
    just like built-ins.
    """
    parser = argparse.ArgumentParser(
        prog="m",
        description="M (MUMPS) source-level toolchain.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"m-cli {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # `m fmt`
    fmt_parser = subparsers.add_parser(
        "fmt",
        help="Format M source files",
        description=(
            "Parse and pretty-print M (.m) source files. By default, "
            "rewrites files in place. Use --check to verify only, --diff "
            "to print a unified diff, or --stdout to write to stdout."
        ),
    )
    fmt_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help=(
            "One or more .m files (or directories — searched recursively "
            "for *.m). Default: current directory."
        ),
    )
    fmt_parser.add_argument(
        "--rules",
        default=None,
        help=(
            "Canonical-layout rules to apply: 'none' (identity, default), "
            "'canonical' (SAC hygiene: trim + uppercase), 'pythonic' "
            "(expand abbreviations to canonical names: S→SET, $L→$LENGTH), "
            "'pythonic-lower' (same but lowercase output: set, $length), "
            "'compact' (inverse: SET→S, $LENGTH→$L), 'all' (every "
            "registered rule — diagnostic only), or a comma-separated "
            "list of rule ids. When unset, falls back to [fmt] rules "
            "from .m-cli.toml / pyproject.toml."
        ),
    )
    fmt_parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write; exit 1 if any file is not already formatted",
    )
    fmt_parser.add_argument(
        "--diff",
        action="store_true",
        help="Don't write; print unified diff for each file that would change",
    )
    fmt_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write formatted output to stdout (single-file mode)",
    )
    fmt_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file progress output",
    )
    fmt_parser.add_argument(
        "--list-rules",
        action="store_true",
        help=(
            "Emit the full fmt rule inventory (id, title, description, "
            "presets) as JSON and exit. Source of truth for "
            "dist/fmt-rules.json."
        ),
    )
    fmt_parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Force JSON output. Currently only meaningful with --list-rules "
            "(the rule inventory always emits JSON in Phase 0); accepted "
            "for explicit invocation per the tier-1 manifest contract."
        ),
    )
    fmt_parser.set_defaults(func=fmt_command)

    # `m lint`
    lint_parser = subparsers.add_parser(
        "lint",
        help="Lint M source files",
        description=(
            "Run linter rules over M (.m) source files. m-cli's lint engine "
            "is engine- and dialect-neutral; opinionated rule sets ship as "
            "named *profiles*. The default profile ('default') is m-cli's "
            "curated baseline. Run `m lint --list-profiles` to see what "
            "ships (e.g. 'xindex' — VA VistA Toolkit ^XINDEX port; 'sac' — "
            "VA SAC subset). Pass --rules=<profile> to switch, or "
            "--rules=M-XINDX-013,M-XINDX-019 for a specific rule subset.\n\n"
            "TIP: if you're linting YottaDB-specific or IRIS-specific code, "
            "set --target-engine=yottadb (or =iris) — engine-aware rules "
            "(M-MOD-021/022/023) flag $Z* tokens as non-portable under the "
            "default --target-engine=any, generating thousands of findings "
            "on engine-specific code. Set in .m-cli.toml as `[lint] "
            'target_engine = "yottadb"` to make it permanent.'
        ),
    )
    lint_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help=(
            "One or more .m files (or directories — searched recursively "
            "for *.m). Default: current directory."
        ),
    )
    lint_parser.add_argument(
        "--rules",
        default=None,
        help=(
            "Profile name or comma-separated rule IDs (default: 'default', "
            "or [lint] rules from .m-cli.toml / pyproject.toml). See "
            "--list-profiles for the available named profiles."
        ),
    )
    lint_parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List the named lint profiles and exit",
    )
    lint_parser.add_argument(
        "--list-rules",
        action="store_true",
        help=(
            "Emit the full rule inventory (id, severity, category, tags, "
            "profiles, fixer_id, description) as JSON and exit. Source of "
            "truth for dist/lint-rules.json."
        ),
    )
    lint_parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Force JSON output. Currently only meaningful with --list-rules "
            "(the rule inventory always emits JSON in Phase 0); accepted "
            "for explicit invocation per the tier-1 manifest contract."
        ),
    )
    lint_parser.add_argument(
        "--target-engine",
        choices=("any", "yottadb", "iris"),
        default=None,
        help=(
            "Target M engine for engine-aware rules. 'any' (default) keeps "
            "the linter portable; 'yottadb' / 'iris' unlock engine-specific "
            "allowlists for $Z* ISVs/functions and Z-commands. CLI wins over "
            "[lint] target_engine in .m-cli.toml."
        ),
    )
    lint_parser.add_argument(
        "--threshold",
        action="append",
        metavar="KEY=VAL",
        default=None,
        help=(
            "Override a [lint.thresholds] config value. Repeatable. "
            "Example: --threshold line_length=120 --threshold routine_lines=2000. "
            "Known keys: line_length, code_line_length, routine_lines, "
            "label_lines (see m_cli.lint.thresholds.KNOWN_THRESHOLDS)."
        ),
    )
    lint_parser.add_argument(
        "--format",
        choices=("text", "json", "tap"),
        default="text",
        help="Output format (default: text)",
    )
    lint_parser.add_argument(
        "--error-on",
        default="warning",
        help=(
            "Severity threshold for non-zero exit code: "
            "error | warning | style | info (default: warning)"
        ),
    )
    lint_parser.add_argument(
        "--lint-unparseable",
        action="store_true",
        help="Lint files that have parse errors (default: skip them)",
    )
    lint_parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help=(
            "Number of parallel worker processes (default: os.cpu_count(); 1 to disable the pool)"
        ),
    )
    lint_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress summary output",
    )
    lint_parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Apply auto-fixes for diagnostics whose rule has a `fixer_id`. "
            "Each unique fixer (an `m fmt` rule) runs once per affected file. "
            "Files are rewritten in place; remaining (non-fixable) findings "
            "are still reported. Combine with --check to preview without "
            "writing."
        ),
    )
    lint_parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to a baseline file (default: .m-lint-baseline.json in the "
            "first ancestor that contains one). Findings present in the "
            "baseline are suppressed. Use --update-baseline to regenerate."
        ),
    )
    lint_parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Disable baseline filtering even if .m-lint-baseline.json exists.",
    )
    lint_parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Write current findings to the baseline file (default: "
            ".m-lint-baseline.json in the project root) and exit 0. "
            "Existing entries are replaced wholesale."
        ),
    )
    lint_parser.set_defaults(func=lint_command)

    # `m test`
    test_parser = subparsers.add_parser(
        "test",
        help="Run M test suites against YottaDB",
        description=(
            "Discover and run M test suites. A suite is a `.m` file whose "
            "stem ends in `TST`; test labels follow the `t<UpperCase>"
            "(pass,fail)` convention (m-tools / TESTRUN). Pass paths to "
            "files or directories; with no path, falls back to "
            "`./routines/tests/`. Use `FILE::tLabel` to run one test."
        ),
    )
    test_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "Files, directories, or `FILE::tLabel` selectors. With no "
            "argument, looks for `./routines/tests/`."
        ),
    )
    test_parser.add_argument(
        "--list",
        action="store_true",
        help="List discovered suites and tests without running them",
    )
    test_parser.add_argument(
        "--filter",
        default=None,
        help="Only run suites whose name contains this substring",
    )
    test_parser.add_argument(
        "--format",
        choices=("text", "tap", "json", "junit"),
        default="text",
        help="Output format (default: text)",
    )
    test_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress summary output",
    )
    test_parser.add_argument(
        "--changed",
        action="store_true",
        help=(
            "Run only suites whose source has changed in git "
            "(working tree + index + untracked). Combine with "
            "--changed-base to diff against a specific revision."
        ),
    )
    test_parser.add_argument(
        "--changed-base",
        default=None,
        metavar="REV",
        help=("With --changed: diff against revision REV (e.g. main) instead of the working tree."),
    )
    test_parser.add_argument(
        "--no-isolation",
        action="store_true",
        help=(
            "Skip the per-test STDFIX transactional wrapper. Use for "
            "legacy ^TESTRUN-style suites that don't want a TSTART / "
            "TROLLBACK around each test (default: isolation on)."
        ),
    )
    test_parser.add_argument(
        "--seed",
        action="append",
        default=[],
        metavar="PATH",
        dest="seeds",
        help=(
            "Load a STDSEED TSV manifest before running each test "
            '(`do load^STDSEED("PATH")`). Repeat for multiple seeds; '
            "order is preserved."
        ),
    )
    test_parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="PATH",
        dest="env_files",
        help=(
            "Load a `.env` file via STDENV before running each suite. "
            'Parsed values land in `^STDLIB($JOB,"env",KEY)` so test '
            'code reads via `$get(^STDLIB($JOB,"env","KEY"))`. '
            "Repeat for multiple env files; later files override earlier "
            "keys."
        ),
    )
    test_parser.add_argument(
        "--update-snapshots",
        action="store_true",
        dest="update_snapshots",
        help=(
            "Set the STDSNAP update sentinel before running each suite, "
            "so `asserts^STDSNAP` rewrites baselines instead of comparing. "
            "Run after an intentional change in test output to regenerate "
            "snapshot files."
        ),
    )
    test_parser.add_argument(
        "--timings",
        action="store_true",
        dest="timings",
        help=(
            "Show per-suite wall-clock duration in the summary line. "
            "Captures the full subprocess invocation (SSH + ydb startup "
            "+ test execution); useful for spotting suites that are "
            "slowing down the inner loop."
        ),
    )
    test_parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        metavar="SECONDS",
        help=(
            "Per-suite (or per-test, in single-test mode) timeout in "
            "seconds. The subprocess is killed if it runs past the "
            "deadline; the suite is reported as TIMEOUT, distinct "
            "from FAIL/0/0 caused by a parse-level zero-assertion "
            "result. Pass 0 to disable. Default: 600."
        ),
    )
    test_parser.set_defaults(func=test_command)

    # `m watch`
    watch_parser = subparsers.add_parser(
        "watch",
        help="Re-run M test suites on file change",
        description=(
            "Watch `.m` files and re-run affected test suites on save. "
            "Source `foo.m` maps to suite `FOOTST.m`; suite-file edits "
            "re-run only that suite. With no path, looks for "
            "`./routines/tests/`."
        ),
    )
    watch_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to watch (default: ./routines/tests/)",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds (default: 0.5)",
    )
    watch_parser.add_argument(
        "--once",
        action="store_true",
        help="Run the initial pass and exit (no watch loop)",
    )
    watch_parser.add_argument(
        "--filter",
        default=None,
        help="Only watch / run suites whose name contains this substring",
    )
    watch_parser.add_argument(
        "--format",
        choices=("text", "tap", "json"),
        default="text",
        help="Output format (default: text)",
    )
    watch_parser.set_defaults(func=watch_command)

    # `m coverage`
    coverage_parser = subparsers.add_parser(
        "coverage",
        help="Measure test coverage of an M project",
        description=(
            "Run the project's test suites under YottaDB ZBREAK "
            "instrumentation and report which production labels were "
            "exercised. Label-level coverage (line-level via source "
            "instrumentation is a future deliverable). Outputs text "
            "(default), JSON. Use --uncovered to list only uncovered "
            "labels; --min-percent N to fail the run when coverage is "
            "below the threshold."
        ),
    )
    add_coverage_arguments(coverage_parser)

    # `m lsp`
    lsp_parser = subparsers.add_parser(
        "lsp",
        help="Run the m-cli Language Server (over stdio)",
        description=(
            "Start the m-cli Language Server. Editors invoke this as a "
            "subprocess and exchange LSP messages over stdin/stdout. "
            "Features: diagnostics (lint on save/change), formatting "
            "(canonical layout), code actions (Quick Fix per fixable "
            "diagnostic), hover (M command/ISV/intrinsic descriptions), "
            "and completion (M keyword set). Requires the optional "
            "`[lsp]` extra (`pip install 'm-cli[lsp]'`)."
        ),
    )
    lsp_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging on stderr",
    )
    lsp_parser.add_argument(
        "--rules",
        default=None,
        help=(
            "Rule filter for diagnostics — passed to `m_cli.lint.select_rules`. "
            "Examples: `default` (the built-in default profile), `all`, "
            "`xindex` (VA VistA Toolkit), `sac`, `M-XINDX-013,M-XINDX-019`."
        ),
    )
    # vscode-languageclient appends `--stdio` when TransportKind.stdio is set;
    # accept and ignore it since stdio is the only transport we support.
    lsp_parser.add_argument(
        "--stdio",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    lsp_parser.set_defaults(func=lsp_command)

    # `m doctor`
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose the M development environment",
        description=(
            "Run a sequence of environment-health checks: $ydb_dist, "
            "$ydb_routines, the tree-sitter-m parser, m-standard "
            "keyword TSVs, and the `ydb` binary. Each check reports "
            "OK / WARN / FAIL with an actionable hint on failure. "
            "Exits 1 if any check is FAIL (WARN does not fail the run)."
        ),
    )
    doctor_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    doctor_parser.set_defaults(func=doctor_command)

    # `m new`
    new_parser = subparsers.add_parser(
        "new",
        help="Scaffold a new M project",
        description=(
            "Create a self-contained M project that passes `m fmt --check`, "
            "`m lint`, and `m test` on a clean clone. Generates "
            "routines/<NAME>.m, routines/<NAME>ASRT.m (a tiny in-tree "
            "assertion helper so the project has zero external M deps), "
            "tests/<NAME>TST.m, .m-cli.toml (pythonic-lower style), "
            ".gitignore, Makefile, and README.md. The routine name is "
            "derived from the project name (uppercased, alphanumeric only, "
            "≤ 8 chars per the M routine-name limit)."
        ),
    )
    new_parser.add_argument(
        "name",
        help="Project name (also drives the M routine name)",
    )
    new_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Target directory (default: ./<name>/)",
    )
    new_parser.add_argument(
        "--force",
        action="store_true",
        help="Scaffold even if the target directory exists and is non-empty",
    )
    new_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file progress output",
    )
    new_parser.set_defaults(func=new_command)

    # `m ci` (with sub-action `init`)
    ci_parser = subparsers.add_parser(
        "ci",
        help="CI scaffolding (subcommand: `init`)",
        description="Scaffold CI configuration for m-cli projects.",
    )
    ci_actions = ci_parser.add_subparsers(dest="ci_action", metavar="<action>")
    ci_init_parser = ci_actions.add_parser(
        "init",
        help="Preview (or with --write, scaffold) .github/workflows/m-ci.yml",
        description=(
            "Scaffold .github/workflows/m-ci.yml. Without --write, prints "
            "the planned file path and workflow YAML to stdout and exits 0 "
            "(preview mode — never mutates state). Pass --write to actually "
            "create the file."
        ),
    )
    ci_init_parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Write the workflow file. Without this, prints the planned "
            "path and workflow YAML to stdout and exits 0 (preview mode)."
        ),
    )
    ci_init_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Project root (default: current directory)",
    )
    ci_init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing workflow file (with --write)",
    )
    ci_init_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file progress output",
    )
    ci_init_parser.set_defaults(func=ci_command)

    # `m run`
    run_parser = subparsers.add_parser(
        "run",
        help="Run an M routine via `ydb -run ENTRYREF`",
        description=(
            "Thin wrapper around `ydb -run`. Resolves the ydb binary "
            "(via $YDB, $ydb_dist/ydb, or PATH) and execs it with the "
            "given entryref. Pass `--routines PATH` (repeatable) to "
            "prepend project paths onto $ydb_routines. Extra arguments "
            "after `--` flow through to the M program via $ZCMDLINE. "
            "The subprocess returncode is returned directly."
        ),
    )
    run_parser.add_argument(
        "entryref",
        help="ROUTINE or LABEL^ROUTINE to invoke (case-insensitive)",
    )
    run_parser.add_argument(
        "--routines",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Path to prepend to $ydb_routines (repeatable). When unset, "
            "the parent env's $ydb_routines is used unchanged."
        ),
    )
    run_parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed to the M program via $ZCMDLINE",
    )
    run_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress the `m run: ydb -run ENTRYREF` banner",
    )
    run_parser.set_defaults(func=run_command)

    # `m build`
    build_parser = subparsers.add_parser(
        "build",
        help="Warm-compile M routines via the engine compiler",
        description=(
            "Walk the given paths for `.m` files and run `ydb <file>` "
            "on each — YottaDB compiles the routine to a sibling `.o` "
            "on success and prints a per-file error block on failure. "
            "Errors are surfaced uniformly with a `FILE: compile failed "
            "(rc=N)` header followed by the engine output. Exits 1 on "
            "any failure."
        ),
    )
    build_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to compile (default: current directory)",
    )
    build_parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "After compiling, remove any `.o` files this run produced. "
            "Use in CI gates that just want a 'does it compile?' check "
            "without polluting the working tree."
        ),
    )
    build_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file `ok` lines and the final summary",
    )
    build_parser.set_defaults(func=build_command)

    # `m doc` — godoc-style symbol lookup over the m-stdlib manifest
    # (per discoverability-and-tooling-plan.md § 4.1, WB1). The
    # legacy path-based extract-to-Markdown behaviour is now
    # accessible only via the underlying library
    # (`m_cli.doc.extract` / `m_cli.doc.render`); the CLI surface
    # is the manifest reader.
    doc_parser = subparsers.add_parser(
        "doc",
        help="godoc-style symbol lookup over the m-stdlib manifest",
        description=(
            "Look up a module or label in the m-stdlib manifest and "
            "print its signature, params, returns, raises, examples, "
            "and source pointer. Forms: `m doc STDJSON` (module "
            "overview), `m doc STDJSON.parse` (single label), `m doc "
            "parse` (fuzzy name lookup across modules), `m doc` (list "
            "every module). The manifest is found by walking up from "
            "cwd looking for `dist/stdlib-manifest.json`, then by "
            "checking $M_CLI_MANIFEST, then `~/projects/m-stdlib/"
            "dist/stdlib-manifest.json`; --manifest PATH overrides."
        ),
    )
    doc_parser.add_argument(
        "symbol",
        nargs="?",
        default="",
        help="Symbol to look up: MODULE, MODULE.label, or bare label name",
    )
    doc_parser.add_argument(
        "--short",
        action="store_true",
        help="One-line synopsis instead of full long-form output",
    )
    doc_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw manifest entry as JSON",
    )
    doc_parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    doc_parser.set_defaults(func=doc_command)

    # `m search <query>` — full-text search over the m-stdlib manifest
    # (per discoverability-and-tooling-plan.md § 4.2, WB3). Substring
    # match, case-insensitive, AND-style across query tokens; ranks
    # synopsis hits above description hits above example hits.
    search_parser = subparsers.add_parser(
        "search",
        help="Full-text search over the m-stdlib manifest",
        description=(
            "Walk every (module, label) entry and report any whose "
            "synopsis / description / example contains every space-"
            "separated token in the query (case-insensitive). Results "
            "rank synopsis matches above description above example. "
            "Manifest discovery is shared with `m doc` (--manifest "
            "PATH overrides; otherwise walks up from cwd, then "
            "$M_CLI_MANIFEST, then ~/projects/m-stdlib/dist/...)."
        ),
    )
    search_parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query — space-separated tokens (AND-style match)",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of matches to print (default: 50)",
    )
    search_parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    search_parser.set_defaults(func=search_command)

    # `m manifest [path]` — emit the m-stdlib manifest (or a sub-path)
    # as JSON. Thin wrapper for piping into jq / scripting / AI agent
    # context loading. Per WB4.
    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Emit the m-stdlib manifest (or a sub-path) as JSON",
        description=(
            "With no path, writes the resolved dist/stdlib-manifest.json "
            "to stdout. With a path like STDJSON / STDJSON.parse / "
            "modules / errors / stdlib_version, emits just that subtree. "
            "Manifest discovery is shared with `m doc`."
        ),
    )
    manifest_parser.add_argument(
        "path",
        nargs="?",
        default="",
        help="Sub-path to emit (e.g. STDJSON.parse). Empty = whole manifest.",
    )
    manifest_parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    manifest_parser.set_defaults(func=manifest_command)

    # `m examples [MODULE]` — print every @example body from the
    # manifest, prefixed with `module.label:` for grep-friendliness.
    # Per WB4.
    examples_parser = subparsers.add_parser(
        "examples",
        help="Print every @example from the manifest",
        description=(
            "Walk every public label's @example bodies and emit them "
            "prefixed with `module.label:` so the output is greppable. "
            "With a MODULE argument, scope the walk to that module only."
        ),
    )
    examples_parser.add_argument(
        "module",
        nargs="?",
        default="",
        help="Module to scope output to (default: every module)",
    )
    examples_parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    examples_parser.set_defaults(func=examples_command)

    # `m errors` — list every U-STD* error code with its producing
    # module + labels. Per WB4. Reads dist/errors.json when it exists
    # (m-stdlib's WA7 sidecar); falls back to deriving from the main
    # manifest's per-label `raises` arrays.
    errors_parser = subparsers.add_parser(
        "errors",
        help="List every U-STD* error code and the labels that raise it",
        description=(
            "Inverted index over the manifest's @raises tags: every "
            "U-STDxxx-NAME code is listed with its producing module + "
            "every label that raises it. Reads dist/errors.json when "
            "available (m-stdlib's WA7 sidecar); otherwise derives the "
            "inversion from the main manifest's per-label `raises` arrays."
        ),
    )
    errors_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the errors index as JSON (the same shape as dist/errors.json)",
    )
    errors_parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    errors_parser.set_defaults(func=errors_command)

    # ── `m plugins` — out-of-tree subcommand introspection ────────────
    plugins_parser = subparsers.add_parser(
        "plugins",
        help="List installed m-cli plugins (out-of-tree subcommands)",
        description=(
            "Walks every Python entry-point in the 'm_cli.plugins' "
            "group and reports the discovered subcommands. Plugins "
            "whose names collide with built-ins, fail to load, or "
            "raise during register() are listed under 'conflicts' "
            "and skipped — the dispatcher is never blocked by a "
            "broken plugin. See docs/plugin-development.md for the "
            "contract third-party packages should follow."
        ),
    )
    plugins_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the discovered set as JSON",
    )
    plugins_parser.set_defaults(func=plugins_command)

    # ── `m capabilities` — machine-readable view of the CLI surface ──
    # Drives dist/commands.json (consumed by repo.meta.json's `commands`
    # exposure). Source of truth = this argparse tree.
    capabilities_parser = subparsers.add_parser(
        "capabilities",
        help="Emit a machine-readable view of every m subcommand (JSON)",
        description=(
            "Walk the argparse subparser tree and emit a JSON document "
            "describing every subcommand's purpose, options, choices, "
            "defaults, and (when authored via the parser's epilog field) "
            "example invocations. The output is the source artifact for "
            "dist/commands.json, exposed by tier-1 repo.meta.json. "
            "Plugin-contributed subcommands appear automatically."
        ),
    )
    capabilities_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (currently the only supported format; accepted for explicitness)",
    )
    capabilities_parser.set_defaults(func=capabilities_command)

    # ── Discover and register out-of-tree plugins ─────────────────────
    # Built-in subcommand names — passed to register_plugins() so
    # entry-points that collide with them get rejected up front.
    _builtins = set(subparsers.choices)
    _registered, _conflicts = register_plugins(subparsers, builtins=_builtins)
    # Stash the discovery result on the parser defaults so the
    # `m plugins` handler can read them without rediscovering. Also stash
    # the built-in name set so `m capabilities` can filter out
    # plugin-contributed subparsers — dist/commands.json must describe
    # m-cli's canonical surface, not whatever happens to be installed
    # on the contributor's machine.
    parser.set_defaults(
        _plugin_registered=_registered,
        _plugin_conflicts=_conflicts,
        _m_cli_builtins=frozenset(_builtins),
    )

    # ── Bare-dispatcher overviews (gh-style two-line desc + COMMANDS) ──
    # Must come *after* plugin registration so plugin-contributed
    # subcommands appear in the bare `m` listing alongside built-ins.
    _ROOT_TAGLINE = (
        "Engine-neutral source tooling (fmt/lint/doc); "
        "runtime tools (test/coverage/build) target YottaDB."
    )
    parser.set_defaults(
        func=lambda _a: print_overview(parser, subparsers, tagline=_ROOT_TAGLINE),
    )
    _CI_TAGLINE = (
        "Writes `.github/workflows/m-ci.yml` "
        "(fmt --check + lint + test + coverage)."
    )
    ci_parser.set_defaults(
        func=lambda _a: print_overview(
            ci_parser, ci_actions, tagline=_CI_TAGLINE, word="action"
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Two-pass parsing so unknown flags surface at the *resolved
    # subparser*'s error() — not bubbled to the root parser. Argparse's
    # default routing prints root usage for any unknown arg, which is
    # actively unhelpful when the bogus flag was attached to a leaf (the
    # user can't read off which leaf rejected what). See CLI-UX guide §3.4.
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        leaf = _resolve_leaf_parser(parser, args)
        # parser.error() prints usage to stderr and SystemExits with rc=2.
        leaf.error(f"unrecognized arguments: {' '.join(unknown)}")
    return args.func(args)


def _resolve_leaf_parser(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> argparse.ArgumentParser:
    """Walk down `parser` following the chain of matched subcommands in
    `args`, returning the deepest parser the user actually reached.

    For `m fmt …` this returns the `fmt` subparser. For `m ci init …`
    this walks `m → ci → init`. For bare `m`, it returns the root.
    """
    current = parser
    while True:
        sub_action = next(
            (
                a
                for a in current._actions
                if isinstance(a, argparse._SubParsersAction)
            ),
            None,
        )
        if sub_action is None:
            return current
        sub_name = getattr(args, sub_action.dest, None)
        if not sub_name or sub_name not in sub_action.choices:
            return current
        current = sub_action.choices[sub_name]


if __name__ == "__main__":
    sys.exit(main())
