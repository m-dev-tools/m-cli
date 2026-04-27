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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="m",
        description=(
            "M (MUMPS) source-level toolchain. Subcommands: "
            "fmt (format), lint (planned), test (planned)."
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
