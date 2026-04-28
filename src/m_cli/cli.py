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
            "'canonical' (every safe rule), 'all', or a comma-separated "
            "list of rule ids (e.g. 'trim-trailing-whitespace'). When "
            "unset, falls back to [fmt] rules from .m-cli.toml / pyproject.toml."
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
            "Run linter rules over M (.m) source files. The default rule "
            "family is 'xindex' — replicating the VistA Toolkit ^XINDEX "
            "rule set as the baseline. Use --rules=all for everything, or "
            "--rules=M-XINDX-013,M-XINDX-019 for a specific subset."
        ),
    )
    lint_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="One or more .m files (or directories — searched recursively for *.m)",
    )
    lint_parser.add_argument(
        "--rules",
        default=None,
        help=(
            "Rule family or comma-separated rule IDs (default: xindex, "
            "or [lint] rules from .m-cli.toml / pyproject.toml)"
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
            "fatal | standard | warning | info (default: warning)"
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
        choices=("text", "tap", "json"),
        default="text",
        help="Output format (default: text)",
    )
    test_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress summary output",
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
            "Examples: `xindex` (default), `all`, `sac`, `M-XINDX-013,M-XINDX-019`."
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
