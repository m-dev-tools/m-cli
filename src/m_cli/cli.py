"""`m` CLI dispatcher.

Single binary `m` with subcommands (`m fmt`, future: `m lint`, `m test`).
Mirrors `cargo`/`go`/`git` style.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli import __version__
from m_cli.fmt import fmt_command
from m_cli.lint import lint_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="m",
        description=(
            "M (MUMPS) source-level toolchain. Subcommands: "
            "fmt (format), lint (lint), test (planned)."
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
        default="xindex",
        help="Rule family or comma-separated rule IDs (default: xindex)",
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
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress summary output",
    )
    lint_parser.set_defaults(func=lint_command)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
