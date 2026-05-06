"""`m` CLI dispatcher.

Single binary `m` with subcommands (`m fmt`, future: `m lint`, `m test`).
Mirrors `cargo`/`go`/`git` style.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli import __version__
from m_cli.coverage.cli import add_arguments as add_coverage_arguments
from m_cli.doctor import doctor_command
from m_cli.fmt import fmt_command
from m_cli.lint import lint_command
from m_cli.lsp import lsp_command
from m_cli.test import test_command
from m_cli.watch import watch_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="m",
        description=(
            "M (MUMPS) source-level toolchain. Subcommands: "
            "fmt (format), lint (lint), test (run test suites), "
            "watch (re-run suites on save), coverage (test coverage), "
            "lsp (Language Server)."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"m-cli {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

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
        nargs="+",
        type=Path,
        help="One or more .m files (or directories — searched recursively for *.m)",
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
        help="One or more .m files (or directories — searched recursively for *.m)",
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
