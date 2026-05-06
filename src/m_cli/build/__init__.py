"""m build — warm-compile a directory of M routines.

Walks the given paths for ``.m`` files, runs ``ydb <file>`` on each
(YDB compiles the routine to a sibling ``.o`` on success), and
aggregates errors. ``--check`` cleans up the ``.o`` byproducts so CI
gates that just want "does it compile?" can use it without polluting
the working tree.
"""

from m_cli.build.cli import build_command
from m_cli.build.runner import (
    BuildResult,
    compile_file,
    discover_files,
)

__all__ = ["build_command", "BuildResult", "compile_file", "discover_files"]
